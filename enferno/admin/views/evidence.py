"""Evidence management API.

Covers the record, its chain of custody, its revision history, and the linking
of media to it. Deliberately mirrors the bulletin endpoints so the access rules,
audit calls and pagination behave the same way across record types.

Two rules run through all of it:

  Evidence is archived, never deleted. There is no destructive endpoint; the
  closest is a status change to Archived, which is Admin-only and logged.

  Custody is append-only. There is no update or delete route for a custody
  entry -- a mistake is corrected by appending a Correction, so the chain always
  reads as what was recorded at the time.
"""

from __future__ import annotations

from typing import Optional

from flask import Response, request
from flask.templating import render_template
from flask_security.decorators import auth_required, current_user, roles_accepted, roles_required
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from enferno.admin.models import (
    Activity,
    Evidence,
    EvidenceCustody,
    EvidenceHistory,
    Media,
)
from enferno.extensions import db
from enferno.utils.http_response import HTTPResponse
from enferno.utils.logging_utils import get_logger
import enferno.utils.typing as t
from . import admin, PER_PAGE

logger = get_logger()


def _can_access(evidence: Evidence) -> bool:
    """Access-role check, matching how bulletins and actors are gated.

    An evidence record with no roles attached is unrestricted; one with roles is
    visible only to holders of those roles. Admins see everything.
    """
    if current_user.has_role("Admin"):
        return True
    if not evidence.roles:
        # Restrictive mode treats "no roles" as nobody-but-admin.
        from flask import current_app

        return not current_app.config.get("ACCESS_CONTROL_RESTRICTIVE")
    user_roles = {r.id for r in (current_user.roles or [])}
    return bool(user_roles & {r.id for r in evidence.roles})


def _load(id: int) -> Optional[Evidence]:
    """Fetch an evidence record with its relations, or None if out of reach."""
    evidence = (
        Evidence.query.filter(Evidence.id == id, Evidence.deleted.is_(False))
        .options(
            selectinload(Evidence.roles),
            selectinload(Evidence.bulletins),
            selectinload(Evidence.actors),
            selectinload(Evidence.locations),
            selectinload(Evidence.events),
            selectinload(Evidence.sources),
            selectinload(Evidence.related_evidence),
            selectinload(Evidence.medias),
        )
        .first()
    )
    if evidence is None or not _can_access(evidence):
        return None
    return evidence


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------


@admin.route("/evidence/", defaults={"id": None})
@admin.route("/evidence/<int:id>")
@roles_accepted("Admin", "Mod", "DA")
def evidence_dashboard(id: Optional[t.id]) -> str:
    """The Evidence section."""
    return render_template("admin/evidence.html")


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


def _parse_date(value):
    """A date filter bound, or None if it is not a date we can use.

    A malformed bound is dropped rather than raised: a stray character in one
    date box should narrow nothing, not fail the whole search.
    """
    from datetime import datetime

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
    logger.warning(f"Ignoring unparseable evidence date filter: {value!r}")
    return None


@admin.post("/api/evidence/")
@auth_required("session")
def api_evidence_list() -> Response:
    """
    Paginated, filtered evidence list.

    Filters map onto the search requirements: identifier, type, status,
    confidentiality, relevance, dates, and the related bulletin, location,
    actor, event and source.

    Returns:
        - json feed of evidence records.
    """
    payload = request.json or {}
    page = payload.get("page", 1)
    per_page = min(int(payload.get("per_page", PER_PAGE)), 100)
    q = payload.get("q") or {}

    query = Evidence.query.filter(Evidence.deleted.is_(False))

    if q.get("evidence_number"):
        query = query.filter(Evidence.evidence_number.ilike(f"%{q['evidence_number']}%"))
    if q.get("case_code"):
        query = query.filter(Evidence.case_code.ilike(f"%{q['case_code']}%"))
    if q.get("evidence_type"):
        query = query.filter(Evidence.evidence_type == q["evidence_type"])
    if q.get("status"):
        query = query.filter(Evidence.status == q["status"])
    if q.get("confidentiality"):
        query = query.filter(Evidence.confidentiality == q["confidentiality"])
    if q.get("collector"):
        query = query.filter(Evidence.collector.ilike(f"%{q['collector']}%"))
    if q.get("text"):
        needle = f"%{q['text']}%"
        query = query.filter(
            or_(
                Evidence.description.ilike(needle),
                Evidence.content_summary.ilike(needle),
                Evidence.relevance.ilike(needle),
                Evidence.notes.ilike(needle),
                Evidence.evidence_number.ilike(needle),
                Evidence.case_code.ilike(needle),
            )
        )
    # Date ranges. Each bound is optional, so "everything before X" and
    # "everything after X" are both expressible.
    for field, column in (
        ("date_collected", Evidence.date_collected),
        ("evidence_date", Evidence.evidence_date),
    ):
        for bound, op in (("_from", "ge"), ("_to", "le")):
            raw = q.get(f"{field}{bound}")
            if not raw:
                continue
            parsed = _parse_date(raw)
            if parsed is None:
                continue
            query = query.filter(column >= parsed if op == "ge" else column <= parsed)

    if q.get("bulletin_id"):
        query = query.filter(Evidence.bulletins.any(id=q["bulletin_id"]))
    if q.get("location_id"):
        query = query.filter(Evidence.locations.any(id=q["location_id"]))
    if q.get("actor_id"):
        query = query.filter(Evidence.actors.any(id=q["actor_id"]))
    if q.get("event_id"):
        query = query.filter(Evidence.events.any(id=q["event_id"]))
    if q.get("source_id"):
        query = query.filter(Evidence.sources.any(id=q["source_id"]))

    result = (
        query.options(selectinload(Evidence.roles), selectinload(Evidence.bulletins))
        .order_by(Evidence.id.desc())
        .paginate(page=page, per_page=per_page, count=True)
    )

    # Access filtering happens after the query because it depends on role
    # intersection; the page may therefore come back short, which matches how
    # the other record types behave.
    items = [e.to_dict(include_media=False) for e in result.items if _can_access(e)]

    return HTTPResponse.success(data={"items": items, "perPage": per_page, "total": result.total})


@admin.get("/api/evidence/<int:id>")
@auth_required("session")
def api_evidence_get(id: t.id) -> Response:
    """
    A single evidence record with its media and custody chain.

    Returns:
        - the evidence record, or 404 when missing or out of reach.
    """
    evidence = _load(id)
    if evidence is None:
        # Same answer for missing and restricted: the existence of a restricted
        # evidence item is itself worth not confirming.
        return HTTPResponse.not_found("Evidence not found")

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_VIEW,
        Activity.STATUS_SUCCESS,
        evidence.to_mini(),
        "evidence",
    )
    return HTTPResponse.success(data=evidence.to_dict())


@admin.post("/api/evidence/create")
@roles_accepted("Admin", "Mod", "DA")
def api_evidence_create() -> Response:
    """
    Create an evidence record.

    The identifier is assigned here and is never taken from input, so an
    evidence number cannot be chosen or reused.

    Returns:
        - the created record.
    """
    payload = (request.json or {}).get("item") or {}

    evidence = Evidence()
    evidence.evidence_number = Evidence.generate_number()
    evidence.user_id = current_user.id
    evidence.collected_by_id = payload.get("collected_by_id") or current_user.id
    evidence.from_json(payload)

    db.session.add(evidence)
    db.session.commit()

    evidence.create_revision(user_id=current_user.id)

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_CREATE,
        Activity.STATUS_SUCCESS,
        evidence.to_mini(),
        "evidence",
    )
    return HTTPResponse.created(
        data={"item": evidence.to_dict()},
        message=f"Created evidence {evidence.evidence_number}",
    )


@admin.put("/api/evidence/<int:id>")
@roles_accepted("Admin", "Mod", "DA")
def api_evidence_update(id: t.id) -> Response:
    """
    Update an evidence record, snapshotting the previous state first.

    Returns:
        - the updated record.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    if evidence.status == Evidence.STATUS_ARCHIVED and not current_user.has_role("Admin"):
        return HTTPResponse.forbidden("Archived evidence can only be changed by an admin")

    payload = (request.json or {}).get("item") or {}
    # Neither the identifier nor the creator is editable.
    payload.pop("evidence_number", None)
    evidence.from_json(payload)
    db.session.commit()

    evidence.create_revision(user_id=current_user.id)

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_UPDATE,
        Activity.STATUS_SUCCESS,
        evidence.to_mini(),
        "evidence",
    )
    return HTTPResponse.success(
        data={"item": evidence.to_dict()}, message=f"Saved {evidence.evidence_number}"
    )


@admin.put("/api/evidence/<int:id>/archive")
@roles_required("Admin")
def api_evidence_archive(id: t.id) -> Response:
    """
    Archive an evidence record.

    This is the closest thing to deletion the module offers. The row, its
    history, its custody chain and its media all stay in place -- archiving is a
    status change, so nothing about the evidence is destroyed.

    Returns:
        - the archived record.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    evidence.status = Evidence.STATUS_ARCHIVED
    db.session.commit()
    evidence.create_revision(user_id=current_user.id)

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_ARCHIVE,
        Activity.STATUS_SUCCESS,
        evidence.to_mini(),
        "evidence",
    )
    return HTTPResponse.success(
        data={"item": evidence.to_mini()}, message=f"Archived {evidence.evidence_number}"
    )


# --------------------------------------------------------------------------
# Chain of custody -- create and read only, by design
# --------------------------------------------------------------------------


@admin.get("/api/evidence/<int:id>/custody")
@auth_required("session")
def api_evidence_custody_list(id: t.id) -> Response:
    """
    The custody chain for an evidence record, oldest first.

    Returns:
        - the custody entries.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    entries = (
        EvidenceCustody.query.filter(EvidenceCustody.evidence_id == id)
        .order_by(EvidenceCustody.occurred_at.asc(), EvidenceCustody.id.asc())
        .all()
    )
    return HTTPResponse.success(data={"items": [e.to_dict() for e in entries]})


@admin.post("/api/evidence/<int:id>/custody")
@roles_accepted("Admin", "Mod", "DA")
def api_evidence_custody_add(id: t.id) -> Response:
    """
    Append a custody entry.

    There is no matching update or delete route. Custody is a record of what
    happened, so an error is corrected by appending an entry with action
    "Correction" explaining it, leaving the original in place.

    Returns:
        - the created entry.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    payload = (request.json or {}).get("item") or {}
    action = payload.get("action")
    if action not in EvidenceCustody.ACTIONS:
        return HTTPResponse.error(
            f"action must be one of: {', '.join(EvidenceCustody.ACTIONS)}", status=400
        )

    entry = EvidenceCustody(evidence_id=evidence.id, recorded_by_id=current_user.id)
    entry.from_json(payload)
    db.session.add(entry)
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_CUSTODY_ADD,
        Activity.STATUS_SUCCESS,
        entry.to_mini(),
        "evidence_custody",
    )
    return HTTPResponse.created(data={"item": entry.to_dict()}, message="Custody entry recorded")


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


@admin.get("/api/evidence/<int:id>/history")
@auth_required("session")
def api_evidence_history(id: t.id) -> Response:
    """
    Revision history for an evidence record.

    The depth of each revision depends on the caller's view_full_history
    permission, which EvidenceHistory.to_dict enforces.

    Returns:
        - the revisions, newest first.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    revisions = (
        EvidenceHistory.query.filter(EvidenceHistory.evidence_id == id)
        .order_by(EvidenceHistory.id.desc())
        .all()
    )
    return HTTPResponse.success(data={"items": [r.to_dict() for r in revisions]})


# --------------------------------------------------------------------------
# Media linkage
# --------------------------------------------------------------------------


@admin.put("/api/evidence/<int:id>/media/<int:media_id>")
@roles_accepted("Admin", "Mod", "DA")
def api_evidence_attach_media(id: t.id, media_id: t.id) -> Response:
    """
    Attach an already-uploaded media file to an evidence record.

    The file is not copied -- only the link is set -- so the same stored file is
    never duplicated by being associated with a record. A human-readable media
    number is assigned on first attach.

    Returns:
        - the attached media item.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    media = db.session.get(Media, media_id)
    if media is None or media.deleted:
        return HTTPResponse.not_found("Media not found")

    media.evidence_id = evidence.id
    if not media.media_number:
        media.media_number = _next_media_number(media)
    if media.version is None:
        media.version = 1
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_UPDATE,
        Activity.STATUS_SUCCESS,
        {**evidence.to_mini(), "attached_media_id": media.id},
        "evidence",
    )
    return HTTPResponse.success(data={"item": media.to_dict()}, message="Media attached")


@admin.post("/api/evidence/<int:id>/media")
@roles_accepted("Admin", "Mod", "DA")
def api_evidence_add_media(id: t.id) -> Response:
    """
    Register a freshly uploaded file as media on this evidence record.

    /api/media/upload/ stores the bytes and hands back a filename and etag, but
    it does not create a Media row -- for bulletins that happens when the parent
    is saved. Evidence records attach files one at a time, so this does both
    steps together: a file can never be left uploaded but unattached.

    The etag is the file's hash, so re-uploading the same bytes re-uses the
    existing Media row rather than creating a second record pointing at the same
    content. A file already held as evidence elsewhere is refused, because a
    single exhibit belongs to one record.

    Returns:
        - the created (or re-used) media item.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    payload = request.json or {}
    if not payload.get("filename"):
        return HTTPResponse.error("A stored filename is required", status=417)

    media = None
    etag = payload.get("etag")
    if etag:
        media = Media.query.filter(Media.etag == etag, Media.deleted == False).first()
        if media is not None and media.evidence_id and media.evidence_id != evidence.id:
            return HTTPResponse.error(
                "That file is already attached to another evidence record", status=409
            )

    if media is None:
        media = Media()
        media.from_json(payload)
        media.user_id = current_user.id
        db.session.add(media)

    media.evidence_id = evidence.id
    if not media.media_number:
        media.media_number = _next_media_number(media)
    if media.version is None:
        media.version = 1
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_UPDATE,
        Activity.STATUS_SUCCESS,
        {**evidence.to_mini(), "attached_media_id": media.id},
        "evidence",
    )
    return HTTPResponse.success(data={"item": media.to_dict()}, message="File attached")


@admin.delete("/api/evidence/<int:id>/media/<int:media_id>")
@roles_accepted("Admin", "Mod", "DA")
def api_evidence_detach_media(id: t.id, media_id: t.id) -> Response:
    """
    Unlink a media file from an evidence record.

    Unlinking clears the association only; the file and its media row remain, so
    detaching is not a route to deleting evidence.

    Returns:
        - confirmation.
    """
    evidence = _load(id)
    if evidence is None:
        return HTTPResponse.not_found("Evidence not found")

    media = db.session.get(Media, media_id)
    if media is None or media.evidence_id != evidence.id:
        return HTTPResponse.not_found("Media not attached to this evidence")

    media.evidence_id = None
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_EVIDENCE_UPDATE,
        Activity.STATUS_SUCCESS,
        {**evidence.to_mini(), "detached_media_id": media.id},
        "evidence",
    )
    return HTTPResponse.success(message="Media unlinked")


def _next_media_number(media: Media) -> str:
    """IMG-000456 / VID-000457 / AUD-.. / DOC-.. depending on the file type.

    Prefixed by kind so an identifier is recognisable on a custody form without
    having to look it up.
    """
    file_type = (media.media_file_type or "").lower()
    if file_type.startswith("image"):
        prefix = "IMG"
    elif file_type.startswith("video"):
        prefix = "VID"
    elif file_type.startswith("audio"):
        prefix = "AUD"
    else:
        prefix = "DOC"

    last = (
        db.session.query(Media.media_number)
        .filter(Media.media_number.like(f"{prefix}-%"))
        .order_by(Media.media_number.desc())
        .limit(1)
        .scalar()
    )
    seq = 0
    if last:
        try:
            seq = int(last.split("-", 1)[1])
        except (ValueError, IndexError):
            seq = 0
    while True:
        seq += 1
        candidate = f"{prefix}-{seq:06d}"
        exists = db.session.query(Media.id).filter(Media.media_number == candidate).first()
        if not exists:
            return candidate
