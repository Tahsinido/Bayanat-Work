"""Search-only bulletin access.

Browsing the bulletin list and searching it are separate privileges. A user
without the browse permission gets nothing back from the list endpoint until
they actually search for something; a user who has it keeps the paginated feed
of the whole table.

The rule lives on the API rather than in the page, so calling
/admin/api/bulletins/ directly is subject to exactly the same restriction as
the UI is.

A search also grants access to what it found: the bulletins a user's own search
surfaced become openable by that user for a while. Without that the
single-record endpoint would be an unmetered way around the list restriction --
walk the ids and read the table one row at a time. Hits are held per user in
Redis under an expiry, so what a search grants is scoped to the searcher and
does not outlive their work on it.

Per-record role restrictions (User.can_access) are untouched and still apply on
top of all of this. This module decides *whether* results may come back at all,
never *which* ones.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, Optional

from flask_security.decorators import current_user

from enferno.extensions import rds
from enferno.utils.logging_utils import get_logger

logger = get_logger()

# How long a bulletin stays openable after a search surfaced it. Long enough to
# read through a result set and come back to it, short enough that access
# granted by one afternoon's search does not persist indefinitely.
DEFAULT_SEARCH_HIT_TTL = 24 * 60 * 60

_KEY = "bulletin:searchhit:{user}:{bulletin}"

# Keys that appear in a query block but narrow nothing by themselves.
#
# The `op*` family chooses how other filters combine (and/or), `child*` widens
# a taxonomy filter to its descendants, and the event flags shape how event
# conditions are grouped. A block holding only these has not searched for
# anything, so it must not unlock results.
#
# `ids` is here for a different reason: it is an enumeration primitive. Left to
# count as a search, a caller could post every id in the table and get the whole
# database back through the search path -- exactly what the browse restriction
# exists to prevent. Combined with a real filter it is harmless, since the other
# filter still does the narrowing.
NON_QUALIFYING_KEYS = frozenset(
    {
        "op",
        "opTags",
        "optags",
        "opTerms",
        "opETags",
        "opETerms",
        "opEthno",
        "opNat",
        "opDialects",
        "oplabels",
        "oplocations",
        "opsources",
        "opvlabels",
        "childlabels",
        "childsources",
        "childverlabels",
        "inEact",
        "eEact",
        "singleEvent",
        "ids",
    }
)


def search_hit_ttl() -> int:
    """Seconds a searched-for bulletin stays openable.

    Kept tolerant: a bad value in the saved configuration must not take bulletin
    access down, so it is logged and the default stands.
    """
    value = None
    try:
        from enferno.settings import Config

        value = Config.get("BULLETIN_SEARCH_HIT_TTL", None)
    except Exception:
        value = None

    if value is None:
        value = os.environ.get("BULLETIN_SEARCH_HIT_TTL")
    if value is None or value == "":
        return DEFAULT_SEARCH_HIT_TTL

    try:
        return max(60, int(value))
    except (TypeError, ValueError):
        logger.warning(
            f"Invalid BULLETIN_SEARCH_HIT_TTL={value!r}, "
            f"falling back to {DEFAULT_SEARCH_HIT_TTL}"
        )
        return DEFAULT_SEARCH_HIT_TTL


def can_browse(user: Optional[Any] = None) -> bool:
    """True when this user may list bulletins without searching first.

    Admins always may. Everyone else needs the permission granted to them
    explicitly, the same way exporting and media access are granted.
    """
    user = current_user if user is None else user
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.has_role("Admin"):
        return True
    return bool(getattr(user, "can_browse_bulletins", False))


def is_search(q: Any) -> bool:
    """True when the query actually asks for something.

    `q` is the list of filter blocks the search endpoint receives. An unfiltered
    listing arrives as `[{}]`, and blocks whose values are all empty (a cleared
    text box, an emptied multi-select) are no different from that -- both mean
    "everything", which is the thing a search-only user may not have.
    """
    for block in q or []:
        if not isinstance(block, dict):
            continue
        for key, value in block.items():
            if key in NON_QUALIFYING_KEYS:
                continue
            # False and 0 are legitimate filter values; "" and [] are not.
            if value is None or value == "" or value == [] or value == {}:
                continue
            return True
    return False


def _key(user_id: int, bulletin_id: int) -> str:
    return _KEY.format(user=user_id, bulletin=bulletin_id)


def remember_hits(ids: Iterable[Any], user: Optional[Any] = None) -> None:
    """Record that this user's own search surfaced these bulletins.

    A no-op for users who can browse: nothing needs remembering when every
    record is open to them anyway.
    """
    user = current_user if user is None else user
    user_id = getattr(user, "id", None)
    if not user_id or can_browse(user):
        return

    wanted = []
    for value in ids or []:
        try:
            wanted.append(int(value))
        except (TypeError, ValueError):
            continue
    if not wanted:
        return

    ttl = search_hit_ttl()
    try:
        pipe = rds.pipeline()
        for bulletin_id in wanted:
            pipe.setex(_key(user_id, bulletin_id), ttl, 1)
        pipe.execute()
    except Exception as e:
        # The search itself still succeeded; only the follow-up "open this
        # result" will be refused. Logged loudly because that combination looks
        # like a permissions bug from the user's side.
        logger.error(f"Could not record bulletin search hits for user {user_id}: {e}")


def may_open(bulletin_id: Any, user: Optional[Any] = None) -> bool:
    """True when this user may open this bulletin's full record.

    Either they can browse, or one of their own searches put this bulletin in
    front of them. Says nothing about the record's own role restrictions --
    User.can_access is still checked separately by the caller.
    """
    user = current_user if user is None else user
    if can_browse(user):
        return True

    user_id = getattr(user, "id", None)
    if not user_id:
        return False

    try:
        return bool(rds.exists(_key(user_id, int(bulletin_id))))
    except (TypeError, ValueError):
        return False
    except Exception as e:
        # Fail closed. An access check that cannot be evaluated is not a pass.
        logger.error(f"Could not check bulletin search hits for user {user_id}: {e}")
        return False
