"""Django configuration mixin for OIDC authorization code flow and userinfo mapping."""

from configurations import values


class OIDCSettings:
    """OIDC authorization code flow and userinfo mapping."""

    # OIDC - Authorization Code Flow
    OIDC_CREATE_USER = values.BooleanValue(
        default=True,
        environ_name="OIDC_CREATE_USER",
        environ_prefix=None,
    )
    OIDC_RP_SIGN_ALGO = values.Value("RS256", environ_name="OIDC_RP_SIGN_ALGO", environ_prefix=None)
    OIDC_RP_CLIENT_ID = values.Value(
        "conversations", environ_name="OIDC_RP_CLIENT_ID", environ_prefix=None
    )
    OIDC_RP_CLIENT_SECRET = values.Value(
        None,
        environ_name="OIDC_RP_CLIENT_SECRET",
        environ_prefix=None,
    )
    OIDC_OP_URL = values.Value(None, environ_name="OIDC_OP_URL", environ_prefix=None)
    OIDC_OP_JWKS_ENDPOINT = values.Value(environ_name="OIDC_OP_JWKS_ENDPOINT", environ_prefix=None)
    OIDC_OP_AUTHORIZATION_ENDPOINT = values.Value(
        environ_name="OIDC_OP_AUTHORIZATION_ENDPOINT", environ_prefix=None
    )
    OIDC_OP_TOKEN_ENDPOINT = values.Value(
        None, environ_name="OIDC_OP_TOKEN_ENDPOINT", environ_prefix=None
    )
    OIDC_OP_USER_ENDPOINT = values.Value(
        None, environ_name="OIDC_OP_USER_ENDPOINT", environ_prefix=None
    )
    OIDC_OP_LOGOUT_ENDPOINT = values.Value(
        None, environ_name="OIDC_OP_LOGOUT_ENDPOINT", environ_prefix=None
    )
    OIDC_AUTHENTICATE_CLASS = "lasuite.oidc_login.views.OIDCAuthenticationRequestView"
    OIDC_CALLBACK_CLASS = "core.authentication.views.OIDCAuthenticationCallbackView"
    OIDC_AUTH_REQUEST_EXTRA_PARAMS = values.DictValue(
        {}, environ_name="OIDC_AUTH_REQUEST_EXTRA_PARAMS", environ_prefix=None
    )
    OIDC_RP_SCOPES = values.Value(
        "openid email", environ_name="OIDC_RP_SCOPES", environ_prefix=None
    )
    # Restrict login and account creation to users exposing one of these roles
    # in their OIDC "roles" claim. Empty (default) disables the restriction.
    OIDC_ALLOWED_ROLES = values.ListValue(
        [], environ_name="OIDC_ALLOWED_ROLES", environ_prefix=None
    )
    LOGIN_REDIRECT_URL = values.Value(None, environ_name="LOGIN_REDIRECT_URL", environ_prefix=None)
    LOGIN_REDIRECT_URL_FAILURE = values.Value(
        None, environ_name="LOGIN_REDIRECT_URL_FAILURE", environ_prefix=None
    )
    LOGOUT_REDIRECT_URL = values.Value(
        None, environ_name="LOGOUT_REDIRECT_URL", environ_prefix=None
    )
    OIDC_USE_NONCE = values.BooleanValue(
        default=True, environ_name="OIDC_USE_NONCE", environ_prefix=None
    )
    OIDC_REDIRECT_REQUIRE_HTTPS = values.BooleanValue(
        default=False, environ_name="OIDC_REDIRECT_REQUIRE_HTTPS", environ_prefix=None
    )
    OIDC_REDIRECT_ALLOWED_HOSTS = values.ListValue(
        default=[], environ_name="OIDC_REDIRECT_ALLOWED_HOSTS", environ_prefix=None
    )
    OIDC_STORE_ID_TOKEN = values.BooleanValue(
        default=True, environ_name="OIDC_STORE_ID_TOKEN", environ_prefix=None
    )
    OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION = values.BooleanValue(
        default=True,
        environ_name="OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION",
        environ_prefix=None,
    )
    OIDC_USE_PKCE = values.BooleanValue(
        default=False, environ_name="OIDC_USE_PKCE", environ_prefix=None
    )
    OIDC_PKCE_CODE_CHALLENGE_METHOD = values.Value(
        default="S256",
        environ_name="OIDC_PKCE_CODE_CHALLENGE_METHOD",
        environ_prefix=None,
    )
    OIDC_PKCE_CODE_VERIFIER_SIZE = values.IntegerValue(
        default=64, environ_name="OIDC_PKCE_CODE_VERIFIER_SIZE", environ_prefix=None
    )
    OIDC_STORE_ACCESS_TOKEN = values.BooleanValue(
        default=False, environ_name="OIDC_STORE_ACCESS_TOKEN", environ_prefix=None
    )
    OIDC_STORE_REFRESH_TOKEN = values.BooleanValue(
        default=False, environ_name="OIDC_STORE_REFRESH_TOKEN", environ_prefix=None
    )
    OIDC_STORE_REFRESH_TOKEN_KEY = values.Value(
        default=None,
        environ_name="OIDC_STORE_REFRESH_TOKEN_KEY",
        environ_prefix=None,
    )

    # WARNING: Enabling this setting allows multiple user accounts to share the same email
    # address. This may cause security issues and is not recommended for production use when
    # email is activated as fallback for identification (see previous setting).
    OIDC_ALLOW_DUPLICATE_EMAILS = values.BooleanValue(
        default=False,
        environ_name="OIDC_ALLOW_DUPLICATE_EMAILS",
        environ_prefix=None,
    )

    USER_OIDC_ESSENTIAL_CLAIMS = values.ListValue(
        default=[], environ_name="USER_OIDC_ESSENTIAL_CLAIMS", environ_prefix=None
    )

    OIDC_USERINFO_FULLNAME_FIELDS = values.ListValue(
        default=["first_name", "last_name"],
        environ_name="OIDC_USERINFO_FULLNAME_FIELDS",
        environ_prefix=None,
    )
    OIDC_USERINFO_SHORTNAME_FIELD = values.Value(
        default="first_name",
        environ_name="OIDC_USERINFO_SHORTNAME_FIELD",
        environ_prefix=None,
    )

    ALLOW_LOGOUT_GET_METHOD = values.BooleanValue(
        default=True, environ_name="ALLOW_LOGOUT_GET_METHOD", environ_prefix=None
    )
