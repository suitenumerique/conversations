# Running the app locally with Tilt

[Tilt](https://tilt.dev) orchestrates the local Kubernetes development environment: it builds Docker images, deploys all services via Helm, and keeps everything in sync as you edit code.

## Prerequisites

Install the following tools before getting started:

- [Docker](https://docs.docker.com/get-docker/)
- [Kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation) — local Kubernetes cluster
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Helm](https://helm.sh/docs/intro/install/) + [Helmfile](https://helmfile.readthedocs.io/en/latest/#installation)
- [mkcert](https://github.com/FiloSottile/mkcert#installation) — local TLS certificates
- [Tilt](https://docs.tilt.dev/install.html)

## Step 1 — Create the Kubernetes cluster

```bash
make build-k8s-cluster
```

This runs `bin/start-kind.sh`, which:

1. Creates a local Docker registry at `localhost:5001`
2. Creates a Kind cluster named `conversations`
3. Installs the ingress-nginx controller
4. Generates mkcert TLS certificates for `*.127.0.0.1.nip.io`

All local domains resolve to `127.0.0.1` via [nip.io](https://nip.io) — no `/etc/hosts` edits needed.

## Step 2 — Configure secrets

Copy the secrets template and fill in the required values:

```bash
cp env.d/development/kube-secret.dist env.d/development/kube-secret
```

Then edit `env.d/development/kube-secret`:

| Variable | Required | Description |
|---|---|---|
| `AI_BASE_URL` | Yes | LLM provider base URL |
| `AI_API_KEY` | Yes | LLM provider API key |
| `ALBERT_API_URL` | No | Albert API URL (if using Albert provider) |
| `ALBERT_API_KEY` | No | Albert API key |
| `BRAVE_API_KEY` | No | Brave Search API key (web search tool) |
| `STT_SERVICE_URL` | No | Speech-to-text service URL |
| `STT_SERVICE_API_KEY` | No | Speech-to-text service API key |
| `STT_WEBHOOK_API_KEY` | No | Bearer token the STT service uses when calling back the transcription webhook |
| `LANGFUSE_SECRET_KEY` | No | Langfuse secret key |
| `LANGFUSE_PUBLIC_KEY` | No | Langfuse public key |
| `LANGFUSE_HOST` | No | Langfuse instance URL |

## Step 3 — Start the app

```bash
make start-tilt
```

Tilt will:

1. Build the backend and frontend Docker images and push them to `localhost:5001`
2. Deploy supporting services (PostgreSQL, Keycloak, MinIO, Redis) via the `extra` Helm chart
3. Deploy the backend and frontend via the `conversations` Helm chart
4. Run database migrations and create a superuser (`admin@example.com` / `admin`)
5. Watch source files and sync changes live

The Tilt dashboard opens at `http://localhost:10350`. Wait for all resources to turn green before accessing the app.

## Accessing the services

| Service | URL | Credentials |
|---|---|---|
| App | `https://conversations.127.0.0.1.nip.io` | via Keycloak |
| Keycloak admin | `https://conversations-keycloak.127.0.0.1.nip.io` | `su` / `su` |
| MinIO console | `http://localhost:9001` | `conversations` / `password` |
| Tilt dashboard | `http://localhost:10350` | — |

## Django management commands

The Tilt dashboard exposes two buttons on the `conversations-backend` resource:

- **Run makemigration** — runs `python manage.py makemigrations`
- **Run database migration** — runs `python manage.py migrate --no-input`

## Stopping

```bash
make stop-tilt
```

This shuts down Tilt but leaves the Kind cluster running. To also delete the cluster:

```bash
kind delete cluster --name conversations
```
