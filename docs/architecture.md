## Architecture

### Global system architecture

```mermaid
flowchart TD
    User -- HTTP --> Front("Frontend (NextJS SPA)")
    Front -- REST API --> Back("Backend (Django)")
    Front -- OIDC --> Back -- OIDC ---> OIDC("Keycloak / ProConnect")
    Back -- REST API --> Yserver
    Back --> DB("Database (PostgreSQL)")
    Back <--> Celery --> DB
```
