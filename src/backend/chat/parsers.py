"""Request parsers for the chat endpoints."""

import io

from django.conf import settings

from rest_framework import exceptions, parsers, status


class RequestBodyTooLarge(exceptions.APIException):
    """The request body is over the size the endpoint accepts."""

    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_detail = "Request body too large."
    default_code = "request_body_too_large"


class SizeLimitedJSONParser(parsers.JSONParser):
    """JSON parser that refuses bodies over `CHAT_REQUEST_MAX_BODY_SIZE` bytes.

    DRF parses straight from the request stream, which skips Django's
    `DATA_UPLOAD_MAX_MEMORY_SIZE` check. Reading at most one byte past the
    limit bounds memory whatever `Content-Length` says, chunked bodies included.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        limit = settings.CHAT_REQUEST_MAX_BODY_SIZE
        body = stream.read(limit + 1)
        if len(body) > limit:
            raise RequestBodyTooLarge()
        return super().parse(io.BytesIO(body), media_type, parser_context)
