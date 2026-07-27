from __future__ import annotations

from flask import Response, request
from flask.templating import render_template
from flask_security.decorators import current_user, roles_accepted, roles_required
from sqlalchemy import desc, or_

from enferno.extensions import db
from enferno.admin.constants import Constants
from enferno.admin.models import Activity, FieldData, FieldDataSite
from enferno.utils.search_snippets import first_snippet
from enferno.admin.models.Notification import Notification
from enferno.admin.validation.models import FieldDataRequestModel
from enferno.utils.http_response import HTTPResponse
from enferno.utils.validation_utils import validate_with
import enferno.utils.typing as t
from . import admin, PER_PAGE

# Columns the list endpoint is allowed to sort by. Anything else falls back to
# id, so a crafted sort key can't reach an arbitrary attribute.
SORTABLE_COLUMNS = {
    "id",
    "name_of_site",
    "mission_date",
    "collected_data_by",
    "type_of_site",
    "no_of_site",
    "code",
    "total_photos",
    "total_videos",
    "total_interviews",
    "drone_photos",
    "drone_videos",
    "data_storage_location",
    "analysis_by",
    "analysis_date",
    "shared_with",
    "excavated_status",
    "created_by",
    "modified_last_by",
    "modified_last_date",
}


@admin.route("/field-data/")
@roles_accepted("Admin", "Mod", "DA")
def field_data() -> str:
    """
    Endpoint to render the field data backend page.

    Returns:
        - html template of the field data backend page.
    """
    return render_template("admin/field-data.html")


@admin.route("/api/field-data/")
def api_field_data() -> Response:
    """
    API Endpoint to feed json data of field data records, supports paging,
    search and sorting.

    Returns:
        - json response of field data records.
    """
    q = request.args.get("q")
    page = request.args.get("page", 1, int)
    per_page = request.args.get("per_page", PER_PAGE, int)
    sort_by = request.args.get("sort_by")
    sort_desc = request.args.get("sort_desc", "false").lower() == "true"

    query = FieldData.query.filter(FieldData.deleted == False)  # noqa: E712

    terms = [word for word in (q or "").split(" ") if word]

    if terms:
        # Every word must appear somewhere, so extra terms narrow the result
        # set instead of widening it.
        for word in terms:
            term = f"%{word}%"
            # A site match pulls in its parent location, so searching finds
            # locations by the content of any site beneath them.
            site_match = FieldData.id.in_(
                db.session.query(FieldDataSite.field_data_id).filter(
                    or_(
                        FieldDataSite.site_name.ilike(term),
                        FieldDataSite.code.ilike(term),
                        FieldDataSite.type_of_site.ilike(term),
                        FieldDataSite.description.ilike(term),
                        FieldDataSite.legal_analysis.ilike(term),
                        FieldDataSite.data_storage_location.ilike(term),
                        FieldDataSite.collected_data_by.ilike(term),
                    )
                )
            )
            query = query.filter(
                or_(
                    FieldData.name_of_site.ilike(term),
                    FieldData.code.ilike(term),
                    FieldData.type_of_site.ilike(term),
                    FieldData.collected_data_by.ilike(term),
                    FieldData.data_storage_location.ilike(term),
                    FieldData.analysis_by.ilike(term),
                    FieldData.shared_with.ilike(term),
                    FieldData.excavated_status.ilike(term),
                    FieldData.description.ilike(term),
                    FieldData.legal_analysis.ilike(term),
                    site_match,
                )
            )

    if sort_by in SORTABLE_COLUMNS:
        column = getattr(FieldData, sort_by)
        query = query.order_by(desc(column) if sort_desc else column)
    else:
        query = query.order_by(desc(FieldData.id))

    result = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for item in result.items:
        data = item.to_dict()
        if terms:
            # Show where the term was found so the row can be judged without
            # opening the record. Site text is included after the location's
            # own, and labelled with the site it came from.
            sources = [
                ("Description", item.description),
                ("Legal analysis", item.legal_analysis),
            ]
            for site in item.sites:
                label = site.site_name or "Site"
                sources.append((f"{label} - description", site.description))
                sources.append((f"{label} - legal analysis", site.legal_analysis))
            data["snippet"] = first_snippet(sources, terms)
        items.append(data)

    response = {
        "items": items,
        "perPage": per_page,
        "total": result.total,
    }
    return HTTPResponse.success(data=response)


@admin.get("/api/field-data/<int:id>")
def api_field_data_get(id: t.id) -> Response:
    """
    Endpoint to get a single field data record.

    Args:
        - id: id of the item.

    Returns:
        - json response of the field data record.
    """
    item = db.session.get(FieldData, id)
    if item is None or item.deleted:
        return HTTPResponse.not_found("Field Data not found")
    return HTTPResponse.success(data={"item": item.to_dict()})


@admin.post("/api/field-data/")
@roles_accepted("Admin", "Mod", "DA")
@validate_with(FieldDataRequestModel)
def api_field_data_create(validated_data: dict) -> Response:
    """
    Endpoint to create a field data record.

    Args:
        - validated_data: validated data from the request.

    Returns:
        - success/error string based on the operation result.
    """
    item = FieldData()
    item = item.from_json(validated_data["item"])
    item.stamp_modified_by(current_user)

    if item.save():
        Activity.create(
            current_user,
            Activity.ACTION_CREATE,
            Activity.STATUS_SUCCESS,
            item.to_mini(),
            "field_data",
        )
        return HTTPResponse.created(
            message=f"Created Field Data #{item.id}", data={"item": item.to_dict()}
        )
    return HTTPResponse.error("Save Failed", status=500)


@admin.put("/api/field-data/<int:id>")
@roles_accepted("Admin", "Mod", "DA")
@validate_with(FieldDataRequestModel)
def api_field_data_update(id: t.id, validated_data: dict) -> Response:
    """
    Endpoint to update a field data record.

    Args:
        - id: id of the item to update.
        - validated_data: validated data from the request.

    Returns:
        - success/error string based on the operation result.
    """
    item = db.session.get(FieldData, id)
    if item is None or item.deleted:
        return HTTPResponse.not_found("Field Data not found")

    item = item.from_json(validated_data["item"])
    item.stamp_modified_by(current_user)

    if item.save():
        Activity.create(
            current_user,
            Activity.ACTION_UPDATE,
            Activity.STATUS_SUCCESS,
            item.to_mini(),
            "field_data",
        )
        return HTTPResponse.success(message=f"Saved Field Data #{item.id}")
    return HTTPResponse.error("Save Failed", status=500)


@admin.delete("/api/field-data/<int:id>")
@roles_required("Admin")
def api_field_data_delete(id: t.id) -> Response:
    """
    Endpoint to delete a field data record.

    Args:
        - id: id of the item to delete.

    Returns:
        - success/error string based on the operation result.
    """
    item = db.session.get(FieldData, id)
    if item is None or item.deleted:
        return HTTPResponse.not_found("Field Data not found")

    subject = item.to_mini()
    name = item.name_of_site

    if item.delete():
        Activity.create(
            current_user,
            Activity.ACTION_DELETE,
            Activity.STATUS_SUCCESS,
            subject,
            "field_data",
        )
        Notification.send_admin_notification_for_event(
            Constants.NotificationEvent.ITEM_DELETED,
            "Field Data Deleted",
            f"Field Data {name} has been deleted by {current_user.username} successfully.",
        )
        return HTTPResponse.success(message=f"Deleted Field Data #{id}")
    return HTTPResponse.error("Error deleting Field Data", status=500)
