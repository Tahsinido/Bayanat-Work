"""Admin-approved, code-verified downloads of original media files.

Viewing is deliberately untouched. Thumbnails, video playback and PDF preview
still stream from the media routes to anyone who may see the record -- gating
those would only blind the people doing the work. What is gated here is taking
a *copy* of the original file off the system, which is the action worth a second
pair of eyes.

The flow is: a user requests one file with a stated reason, an admin approves
and is shown a one-time code, the code reaches the user out of band, and the
file is released only when it comes back. Each approval covers one file for one
person and is spent on first use.
"""

from __future__ import annotations

import io
import os

from flask import Response, request, send_from_directory
from flask.templating import render_template
from flask_security.decorators import auth_required, current_user, roles_required
from werkzeug.utils import safe_join

from enferno.admin.constants import Constants
from enferno.admin.models import Activity, DownloadRequest, Media
from enferno.admin.models.Notification import Notification
from enferno.extensions import db
from enferno.utils.http_response import HTTPResponse
from enferno.utils.logging_utils import get_logger
import enferno.utils.typing as t
from . import admin, PER_PAGE

logger = get_logger()


def _media_or_none(media_id):
    """The media row, if the current user is allowed to know it exists."""
    media = db.session.get(Media, media_id)
    if media is None:
        return None
    if not current_user.has_role("Admin") and not current_user.can_access_media:
        return None
    if not current_user.can_access(media):
        return None
    return media


def _local_file_missing(media: Media) -> bool:
    """True when local storage is in use but the file is not on disk."""
    from flask import current_app

    if not current_app.config["FILESYSTEM_LOCAL"]:
        return False
    path = safe_join(str(Media.media_dir), media.media_file or "")
    return not path or not os.path.exists(path)


def _serve(media: Media) -> Response:
    """Hand over the file itself.

    Local storage streams from disk; S3 hands back a short-lived signed URL for
    the browser to follow, since the file never passes through this process.

    Images and PDFs are stamped with the organisation name on the way out. The
    stored file is left untouched, so its hash still attests to what was
    collected -- only the copy that leaves carries the mark.
    """
    from flask import current_app, send_file

    from enferno.utils.watermark import can_stamp, stamp

    if current_app.config["FILESYSTEM_LOCAL"]:
        # safe_join rejects traversal in the stored filename before it reaches
        # the filesystem.
        path = safe_join(str(Media.media_dir), media.media_file)
        if not path:
            return HTTPResponse.error("Invalid file", status=400)

        watermark = current_app.config.get("MEDIA_WATERMARK_TEXT")
        if watermark and can_stamp(media.media_file):
            with open(path, "rb") as f:
                data = stamp(f.read(), media.media_file, watermark)
            return send_file(
                io.BytesIO(data),
                as_attachment=True,
                download_name=media.media_file,
            )

        return send_from_directory(
            "media", media.media_file, as_attachment=True, download_name=media.media_file
        )

    import boto3
    from botocore.config import Config as BotoConfig

    s3 = boto3.client(
        "s3",
        config=BotoConfig(signature_version="s3v4"),
        aws_access_key_id=current_app.config["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["AWS_SECRET_ACCESS_KEY"],
        region_name=current_app.config["AWS_REGION"],
    )
    url = s3.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": current_app.config["S3_BUCKET"],
            "Key": media.media_file,
            "ResponseContentDisposition": f'attachment; filename="{media.media_file}"',
        },
        ExpiresIn=300,
    )
    return HTTPResponse.success(data={"url": url})


@admin.route("/download-requests/")
@roles_required("Admin")
def download_requests_dashboard() -> str:
    """The approval queue for pending media download requests."""
    return render_template("admin/download-requests.html")


@admin.post("/api/download-requests/")
@auth_required("session")
def api_download_request_create() -> Response:
    """
    Ask an admin to release one original media file.

    Returns:
        - the created request, or the existing pending/approved one so a user
          cannot stack duplicate requests for the same file.
    """
    payload = request.json or {}
    media_id = payload.get("media_id")
    reason = (payload.get("reason") or "").strip()

    if not media_id:
        return HTTPResponse.error("A media file is required", status=400)

    media = _media_or_none(media_id)
    if media is None:
        # Same answer whether the file is missing or merely out of reach: the
        # existence of a restricted file is itself worth not confirming.
        return HTTPResponse.not_found("File not found")

    if not reason:
        return HTTPResponse.error("Please say why you need this file", status=400)

    existing = (
        DownloadRequest.query.filter(
            DownloadRequest.media_id == media.id,
            DownloadRequest.requester_id == current_user.id,
            DownloadRequest.status.in_(
                [DownloadRequest.STATUS_PENDING, DownloadRequest.STATUS_APPROVED]
            ),
        )
        .order_by(DownloadRequest.id.desc())
        .first()
    )
    if existing and not existing.expired:
        return HTTPResponse.success(
            data={"item": existing.to_dict()},
            message="You already have a request open for this file.",
        )

    download_request = DownloadRequest(
        media_id=media.id,
        requester_id=current_user.id,
        reason=reason,
        status=DownloadRequest.STATUS_PENDING,
    )
    db.session.add(download_request)
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_REQUEST_DOWNLOAD,
        Activity.STATUS_SUCCESS,
        download_request.to_mini(),
        "download_request",
    )
    Notification.send_admin_notification_for_event(
        Constants.NotificationEvent.NEW_DOWNLOAD_REQUEST,
        "New Download Request",
        f"{current_user.username} requested the file "
        f"'{media.title or media.media_file}' (request {download_request.id}).",
    )

    return HTTPResponse.created(
        data={"item": download_request.to_dict()},
        message="Request sent. An admin has to approve it before the file is released.",
    )


@admin.post("/api/download-requests/list")
@auth_required("session")
def api_download_requests() -> Response:
    """
    Paginated download requests: everyone's for an admin, your own otherwise.

    Returns:
        - json feed of requests.
    """
    payload = request.json or {}
    page = payload.get("page", 1)
    per_page = payload.get("per_page", PER_PAGE)
    status = payload.get("status")

    query = DownloadRequest.query
    if not current_user.has_role("Admin"):
        query = query.filter(DownloadRequest.requester_id == current_user.id)
    if status:
        query = query.filter(DownloadRequest.status == status)

    result = query.order_by(DownloadRequest.id.desc()).paginate(
        page=page, per_page=per_page, count=True
    )

    return HTTPResponse.success(
        data={
            "items": [item.to_dict() for item in result.items],
            "perPage": per_page,
            "total": result.total,
        }
    )


@admin.put("/api/download-requests/status")
@roles_required("Admin")
def api_download_request_status() -> Response:
    """
    Approve or reject a download request.

    On approval the one-time code is returned **once**, for the admin to pass to
    the requester out of band. It is stored only as a hash, so it cannot be
    retrieved again -- a lost code means approving a fresh request.

    Returns:
        - the code on approval, or a plain confirmation on rejection.
    """
    payload = request.json or {}
    action = payload.get("action")
    request_id = payload.get("requestId")

    if action not in ("approve", "reject"):
        return HTTPResponse.error("Please check request action", status=417)
    if not request_id:
        return HTTPResponse.error("Invalid download request id", status=417)

    download_request = db.session.get(DownloadRequest, request_id)
    if not download_request:
        return HTTPResponse.not_found("Download request does not exist")
    if download_request.status != DownloadRequest.STATUS_PENDING:
        return HTTPResponse.error(
            f"This request has already been {download_request.status.lower()}.", status=409
        )

    if action == "approve":
        code = download_request.approve(current_user)
        db.session.commit()

        Activity.create(
            current_user,
            Activity.ACTION_APPROVE_DOWNLOAD,
            Activity.STATUS_SUCCESS,
            download_request.to_mini(),
            "download_request",
        )
        Notification.send_admin_notification_for_event(
            Constants.NotificationEvent.DOWNLOAD_APPROVED,
            "Download Request Approved",
            f"Request {download_request.id} was approved by {current_user.username}.",
        )

        return HTTPResponse.success(
            data={"item": download_request.to_dict(), "code": code},
            message="Approved. Give this code to the requester directly -- "
            "it is shown once and cannot be recovered.",
        )

    download_request.reject(current_user)
    db.session.commit()
    Activity.create(
        current_user,
        Activity.ACTION_REJECT_DOWNLOAD,
        Activity.STATUS_SUCCESS,
        download_request.to_mini(),
        "download_request",
    )
    return HTTPResponse.success(
        data={"item": download_request.to_dict()}, message="Download request rejected."
    )


@admin.post("/api/download-requests/<int:id>/download")
@auth_required("session")
def api_download_request_download(id: t.id) -> Response:
    """
    Exchange the verification code for the file.

    The request is spent on success, so an approval releases the file once.
    Every wrong code is counted and the request locks after the configured
    number of tries.

    Returns:
        - the file (or a signed URL on S3), or the reason it was refused.
    """
    payload = request.json or {}
    code = payload.get("code")

    download_request = db.session.get(DownloadRequest, id)
    if not download_request:
        return HTTPResponse.not_found("Download request not found")

    # The approval belongs to one person. An admin does not inherit it.
    if download_request.requester_id != current_user.id:
        Activity.create(
            current_user,
            Activity.ACTION_DOWNLOAD,
            Activity.STATUS_DENIED,
            download_request.to_mini(),
            "download_request",
            details="Attempt to use another user's download approval.",
        )
        return HTTPResponse.forbidden("Forbidden")

    if download_request.status == DownloadRequest.STATUS_FULFILLED:
        return HTTPResponse.error("This download has already been used.", status=409)
    if download_request.status != DownloadRequest.STATUS_APPROVED:
        return HTTPResponse.error("This request has not been approved.", status=403)
    if download_request.expired:
        return HTTPResponse.error("This approval has expired.", status=410)
    if download_request.code_expired:
        return HTTPResponse.error("The code has expired. Ask for a new approval.", status=410)
    if download_request.locked:
        return HTTPResponse.error("Too many incorrect codes. Ask for a new approval.", status=429)
    if not code:
        return HTTPResponse.error("Enter the verification code", status=400)

    ok = download_request.verify(code)
    # Persist the attempt count whichever way it went, so a wrong code is never
    # free to retry.
    db.session.commit()

    if not ok:
        Activity.create(
            current_user,
            Activity.ACTION_DOWNLOAD,
            Activity.STATUS_DENIED,
            download_request.to_mini(),
            "download_request",
            details="Incorrect download verification code.",
        )
        return HTTPResponse.error(
            f"Incorrect code. {download_request.to_dict()['attempts_left']} attempts left.",
            status=403,
        )

    media = db.session.get(Media, download_request.media_id)
    if media is None:
        return HTTPResponse.not_found("File not found")

    if _local_file_missing(media):
        return HTTPResponse.not_found("File not found")

    download_request.fulfill()
    db.session.commit()

    Activity.create(
        current_user,
        Activity.ACTION_DOWNLOAD,
        Activity.STATUS_SUCCESS,
        download_request.to_mini(),
        "download_request",
    )
    return _serve(media)
