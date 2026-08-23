"""Eyewitness capture API.

Mirrors the evidence endpoints so access rules, audit calls and pagination
behave the same way across record types.

Every field on the record is filterable, and the ones that point at another
entity filter by that entity rather than by a copied string -- searching for
captures naming a perpetrator finds them through the actor link, so a rename of
the actor does not strand the captures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from flask import Response, request
from flask.templating import render_template
from flask_security.decorators import auth_required, current_user, roles_accepted
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from enferno.admin.models import Activity, Evidence, Eyewitness, Media
from enferno.extensions import db
from enferno.utils.http_response import HTTPResponse
from enferno.utils.logging_utils import get_logger
import enferno.utils.typing as t
from . import admin, PER_PAGE

logger = get_logger()


def _can_access(record: Eyewitness) -> bool:
    """Role-restricted records are visible only to holders of those roles."""
    if not record.roles:
        return True
    if current_user.has_role("Admin"):
        return True
    user_roles = {r.id for r in current_user.roles}
    return bool(user_roles & {r.id for r in record.roles})


def _load(id: int) -> Optional[Eyewitness]:
    record = Eyewitness.query.filter(
        Eyewitness.id == id, Eyewitness.deleted.is_(False)
    ).first()
    if record is None or not _can_access(record):
        return None
    return record


def _parse_date(value):
    """A date filter bound, or None if unusable.

    A malformed bound narrows nothing rather than failing the whole search.
    """
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    logger.warning(f"Ignoring unparseable eyewitness date filter: {value!r}")
    return None


@admin.route("/eyewitness/", defaults={"id": None})
@admin.route("/eyewitness/<int:id>")
@roles_accepted("Admin", "Mod", "DA")
def eyewitness_dashboard(id: Optional[t.id]) -> str:
    """Eyewitness capture list and record view."""
    return render_template("admin/eyewitness.html")


@admin.post("/api/eyewitness/")
@auth_required("session")
def api_eyewitness_list() -> Response:
    """
    Paginated, filtered eyewitness list.

    Returns:
        - json feed of eyewitness captures.
    """
    payload = request.json or {}
    page = payload.get("page", 1)
    per_page = min(int(payload.get("per_page", PER_PAGE)), 100)
    q = payload.get("q") or {}

    query = Eyewitness.query.filter(Eyewitness.deleted.is_(False))

    for field, column in (
        ("item_id", Eyewitness.item_id),
        ("device_id", Eyewitness.device_id),
        ("username", Eyewitness.username),
    ):
        if q.get(field):
            query = query.filter(column.ilike(f"%{q[field]}%"))

    if q.get("status"):
        query = query.filter(Eyewitness.status == q["status"])

    if q.get("number_of_items_min") not in (None, ""):
        try:
            query = query.filter(Eyewitness.number_of_items >= int(q["number_of_items_min"]))
        except (TypeError, ValueError):
            pass
    if q.get("number_of_items_max") not in (None, ""):
        try:
            query = query.filter(Eyewitness.number_of_items <= int(q["number_of_items_max"]))
        except (TypeError, ValueError):
            pass

    if q.get("text"):
        needle = f"%{q['text']}%"
        query = query.filter(
            or_(
                Eyewitness.event_description.ilike(needle),
                Eyewitness.user_notes.ilike(needle),
                Eyewitness.item_id.ilike(needle),
                Eyewitness.device_id.ilike(needle),
                Eyewitness.username.ilike(needle),
            )
        )

    for bound, op in (("_from", "ge"), ("_to", "le")):
        raw = q.get(f"date_of_capture{bound}")
        if not raw:
            continue
        parsed = _parse_date(raw)
        if parsed is None:
            continue
        query = query.filter(
            Eyewitness.date_of_capture >= parsed
            if op == "ge"
            else Eyewitness.date_of_capture <= parsed
        )

    # Entity filters go through the link, not a copied string.
    if q.get("alleged_event_id"):
        query = query.filter(Eyewitness.alleged_event_id == q["alleged_event_id"])
    if q.get("capture_location_id"):
        query = query.filter(Eyewitness.capture_location_id == q["capture_location_id"])
    if q.get("perpetrator_id"):
        query = query.filter(Eyewitness.alleged_perpetrators.any(id=q["perpetrator_id"]))
    if q.get("tag_id"):
        query = query.filter(Eyewitness.tags.any(id=q["tag_id"]))
    if q.get("bulletin_id"):
        query = query.filter(Eyewitness.bulletins.any(id=q["bulletin_id"]))
    if q.get("evidence_id"):
        query = query.filter(Eyewitness.evidence_items.any(id=q["evidence_id"]))
    if q.get("field_data_id"):
        query = query.filter(Eyewitness.field_data.any(id=q["field_data_id"]))
    if q.get("has_coordinates"):
        query = query.filter(Eyewitness.latitude.isnot(None), Eyewitness.longitude.isnot(None))

    result = (
        query.options(
            selectinload(Eyewitness.roles),
            selectinload(Eyewitness.tags),
            selectinload(Eyewitness.alleged_perpetrators),
            # The list renders a location for every row, which reads the chosen
            # location and falls back to the linked site's name. Without these
            # the page costs two extra queries per row.
            selectinload(Eyewitness.capture_location),
            selectinload(Eyewitness.field_data),
        )
        .order_by(Eyewitness.id.desc())
        .paginate(page=page, per_page=per_page, count=True)
    )

    items = [e.to_dict(include_media=False) for e in result.items if _can_access(e)]
    return HTTPResponse.success(data={"items": items, "perPage": per_page, "total": result.total})


@admin.get("/api/eyewitness/<int:id>")
@auth_required("session")
def api_eyewitness_get(id: t.id) -> Response:
    """
    A single capture with its links and media.

    Returns:
        - the eyewitness record.
    """
    record = _load(id)
    if record is None:
        return HTTPResponse.not_found("Eyewitness record not found")
    return HTTPResponse.success(data=record.to_dict())


@admin.post("/api/eyewitness/create")
@roles_accepted("Admin", "Mod", "DA")
def api_eyewitness_create() -> Response:
    """
    Create a capture.

    Returns:
        - the created record.
    """
    payload = (request.json or {}).get("item") or {}

    record = Eyewitness()
    record.from_json(payload)
    record.user_id = current_user.id
    if not record.status:
        record.status = Eyewitness.STATUS_DRAFT
    db.session.add(record)
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_CREATE,
        Activity.STATUS_SUCCESS,
        record.to_mini(),
        "eyewitness",
    )
    return HTTPResponse.created(data={"item": record.to_dict()}, message="Eyewitness record created")


@admin.put("/api/eyewitness/<int:id>")
@roles_accepted("Admin", "Mod", "DA")
def api_eyewitness_update(id: t.id) -> Response:
    """
    Update a capture.

    Returns:
        - the updated record.
    """
    record = _load(id)
    if record is None:
        return HTTPResponse.not_found("Eyewitness record not found")

    payload = (request.json or {}).get("item") or {}
    record.from_json(payload)
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_UPDATE,
        Activity.STATUS_SUCCESS,
        record.to_mini(),
        "eyewitness",
    )
    return HTTPResponse.success(data={"item": record.to_dict()}, message="Eyewitness record saved")


@admin.post("/api/eyewitness/<int:id>/media")
@roles_accepted("Admin", "Mod", "DA")
def api_eyewitness_add_media(id: t.id) -> Response:
    """
    Register an uploaded file as media on this capture.

    Matches the evidence endpoint: /api/media/upload/ stores the bytes, this
    creates the Media row and links it, so a file is never left uploaded but
    unattached.

    Returns:
        - the created (or re-used) media item.
    """
    record = _load(id)
    if record is None:
        return HTTPResponse.not_found("Eyewitness record not found")

    payload = request.json or {}
    if not payload.get("filename"):
        return HTTPResponse.error("A stored filename is required", status=417)

    media = None
    etag = payload.get("etag")
    if etag:
        media = Media.query.filter(Media.etag == etag, Media.deleted == False).first()
        if media is not None and media.eyewitness_id and media.eyewitness_id != record.id:
            return HTTPResponse.error(
                "That file is already attached to another eyewitness record", status=409
            )

    if media is None:
        media = Media()
        media.from_json(payload)
        media.user_id = current_user.id
        db.session.add(media)

    media.eyewitness_id = record.id
    if media.version is None:
        media.version = 1
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_UPDATE,
        Activity.STATUS_SUCCESS,
        {**record.to_mini(), "attached_media_id": media.id},
        "eyewitness",
    )
    return HTTPResponse.success(data={"item": media.to_dict()}, message="File attached")


@admin.delete("/api/eyewitness/<int:id>/media/<int:media_id>")
@roles_accepted("Admin", "Mod", "DA")
def api_eyewitness_detach_media(id: t.id, media_id: t.id) -> Response:
    """
    Unlink a file from a capture. The file itself is kept.

    Returns:
        - confirmation.
    """
    record = _load(id)
    if record is None:
        return HTTPResponse.not_found("Eyewitness record not found")

    media = db.session.get(Media, media_id)
    if media is None or media.eyewitness_id != record.id:
        return HTTPResponse.not_found("Media not attached to this record")

    media.eyewitness_id = None
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_UPDATE,
        Activity.STATUS_SUCCESS,
        {**record.to_mini(), "detached_media_id": media.id},
        "eyewitness",
    )
    return HTTPResponse.success(message="Media unlinked")
