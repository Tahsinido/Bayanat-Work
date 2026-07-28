from __future__ import annotations

from flask import Response, request
from flask.templating import render_template
from flask_security.decorators import current_user, roles_accepted, roles_required
from sqlalchemy import desc, or_

from enferno.extensions import db
from enferno.admin.constants import Constants
from enferno.admin.models import Activity, MissingPerson
from enferno.admin.models.Notification import Notification
from enferno.admin.validation.models import MissingPersonRequestModel
from enferno.utils.http_response import HTTPResponse
from enferno.utils.search_snippets import first_snippet
from enferno.utils.validation_utils import validate_with
import enferno.utils.typing as t
from . import admin, PER_PAGE

# Columns the list endpoint may sort by; anything else falls back to id so a
# crafted sort key cannot reach an arbitrary attribute.
SORTABLE_COLUMNS = {
    "id",
    "name",
    "interview_code",
    "family_member_name",
    "family_phone",
    "created_by",
    "modified_last_by",
    "modified_last_date",
}


@admin.route("/missing-persons/")
@roles_accepted("Admin", "Mod", "DA")
def missing_persons() -> str:
    """
    Endpoint to render the missing persons backend page.

    Returns:
        - html template of the missing persons backend page.
    """
    return render_template("admin/missing-persons.html")


@admin.route("/api/missing-persons/")
def api_missing_persons() -> Response:
    """
    API Endpoint to feed json data of missing person records, supports paging,
    search and sorting.

    Returns:
        - json response of missing person records.
    """
    q = request.args.get("q")
    page = request.args.get("page", 1, int)
    per_page = request.args.get("per_page", PER_PAGE, int)
    sort_by = request.args.get("sort_by")
    sort_desc = request.args.get("sort_desc", "false").lower() == "true"

    query = MissingPerson.query.filter(MissingPerson.deleted == False)  # noqa: E712

    terms = [word for word in (q or "").split(" ") if word]

    if terms:
        # Every word must appear somewhere, so extra terms narrow the result.
        for word in terms:
            term = f"%{word}%"
            query = query.filter(
                or_(
                    MissingPerson.name.ilike(term),
                    MissingPerson.interview_code.ilike(term),
                    MissingPerson.family_member_name.ilike(term),
                    MissingPerson.family_phone.ilike(term),
                    MissingPerson.note.ilike(term),
                )
            )

    if sort_by in SORTABLE_COLUMNS:
        column = getattr(MissingPerson, sort_by)
        query = query.order_by(desc(column) if sort_desc else column)
    else:
        query = query.order_by(desc(MissingPerson.id))

    result = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for item in result.items:
        data = item.to_dict()
        if terms:
            # Same keyword-in-context treatment as Field Data and Bulletins.
            data["snippet"] = first_snippet([("Note", item.note)], terms)
        items.append(data)

    response = {"items": items, "perPage": per_page, "total": result.total}
    return HTTPResponse.success(data=response)


@admin.get("/api/missing-persons/<int:id>")
def api_missing_person_get(id: t.id) -> Response:
    """
    Endpoint to get a single missing person record.

    Args:
        - id: id of the item.

    Returns:
        - json response of the record.
    """
    item = db.session.get(MissingPerson, id)
    if item is None or item.deleted:
        return HTTPResponse.not_found("Missing Person not found")
    return HTTPResponse.success(data={"item": item.to_dict()})


@admin.post("/api/missing-persons/")
@roles_accepted("Admin", "Mod", "DA")
@validate_with(MissingPersonRequestModel)
def api_missing_person_create(validated_data: dict) -> Response:
    """
    Endpoint to create a missing person record.

    Args:
        - validated_data: validated data from the request.

    Returns:
        - success/error string based on the operation result.
    """
    item = MissingPerson()
    item = item.from_json(validated_data["item"])
    item.stamp_modified_by(current_user)

    if item.save():
        Activity.create(
            current_user,
            Activity.ACTION_CREATE,
            Activity.STATUS_SUCCESS,
            item.to_mini(),
            "missing_person",
        )
        return HTTPResponse.created(
            message=f"Created Missing Person #{item.id}", data={"item": item.to_dict()}
        )
    return HTTPResponse.error("Save Failed", status=500)


@admin.put("/api/missing-persons/<int:id>")
@roles_accepted("Admin", "Mod", "DA")
@validate_with(MissingPersonRequestModel)
def api_missing_person_update(id: t.id, validated_data: dict) -> Response:
    """
    Endpoint to update a missing person record.

    Args:
        - id: id of the item to update.
        - validated_data: validated data from the request.

    Returns:
        - success/error string based on the operation result.
    """
    item = db.session.get(MissingPerson, id)
    if item is None or item.deleted:
        return HTTPResponse.not_found("Missing Person not found")

    item = item.from_json(validated_data["item"])
    item.stamp_modified_by(current_user)

    if item.save():
        Activity.create(
            current_user,
            Activity.ACTION_UPDATE,
            Activity.STATUS_SUCCESS,
            item.to_mini(),
            "missing_person",
        )
        return HTTPResponse.success(message=f"Saved Missing Person #{item.id}")
    return HTTPResponse.error("Save Failed", status=500)


@admin.delete("/api/missing-persons/<int:id>")
@roles_required("Admin")
def api_missing_person_delete(id: t.id) -> Response:
    """
    Endpoint to delete a missing person record.

    Args:
        - id: id of the item to delete.

    Returns:
        - success/error string based on the operation result.
    """
    item = db.session.get(MissingPerson, id)
    if item is None or item.deleted:
        return HTTPResponse.not_found("Missing Person not found")

    subject = item.to_mini()
    name = item.name

    if item.delete():
        Activity.create(
            current_user,
            Activity.ACTION_DELETE,
            Activity.STATUS_SUCCESS,
            subject,
            "missing_person",
        )
        Notification.send_admin_notification_for_event(
            Constants.NotificationEvent.ITEM_DELETED,
            "Missing Person Deleted",
            f"Missing Person {name} has been deleted by {current_user.username} successfully.",
        )
        return HTTPResponse.success(message=f"Deleted Missing Person #{id}")
    return HTTPResponse.error("Error deleting Missing Person", status=500)
