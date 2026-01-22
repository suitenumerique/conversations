"""Common test fixtures for chat views tests."""

from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def mock_process_request():
    """
    Mock process_request to bypass OIDC authentication in tests.
    """
    with mock.patch(
        "lasuite.oidc_login.decorators.RefreshOIDCAccessToken.process_request"
    ) as mocked_process_request:
        mocked_process_request.return_value = None
        yield mocked_process_request
