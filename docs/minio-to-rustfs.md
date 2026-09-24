# Switching your local environment from MinIO to RustFS

_Switch made in September 2026._

MinIO images are no longer distributed, so the Docker Compose stack now uses
[RustFS](https://github.com/rustfs/rustfs), an S3-compatible object storage
server. This guide is for developers who already have a local environment
running with MinIO. Fresh installs (`make bootstrap`) need none of this.

## What changed

| | Before (MinIO) | After (RustFS) |
|---|---|---|
| Compose service / hostname | `minio` | `objectstorage` |
| S3 endpoint (inside Docker) | `http://minio:9000` | `http://objectstorage:9000` |
| Local data folder | `data/media` | `data/objectstorage` |
| Bucket setup | `mc` client | `rc` client (RustFS CLI) |

Unchanged: ports `9000` (S3 API) and `9001` (web console), credentials
`conversations` / `password`, and the bucket name `conversations-media-storage`.

> ⚠️ Files uploaded while you were on MinIO are **not** migrated. Existing
> attachments in your local database will point to missing files. If you need
> clean data, reset the database with `make demo` after the switch.

## Steps

All commands run from the repository root.

### 1. Stop the stack

```bash
make stop
```

### 2. Pull the change

```bash
git checkout main && git pull
```

### 3. Update your local environment file

`env.d/development/common` is your local copy of
`env.d/development/common.dist` and is not tracked by git, so it still points
to MinIO. Open it and change the S3 endpoint line from

```
AWS_S3_ENDPOINT_URL=http://minio:9000
```

to

```
AWS_S3_ENDPOINT_URL=http://objectstorage:9000
```

If you use other local env files or a `compose.override.yml` that mention
`minio`, replace `minio` with `objectstorage` there too.

### 4. Remove the old MinIO container

The `minio` service no longer exists in `compose.yml`, so its container is left
behind as an orphan and keeps port `9000` busy:

```bash
docker rm -f conversations-minio-1
```

### 5. Start the stack

```bash
make run
```

This starts RustFS and then runs the `createbuckets` service, which creates the
bucket and applies the CORS rule needed for browser uploads.

### 6. Check that it worked

```bash
docker compose ps objectstorage          # should be "healthy"
docker compose logs createbuckets
```

The `createbuckets` logs should show:

```
✓ Alias 'conversations' configured successfully.
✓ Bucket 'conversations/conversations-media-storage' created successfully.
✓ Applied 1 bucket CORS rule(s).
```

Then upload a file in a conversation from the app. You can also browse the
bucket in the RustFS console at <http://localhost:9001> (`conversations` /
`password`).

### 7. Optional: delete the old MinIO data

Once you are happy with the switch:

```bash
rm -rf data/media
```

## Troubleshooting

**`Bind for 0.0.0.0:9000 failed: port is already allocated`**
The old MinIO container is still running. Redo step 4 (`docker ps` shows its
exact name if it differs).

**RustFS exits with `Permission denied (os error 13)`**
`data/objectstorage` is created automatically on the first start. On Linux,
Docker may create it owned by `root`, and RustFS (which runs as your user)
cannot write to it. Make the folder yours, then restart:

```bash
sudo chown -R "$(id -u):$(id -g)" data/objectstorage
make run
```

On Windows, see [RustFS Permission Issues on Windows](troubleshoot.md#rustfs-permission-issues-on-windows).

**Uploads fail with a CORS error in the browser console**
(`Access-Control-Allow-Origin` missing). RustFS, unlike MinIO, only sends CORS
headers when the bucket has a CORS rule. Re-run the bucket setup:

```bash
docker compose run --rm createbuckets
```

**The backend cannot reach storage (`Could not connect to the endpoint URL: http://minio:9000/...`)**
Your `env.d/development/common` still points to MinIO. Redo step 3, then
`make run`.

**I want to start again from an empty bucket**

```bash
docker compose stop objectstorage
rm -rf data/objectstorage
mkdir data/objectstorage
make run
```

Delete the whole folder, not `data/objectstorage/*`: the `*` skips the hidden
`.rustfs.sys` folder, where RustFS keeps its bucket metadata. Recreating the
folder yourself keeps it owned by your user (see the Permission denied entry above).

**Host-run pytest fails on presigned URL tests with a region mismatch**
If your `~/.aws/config` sets a default region (for example for another S3
provider), it leaks into host-run tests. Run them with
`AWS_CONFIG_FILE=/dev/null`, or use `make test-back`, which runs inside Docker.

## Not covered

The Tilt / Helm development stack ([docs/tilt.md](tilt.md)) still uses MinIO
through the external `dev-backend` chart and is unchanged by this switch.
