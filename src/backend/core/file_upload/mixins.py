"""Mixin to add attachment upload and access control to a viewset."""

import logging
import uuid
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename

from botocore.exceptions import ClientError
from lasuite.malware_detection import malware_detection
from rest_framework import decorators, exceptions, status
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.throttling import UserRateThrottle

from . import enums, utils
from .exceptions import HolderDoesNotExist
from .serializers import FileUploadSerializer

logger = logging.getLogger(__name__)


class AttachmentUploadThrottle(UserRateThrottle):
    """Throttle for the attachment upload endpoint."""

    scope = "attachment_upload"


class AttachmentAuthThrottle(UserRateThrottle):
    """Throttle for the attachment upload endpoint."""

    scope = "attachment_auth"


class AttachmentMixin:
    """
    Mixin to add attachment upload and access control to a viewset.

    The viewset must be based on `GenericViewSet` and define the following methods because
    they are highly model-specific and depends on how attachments are stored (a key in
    an ArrayField, a related model, etc.):
    - `malware_detection_kwargs`
    - `store_attachment`
    - `get_holder_from_key`
    - `_check_attachment_present`
    """

    def malware_detection_kwargs(self, holder) -> dict:
        """
        Extra arguments to pass to the malware detection backend.
        The result will be passed to the `analyse_file` callback method of the backend.

        Should return a dictionary like `{"document_id": str(holder.pk)}`
        """
        raise NotImplementedError()

    def store_attachment(self, holder, key, serializer) -> None:
        """
        Store the attachment key and save it: this provides the permission to access it.

        Used by the attachment_upload endpoint.
        Can be like:

        ```
        holder.attachments.add(key)
        holder.save()
        ```
        """
        raise NotImplementedError()

    def get_holder_from_key(self, key):
        """
        Get the holder object from the attachment key, to check the user has
        access to the attachment holder (so they have access to the attachment).

        Used by the media_auth endpoint.
        Can be like:

        ```
        return self.queryset.get(attachments__contains=[key])
        ```
        """
        raise NotImplementedError()

    def _check_attachment_present(self, holder, key) -> bool:
        """
        Check if the attachment key is present in the holder's attachments.

        Used by the media_check endpoint.
        Can be like:

        ```
        return key in holder.attachments
        ```
        """
        raise NotImplementedError()

    def get_object_key_base(self, holder):
        """Key base of the location where the attachment is stored in object storage."""
        return str(holder.pk)

    def get_media_check_url(self, holder):
        """Get the URL to check the status of an attachment."""
        return reverse(
            f"{self.basename}-media-check",
            kwargs={"pk": holder.pk},
        )

    def check_attachment_holder_permission(self, user, key):
        """
        Check if the user has permission to access the holder of the attachment.

        Raises PermissionDenied if the user does not have permission.
        """
        try:
            holder = self.get_holder_from_key(key)
        except HolderDoesNotExist as err:
            logger.debug("Attachment holder not found for key '%s': %s", key, err)
            # We raise PermissionDenied instead of Http404 to avoid leaking information
            # about the existence of the attachment.
            raise exceptions.PermissionDenied() from err

        self.check_object_permissions(self.request, holder)
        # for now, only the owner can access the attachment
        if holder.owner_id != user.pk:
            raise exceptions.PermissionDenied()

    @decorators.action(detail=True, methods=["post"], url_path="attachment-upload")
    @decorators.throttle_classes([AttachmentUploadThrottle])
    def attachment_upload(self, request, *args, **kwargs):
        """Upload a file related to a given document"""
        # Check permissions first
        holder = self.get_object()

        # Validate metadata in payload
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Generate a generic yet unique filename to store the image in object storage
        file_id = uuid.uuid4()
        ext = serializer.validated_data["expected_extension"]

        # Prepare metadata for storage
        extra_args = {
            "Metadata": {
                "owner": str(request.user.id),
                "status": enums.AttachmentStatus.ANALYZING,
            },
            "ContentType": serializer.validated_data["content_type"],
        }
        file_unsafe = ""
        if serializer.validated_data["is_unsafe"]:
            extra_args["Metadata"]["is_unsafe"] = "true"
            file_unsafe = "-unsafe"

        holder_key_base = self.get_object_key_base(holder)
        key = f"{holder_key_base}/{enums.ATTACHMENTS_FOLDER:s}/{file_id!s}{file_unsafe}.{ext:s}"

        raw_name = serializer.validated_data["file_name"]
        # Strip CR/LF and normalize to a filesystem-safe basename
        safe_name = get_valid_filename(raw_name.replace("\r", "").replace("\n", "")) or "file"
        ascii_name = safe_name.encode("ascii", "ignore").decode("ascii") or "file"
        # RFC 5987 filename* for non-ASCII
        disp_filename = f'filename="{ascii_name}"'
        disp_filename_star = f"filename*=UTF-8''{quote(safe_name)}"
        if (
            not serializer.validated_data["content_type"].startswith("image/")
            or serializer.validated_data["is_unsafe"]
        ):
            extra_args.update(
                {"ContentDisposition": f"attachment; {disp_filename}; {disp_filename_star}"}
            )
        else:
            extra_args.update(
                {"ContentDisposition": f"inline; {disp_filename}; {disp_filename_star}"}
            )

        file = serializer.validated_data["file"]
        default_storage.connection.meta.client.upload_fileobj(
            file, default_storage.bucket_name, key, ExtraArgs=extra_args
        )

        self.store_attachment(holder, key, serializer)

        malware_detection.analyse_file(key, **self.malware_detection_kwargs(holder))

        url = self.get_media_check_url(holder)
        parameters = urlencode({"key": key})

        return Response(
            {
                "file": f"{url:s}?{parameters:s}",
            },
            status=status.HTTP_201_CREATED,
        )

    @decorators.action(detail=False, methods=["get"], url_path="media-auth")
    @decorators.throttle_classes([AttachmentAuthThrottle])
    def media_auth(self, request, *args, **kwargs):
        """
        This view is used by an Nginx subrequest to control access to a document's
        attachment file.

        When we let the request go through, we compute authorization headers that will be added to
        the request going through thanks to the nginx.ingress.kubernetes.io/auth-response-headers
        annotation. The request will then be proxied to the object storage backend who will
        respond with the file after checking the signature included in headers.
        """
        parsed_url = utils.auth_get_original_url(request)
        url_params = utils.auth_get_url_params(enums.MEDIA_STORAGE_URL_PATTERN, parsed_url.path)

        user = request.user
        key = f"{url_params['pk']:s}/{url_params['attachment']:s}"

        # Look for a holder to which the user has access and that includes this attachment
        # Might raise PermissionDenied
        self.check_attachment_holder_permission(user, key)

        # Check if the attachment is ready
        s3_client = default_storage.connection.meta.client
        bucket_name = default_storage.bucket_name
        try:
            head_resp = s3_client.head_object(Bucket=bucket_name, Key=key)
        except ClientError as err:
            raise exceptions.PermissionDenied() from err

        metadata = head_resp.get("Metadata", {})
        # In order to be compatible with existing upload without `status` metadata,
        # we consider them as ready.
        if metadata.get("status", enums.AttachmentStatus.READY) != enums.AttachmentStatus.READY:
            raise exceptions.PermissionDenied()

        # Generate S3 authorization headers using the extracted URL parameters
        request = utils.generate_s3_authorization_headers(key)

        return Response("authorized", headers=request.headers, status=status.HTTP_200_OK)

    @decorators.action(detail=True, methods=["get"], url_path="media-check")
    def media_check(self, request, *args, **kwargs):
        """
        Check if the media is ready to be served.
        """
        holder = self.get_object()

        key = request.query_params.get("key")
        if not key:
            return Response(
                {"detail": "Missing 'key' query parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not self._check_attachment_present(holder, key):
            return Response(
                {"detail": "Attachment missing"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Check if the attachment is ready
        s3_client = default_storage.connection.meta.client
        bucket_name = default_storage.bucket_name
        try:
            head_resp = s3_client.head_object(Bucket=bucket_name, Key=key)
        except ClientError as err:
            logger.error("Client Error fetching file %s metadata: %s", key, err)
            return Response(
                {"detail": "Media not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        metadata = head_resp.get("Metadata", {})

        body = {
            "status": metadata.get("status", enums.AttachmentStatus.ANALYZING),
        }
        if metadata.get("status") == enums.AttachmentStatus.READY:
            body = {
                "status": enums.AttachmentStatus.READY,
                "file": f"{settings.MEDIA_URL:s}{key:s}",
            }

        return Response(body, status=status.HTTP_200_OK)
