"""Serializers for file upload API."""

import mimetypes

from django.conf import settings

import magic
from rest_framework import serializers


class FileUploadSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Receive file upload requests."""

    file = serializers.FileField()

    def validate_file(self, file):
        """Add file size and type constraints as defined in settings."""
        # Validate file size
        if file.size > settings.ATTACHMENT_MAX_SIZE:
            max_size = settings.ATTACHMENT_MAX_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                f"File size exceeds the maximum limit of {max_size:d} MB."
            )

        extension = file.name.rpartition(".")[-1] if "." in file.name else None

        # Read the first few bytes to determine the MIME type accurately
        mime = magic.Magic(mime=True)
        magic_mime_type = mime.from_buffer(file.read(1024))
        file.seek(0)  # Reset file pointer to the beginning after reading
        self.context["is_unsafe"] = False
        if settings.ATTACHMENT_CHECK_UNSAFE_MIME_TYPES_ENABLED:
            self.context["is_unsafe"] = magic_mime_type in settings.ATTACHMENT_UNSAFE_MIME_TYPES

            extension_mime_type, _ = mimetypes.guess_type(file.name)

            # Try guessing a coherent extension from the mimetype
            if extension_mime_type != magic_mime_type:
                self.context["is_unsafe"] = True

        guessed_ext = mimetypes.guess_extension(magic_mime_type)
        # Missing extensions or extensions longer than 5 characters (it's as long as an extension
        # can be) are replaced by the extension we eventually guessed from mimetype.
        if (extension is None or len(extension) > 5) and guessed_ext:
            extension = guessed_ext[1:]

        if extension is None:
            raise serializers.ValidationError("Could not determine file extension.")

        self.context["expected_extension"] = extension
        self.context["content_type"] = magic_mime_type
        self.context["file_name"] = file.name

        return file

    def validate(self, attrs):
        """Override validate to add the computed extension to validated_data."""
        attrs["expected_extension"] = self.context["expected_extension"]
        attrs["is_unsafe"] = self.context["is_unsafe"]
        attrs["content_type"] = self.context["content_type"]
        attrs["file_name"] = self.context["file_name"]
        return attrs
