"""Tests for file upload utilities."""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from django.utils import timezone

from freezegun import freeze_time

from core.file_upload.utils import generate_retrieve_policy, generate_upload_policy


@freeze_time()
def test_generate_upload_policy():
    """
    Test the generate_upload_policy function.
    """

    key = f"test/{uuid4()!s}/key.txt"
    policy = generate_upload_policy(key)

    policy_parsed = urlparse(policy)

    assert policy_parsed.scheme == "http"
    assert policy_parsed.netloc == "localhost:9000"
    assert policy_parsed.path == f"/conversations-media-storage/{key}"

    query_params = parse_qs(policy_parsed.query)

    assert query_params.pop("X-Amz-Algorithm") == ["AWS4-HMAC-SHA256"]
    assert query_params.pop("X-Amz-Credential") == [
        f"conversations/{timezone.now().strftime('%Y%m%d')}/us-east-1/s3/aws4_request"
    ]
    assert query_params.pop("X-Amz-Date") == [timezone.now().strftime("%Y%m%dT%H%M%SZ")]
    assert query_params.pop("X-Amz-Expires") == ["60"]
    assert query_params.pop("X-Amz-SignedHeaders") == ["host;x-amz-acl"]
    assert query_params.pop("X-Amz-Signature") is not None

    assert len(query_params) == 0


@freeze_time()
def test_generate_upload_policy_key_s3_domain_replace(settings):
    """
    Test the generate_upload_policy function with S3_DOMAIN_REPLACE setting.
    """

    settings.AWS_S3_DOMAIN_REPLACE = "https://example.com:1234"
    key = f"test/{uuid4()!s}/key.txt"
    policy = generate_upload_policy(key)

    policy_parsed = urlparse(policy)

    assert policy_parsed.scheme == "https"
    assert policy_parsed.netloc == "example.com:1234"
    assert policy_parsed.path == f"/conversations-media-storage/{key}"

    query_params = parse_qs(policy_parsed.query)

    assert query_params.pop("X-Amz-Algorithm") == ["AWS4-HMAC-SHA256"]
    assert query_params.pop("X-Amz-Credential") == [
        f"conversations/{timezone.now().strftime('%Y%m%d')}/us-east-1/s3/aws4_request"
    ]
    assert query_params.pop("X-Amz-Date") == [timezone.now().strftime("%Y%m%dT%H%M%SZ")]
    assert query_params.pop("X-Amz-Expires") == ["60"]
    assert query_params.pop("X-Amz-SignedHeaders") == ["host;x-amz-acl"]
    assert query_params.pop("X-Amz-Signature") is not None

    assert len(query_params) == 0


@freeze_time()
def test_generate_retrieve_policy():
    """
    Test the generate_retrieve_policy function.
    """
    key = f"test/{uuid4()!s}/key.txt"
    policy = generate_retrieve_policy(key)

    policy_parsed = urlparse(policy)

    assert policy_parsed.scheme == "http"
    assert policy_parsed.netloc == "localhost:9000"
    assert policy_parsed.path == f"/conversations-media-storage/{key}"

    query_params = parse_qs(policy_parsed.query)

    assert query_params.pop("X-Amz-Algorithm") == ["AWS4-HMAC-SHA256"]
    assert query_params.pop("X-Amz-Credential") == [
        f"conversations/{timezone.now().strftime('%Y%m%d')}/us-east-1/s3/aws4_request"
    ]
    assert query_params.pop("X-Amz-Date") == [timezone.now().strftime("%Y%m%dT%H%M%SZ")]
    assert query_params.pop("X-Amz-Expires") == ["180"]
    assert query_params.pop("X-Amz-SignedHeaders") == ["host"]
    assert query_params.pop("X-Amz-Signature") is not None

    assert len(query_params) == 0


@freeze_time()
def test_generate_retrieve_policy_s3_domain_replace(settings):
    """
    Test the generate_retrieve_policy function with S3_DOMAIN_REPLACE setting.
    """

    settings.AWS_S3_DOMAIN_REPLACE = "https://example.com:1234"
    key = f"test/{uuid4()!s}/key.txt"
    policy = generate_retrieve_policy(key)

    policy_parsed = urlparse(policy)

    assert policy_parsed.scheme == "https"
    assert policy_parsed.netloc == "example.com:1234"
    assert policy_parsed.path == f"/conversations-media-storage/{key}"

    query_params = parse_qs(policy_parsed.query)

    assert query_params.pop("X-Amz-Algorithm") == ["AWS4-HMAC-SHA256"]
    assert query_params.pop("X-Amz-Credential") == [
        f"conversations/{timezone.now().strftime('%Y%m%d')}/us-east-1/s3/aws4_request"
    ]
    assert query_params.pop("X-Amz-Date") == [timezone.now().strftime("%Y%m%dT%H%M%SZ")]
    assert query_params.pop("X-Amz-Expires") == ["180"]
    assert query_params.pop("X-Amz-SignedHeaders") == ["host"]
    assert query_params.pop("X-Amz-Signature") is not None

    assert len(query_params) == 0
