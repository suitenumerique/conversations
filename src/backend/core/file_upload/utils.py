"""Util to generate S3 authorization headers for object storage access control"""

import logging
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.storage import default_storage

import boto3
import botocore
from rest_framework import exceptions

logger = logging.getLogger(__name__)


def auth_get_original_url(request):
    """
    Extracts and parses the original URL from the "HTTP_X_ORIGINAL_URL" header.
    Raises PermissionDenied if the header is missing.

    The original url is passed by nginx in the "HTTP_X_ORIGINAL_URL" header.
    See corresponding ingress configuration in Helm chart and read about the
    nginx.ingress.kubernetes.io/auth-url annotation to understand how the Nginx ingress
    is configured to do this.

    Based on the original url and the logged in user, we must decide if we authorize Nginx
    to let this request go through (by returning a 200 code) or if we block it (by returning
    a 403 error). Note that we return 403 errors without any further details for security
    reasons.
    """
    # Extract the original URL from the request header
    original_url = request.META.get("HTTP_X_ORIGINAL_URL")
    if not original_url:
        logger.debug("Missing HTTP_X_ORIGINAL_URL header in subrequest")
        raise exceptions.PermissionDenied()

    logger.debug("Original url: '%s'", original_url)
    return urlparse(original_url)


def auth_get_url_params(pattern, fragment):
    """
    Extracts URL parameters from the given fragment using the specified regex pattern.
    Raises PermissionDenied if parameters cannot be extracted.
    """
    match = pattern.search(fragment)
    try:
        return match.groupdict()
    except (ValueError, AttributeError) as exc:
        logger.debug("Failed to extract parameters from subrequest URL: %s", exc)
        raise exceptions.PermissionDenied() from exc


def generate_s3_authorization_headers(key):
    """
    Generate authorization headers for an s3 object.
    These headers can be used as an alternative to signed urls with many benefits:
    - the urls of our files never expire and can be stored in our documents' content
    - we don't leak authorized urls that could be shared (file access can only be done
      with cookies)
    - access control is truly realtime
    - the object storage service does not need to be exposed on internet
    """
    url = default_storage.unsigned_connection.meta.client.generate_presigned_url(
        "get_object",
        ExpiresIn=0,
        Params={"Bucket": default_storage.bucket_name, "Key": key},
    )
    request = botocore.awsrequest.AWSRequest(method="get", url=url)

    s3_client = default_storage.connection.meta.client
    # pylint: disable=protected-access
    credentials = s3_client._request_signer._credentials  # noqa: SLF001
    frozen_credentials = credentials.get_frozen_credentials()
    region = s3_client.meta.region_name
    auth = botocore.auth.S3SigV4Auth(frozen_credentials, "s3", region)
    auth.add_auth(request)

    return request


def _get_s3_client() -> botocore.client.BaseClient:
    """
    Get the S3 client according to the settings.

    If AWS_S3_DOMAIN_REPLACE is set, create a new S3 client with the specified endpoint_url.
    Otherwise, use the existing client from the default storage.
    """
    # This settings should be used if the backend application and the frontend application
    # can't connect to the object storage with the same domain. This is the case in the
    # docker compose stack used in development. The frontend application will use localhost
    # to connect to the object storage while the backend application will use the object storage
    # service name declared in the docker compose stack.
    # This is needed because the domain name is used to compute the signature. So it can't be
    # changed dynamically by the frontend application.
    if settings.AWS_S3_DOMAIN_REPLACE:
        return boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_S3_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_DOMAIN_REPLACE,
            config=botocore.client.Config(
                region_name=settings.AWS_S3_REGION_NAME,
                signature_version=settings.AWS_S3_SIGNATURE_VERSION,
            ),
        )

    return default_storage.connection.meta.client


def generate_upload_policy(key: str):
    """
    Generate a S3 upload policy for a given key.

    Args:
        key (str): The S3 object key where the file will be uploaded.
    """

    # Get the S3 client according to the settings
    s3_client = _get_s3_client()

    # Generate the policy
    policy = s3_client.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": default_storage.bucket_name, "Key": key, "ACL": "private"},
        ExpiresIn=settings.AWS_S3_UPLOAD_POLICY_EXPIRATION,
    )

    return policy


def generate_retrieve_policy(key: str):
    """
    Generate a S3 retrieve policy for a given item.

    Args:
        key (str): The S3 object key where the file is stored.
    """

    # Get the S3 client according to the settings
    s3_client = _get_s3_client()

    # Generate the policy
    policy = s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": default_storage.bucket_name, "Key": key},
        ExpiresIn=settings.AWS_S3_RETRIEVE_POLICY_EXPIRATION,
    )

    return policy
