# Conversations variables

Here we describe all environment variables that can be set for the conversations application.

## conversations-backend container

These are the environment variables you can set for the `conversations-backend` container.

| Option                                          | Description                                                                                                                       | default                                                 |
|-------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------|
| DJANGO_ALLOWED_HOSTS                            | allowed hosts                                                                                                                     | []                                                      |
| DJANGO_SECRET_KEY                               | secret key                                                                                                                        |                                                         |
| DB_ENGINE                                       | engine to use for database connections                                                                                            | django.db.backends.postgresql_psycopg2                  |
| DB_NAME                                         | name of the database                                                                                                              | conversations                                           |
| DB_USER                                         | user to authenticate with                                                                                                         | dinum                                                   |
| DB_PASSWORD                                     | password to authenticate with                                                                                                     | pass                                                    |
| DB_HOST                                         | host of the database                                                                                                              | localhost                                               |
| DB_PORT                                         | port of the database                                                                                                              | 5432                                                    |
| MEDIA_BASE_URL                                  |                                                                                                                                   |                                                         |
| STORAGES_STATICFILES_BACKEND                    |                                                                                                                                   | whitenoise.storage.CompressedManifestStaticFilesStorage |
| AWS_S3_ENDPOINT_URL                             | S3 endpoint                                                                                                                       |                                                         |
| AWS_S3_ACCESS_KEY_ID                            | access id for s3 endpoint                                                                                                         |                                                         |
| AWS_S3_SECRET_ACCESS_KEY                        | access key for s3 endpoint                                                                                                        |                                                         |
| AWS_S3_REGION_NAME                              | region name for s3 endpoint                                                                                                       |                                                         |
| AWS_STORAGE_BUCKET_NAME                         | bucket name for s3 endpoint                                                                                                       | conversations-media-storage                             |
| ATTACHMENT_MAX_SIZE                             | maximum size of document in bytes                                                                                                 | 10485760                                                |
| PROJECT_FILES_MAX_COUNT                         | max non-image attachments per project (companion markdown rows excluded). Bounds per-turn system-prompt token cost.               | 10                                                      |
| PROJECT_IMAGES_MAX_COUNT                        | max image attachments per project. Every image is pinned to every conversation turn; bounds vision-token cost and provider caps.   | 3                                                       |
| LANGUAGE_CODE                                   | default language                                                                                                                  | en-us                                                   |
| SPECTACULAR_SETTINGS_ENABLE_DJANGO_DEPLOY_CHECK |                                                                                                                                   | false                                                   |
| DJANGO_EMAIL_BACKEND                            | email backend library                                                                                                             | django.core.mail.backends.smtp.EmailBackend             |
| DJANGO_EMAIL_BRAND_NAME                         | brand name for email                                                                                                              |                                                         |
| DJANGO_EMAIL_HOST                               | host name of email                                                                                                                |                                                         |
| DJANGO_EMAIL_HOST_USER                          | user to authenticate with on the email host                                                                                       |                                                         |
| DJANGO_EMAIL_HOST_PASSWORD                      | password to authenticate with on the email host                                                                                   |                                                         |
| DJANGO_EMAIL_LOGO_IMG                           | logo for the email                                                                                                                |                                                         |
| DJANGO_EMAIL_PORT                               | port used to connect to email host                                                                                                |                                                         |
| DJANGO_EMAIL_USE_TLS                            | use tls for email host connection                                                                                                 | false                                                   |
| DJANGO_EMAIL_USE_SSL                            | use sstl for email host connection                                                                                                | false                                                   |
| DJANGO_EMAIL_FROM                               | email address used as sender                                                                                                      | from@example.com                                        |
| DJANGO_CORS_ALLOW_ALL_ORIGINS                   | allow all CORS origins                                                                                                            | false                                                   |
| DJANGO_CORS_ALLOWED_ORIGINS                     | list of origins allowed for CORS                                                                                                  | []                                                      |
| DJANGO_CORS_ALLOWED_ORIGIN_REGEXES              | list of origins allowed for CORS using regulair expressions                                                                       | []                                                      |
| SENTRY_DSN                                      | sentry host                                                                                                                       |                                                         |
| FRONTEND_CSS_URL                                | To add a external css file to the app                                                                                             |                                                         |
| FRONTEND_CONTACT_EMAIL                          | Email address shown in the help menu "Contact us" item (used to build a mailto link)                                              |                                                         |
| FRONTEND_DOCUMENTATION_URL                      | Documentation URL opened from the help menu "Documentation" item                                                                  |                                                         |
| FRONTEND_HOMEPAGE_FEATURE_ENABLED               | frontend feature flag to display the homepage                                                                                     | false                                                   |
| FRONTEND_SILENT_LOGIN_ENABLED                   | frontend fsilent login enabled                                                                                                    | false                                                   |
| FRONTEND_THEME                                  | frontend theme to use                                                                                                             |                                                         |
| POSTHOG_KEY                                     | posthog key for analytics                                                                                                         |                                                         |
| CELERY_BROKER_URL                               | celery broker url                                                                                                                 | redis://redis:6379/0                                    |
| CELERY_BROKER_TRANSPORT_OPTIONS                 | celery broker transport options                                                                                                   | {}                                                      |
| CELERY_TASK_ROUTES                              | maps task names to queues so heavy and fast tasks can run on separate workers ({} = default queue)                                | {}                                                      |
| CELERY_TASK_SOFT_TIME_LIMIT                     | celery soft per-task time limit in seconds (raises SoftTimeLimitExceeded; recorded as a failed parse)                             | 180                                                     |
| CELERY_TASK_TIME_LIMIT                          | celery hard per-task time limit in seconds (SIGKILLs the worker child)                                                            | 300                                                     |
| SESSION_COOKIE_AGE                              | duration of the cookie session                                                                                                    | 60*60*12                                                |
| OIDC_CREATE_USER                                | create used on OIDC                                                                                                               | false                                                   |
| OIDC_RP_SIGN_ALGO                               | verification algorithm used OIDC tokens                                                                                           | RS256                                                   |
| OIDC_RP_CLIENT_ID                               | client id used for OIDC                                                                                                           | conversations                                           |
| OIDC_RP_CLIENT_SECRET                           | client secret used for OIDC                                                                                                       |                                                         |
| OIDC_OP_JWKS_ENDPOINT                           | JWKS endpoint for OIDC                                                                                                            |                                                         |
| OIDC_OP_AUTHORIZATION_ENDPOINT                  | Authorization endpoint for OIDC                                                                                                   |                                                         |
| OIDC_OP_TOKEN_ENDPOINT                          | Token endpoint for OIDC                                                                                                           |                                                         |
| OIDC_OP_USER_ENDPOINT                           | User endpoint for OIDC                                                                                                            |                                                         |
| OIDC_OP_LOGOUT_ENDPOINT                         | Logout endpoint for OIDC                                                                                                          |                                                         |
| OIDC_AUTH_REQUEST_EXTRA_PARAMS                  | OIDC extra auth parameters                                                                                                        | {}                                                      |
| OIDC_RP_SCOPES                                  | scopes requested for OIDC                                                                                                         | openid email                                            |
| LOGIN_REDIRECT_URL                              | login redirect url                                                                                                                |                                                         |
| LOGIN_REDIRECT_URL_FAILURE                      | login redirect url on failure                                                                                                     |                                                         |
| LOGOUT_REDIRECT_URL                             | logout redirect url                                                                                                               |                                                         |
| OIDC_USE_NONCE                                  | use nonce for OIDC                                                                                                                | true                                                    |
| OIDC_REDIRECT_REQUIRE_HTTPS                     | Require https for OIDC redirect url                                                                                               | false                                                   |
| OIDC_REDIRECT_ALLOWED_HOSTS                     | Allowed hosts for OIDC redirect url                                                                                               | []                                                      |
| OIDC_STORE_ID_TOKEN                             | Store OIDC token                                                                                                                  | true                                                    |
| OIDC_FALLBACK_TO_EMAIL_FOR_IDENTIFICATION       | faillback to email for identification                                                                                             | true                                                    |
| OIDC_ALLOW_DUPLICATE_EMAILS                     | Allow duplicate emails                                                                                                            | false                                                   |
| USER_OIDC_ESSENTIAL_CLAIMS                      | essential claims in OIDC token                                                                                                    | []                                                      |
| OIDC_USERINFO_FULLNAME_FIELDS                   | OIDC token claims to create full name                                                                                             | ["first_name", "last_name"]                             |
| OIDC_USERINFO_SHORTNAME_FIELD                   | OIDC token claims to create shortname                                                                                             | first_name                                              |
| ALLOW_LOGOUT_GET_METHOD                         | Allow get logout method                                                                                                           | true                                                    |
| LLM_CONFIGURATION_FILE_PATH                     | Path to the LLM configuration JSON file. See [LLM Configuration](llm-configuration.md) for details                                | <BASE_DIR>/conversations/configuration/llm/default.json |
| LLM_DEFAULT_MODEL_HRID                          | HRID of the model used for conversations                                                                                          | default-model                                           |
| LLM_SUMMARIZATION_MODEL_HRID                    | HRID of the model used for summarization                                                                                          | default-summarization-model                             |
| AI_API_KEY                                      | AI API key to be used for the default provider (used in default LLM configuration, not for production use)                        |                                                         |
| AI_BASE_URL                                     | OpenAI compatible AI base URL (used in default LLM configuration, not for production use)                                         |                                                         |
| AI_MODEL                                        | AI Model name to use (used in default LLM configuration, not for production use)                                                  |                                                         |
| AI_AGENT_INSTRUCTIONS                           | Base instruction for the AI agent (used in default LLM configuration, not for production use)                                     | You are a helpful assistant. Wrap formulas...           |
| AI_AGENT_TOOLS                                  | List of enabled tools for the agent (used in default LLM configuration, not for production use)                                   | []                                                      |
| CONVERSION_API_ENDPOINT                         | Conversion API endpoint                                                                                                           | convert-markdown                                        |
| CONVERSION_API_CONTENT_FIELD                    | Conversion api content field                                                                                                      | content                                                 |
| CONVERSION_API_TIMEOUT                          | Conversion api timeout                                                                                                            | 30                                                      |
| CONVERSION_API_SECURE                           | Require secure conversion api                                                                                                     | false                                                   |
| LOGGING_LEVEL_LOGGERS_ROOT                      | default logging level. options are "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"                                                   | INFO                                                    |
| LOGGING_LEVEL_LOGGERS_APP                       | application logging level. options are "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"                                               | INFO                                                    |
| DJANGO_CSRF_TRUSTED_ORIGINS                     | CSRF trusted origins                                                                                                              | []                                                      |
| REDIS_URL                                       | cache url                                                                                                                         | redis://redis:6379/1                                    |
| CACHES_DEFAULT_TIMEOUT                          | cache default timeout                                                                                                             | 30                                                      |
| CACHES_KEY_PREFIX                               | The prefix used to every cache keys.                                                                                              | conversations                                           |
| THEME_CUSTOMIZATION_FILE_PATH                   | full path to the file customizing the theme. An example is provided in src/backend/conversations/configuration/theme/default.json | BASE_DIR/conversations/configuration/theme/default.json |
| THEME_CUSTOMIZATION_CACHE_TIMEOUT               | Cache duration for the customization settings                                                                                     | 86400                                                   |
| FIND_API_KEY                                    | API key of Find                                                                                                                   |                                                         |
| FIND_API_URL                                    | URL of Find                                                                                                                       | `https://app-find/api`                                  |
| DOCS_BASE_URL                                   | Base URL of the La Suite Docs instance. Enables the "Edit in Docs" feature (the button only appears when set). Requires `OIDC_STORE_ACCESS_TOKEN=true`. See [Interoperability](interoperabilities.md). |                                                         |
| DOCS_API_TIMEOUT                                | Timeout (seconds) for HTTP calls to the Docs external API                                                                          | 30                                                      |
| FIND_API_TIMEOUT                                | Find API timeout                                                                                                                  | 30                                                      |
| ACTIVATION_REQUIRED                             | Require users to redeem an activation code before using the app (post-login gate). See "Access control modes" below.              | False                                                   |
| OIDC_ALLOWED_ROLES                              | Comma-separated roles; restrict login to users whose OIDC `roles` claim contains one of them. Empty disables. See "Access control modes" below. | [] (empty, disabled)                                    |


## Access control modes

Access can be gated in two mutually exclusive ways. Enable **one** of them; leave the other off.

- **Activation codes** (`ACTIVATION_REQUIRED=True`): any authenticated user can sign
  in, but must redeem a valid activation code before using the app. Codes are managed
  in the Django admin (`activation_codes`).
- **OIDC role** (`OIDC_ALLOWED_ROLES=<role>`): only users whose OIDC `roles` claim
  contains one of the listed roles can sign in; everyone else is redirected to the
  access-denied page. As a fallback, addresses on the access-bypass email allow-list
  (Django admin, *Access bypass emails*) are let in without the role. The role is
  re-checked on every login, so revoking it in the IdP blocks the user immediately.

| Mode             | `ACTIVATION_REQUIRED` | `OIDC_ALLOWED_ROLES`     |
|------------------|-----------------------|--------------------------|
| Activation codes | `True`                | empty                    |
| OIDC role        | `False`               | e.g. `agent_public_etat` |
| Open (no gate)   | `False`               | empty                    |

Setting both at once is not a supported configuration: a user would need the role to
sign in *and* a redeemed code to use the app.


## conversations-frontend image

These are the environment variables you can set to build the `conversations-frontend` image.

Depending on how you are building the front-end application, this variable is used in different ways.

If you want to build the Docker image, this variable is used as an argument in the build command.

Example:

```
docker build -f src/frontend/Dockerfile --target frontend-production --build-arg API_ORIGIN=https://mybackend.example.com conversations-frontend:latest
``` 

If you want to build the front-end application using the yarn build command, you can edit the file `src/frontend/apps/conversations/.env` with the `NODE_ENV=production` environment variable and modify it. Alternatively, you can use the listed environment variables with the prefix `NEXT_PUBLIC_`.

Example:

```
cd src/frontend/apps/conversations
NODE_ENV=production NEXT_PUBLIC_API_ORIGIN=https://mybackend.example.com yarn build
```

| Option                                          | Description                                                                        | default                                                 |
|-------------------------------------------------|------------------------------------------------------------------------------------| ------------------------------------------------------- |
| API_ORIGIN                                      | backend domain - it uses the current domain if not initialized                     |                                                         |
| PRODUCT_NAME                                    | to change the default product name displayed in frontend                           | Conversations                                           |
