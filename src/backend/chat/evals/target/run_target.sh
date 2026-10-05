#!/usr/bin/env bash
# Run a git tag of Conversations as an isolated eval target.
#
#   run_target.sh up <tag> [model_hrid]   # backend on http://localhost:${TARGET_PORT:-18071}
#   run_target.sh down <tag>
#
# The tag runs its own compose.yml with our env.d/development files and our
# LLM configuration; a generated override keeps it apart from the current stack.
set -euo pipefail

usage() { echo "usage: $0 up|down <tag> [model_hrid]" >&2; exit 2; }
[[ $# -ge 2 ]] || usage

action=$1
tag=$2
model=${3:-albert-mistral-medium-2508}
here=$(cd "$(dirname "$0")" && pwd)
repo=$(git -C "$here" rev-parse --show-toplevel)
slug=$(printf '%s' "$tag" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '-')
project="conv-target-${slug}"
workdir="${HOME}/.cache/conv-targets/${slug}"
port=${TARGET_PORT:-18071}
DOCKER_USER="$(id -u):$(id -g)"
export DOCKER_USER

compose() {
  docker compose -p "$project" --project-directory "$workdir" \
    -f "$workdir/compose.yml" -f "$workdir/compose.target.yml" "$@"
}

case $action in
  up)
    [[ -d $workdir ]] || git -C "$repo" worktree add --detach "$workdir" "$tag"
    mkdir -p "$workdir/data/media" "$workdir/data/static" "$workdir/data/objectstorage"
    for env_file in common postgresql kc_postgresql crowdin; do
      cp "$repo/env.d/development/$env_file" "$workdir/env.d/development/$env_file"
    done
    docker compose --project-directory "$workdir" -f "$workdir/compose.yml" config --format json \
      | python3 "$here/make_override.py" \
          --image "conversations-target:${slug}" --port "$port" \
          --llm-config "$repo/src/backend/conversations/configuration/llm/custom_llm_configuration.json" \
          --model "$model" --network-name "${project}-lasuite" \
      > "$workdir/compose.target.yml"
    services=(app-dev)
    # No grep -q: an early exit SIGPIPEs compose and pipefail makes the test false.
    if compose config --services | grep -x celery-dev > /dev/null; then services+=(celery-dev); fi
    compose build app-dev
    compose up -d "${services[@]}"
    compose exec -T app-dev python manage.py migrate --noinput
    compose exec -T app-dev python manage.py createsuperuser \
      --email admin@example.com --password admin
    # createsuperuser only sets admin_email; chat code expects the email and
    # OIDC sub a real user always has (e.g. Langfuse reads email's domain).
    compose exec -T app-dev python manage.py shell -c \
      "from core.models import User; User.objects.filter(admin_email='admin@example.com').update(email='admin@example.com', sub='eval-admin')"
    for _ in $(seq 1 90); do
      if curl -fsS "http://localhost:${port}/api/v1.0/config/" > /dev/null; then
        echo "target ${tag} (${model}) ready on http://localhost:${port}"
        exit 0
      fi
      sleep 2
    done
    echo "target ${tag} did not become healthy; see: docker compose -p ${project} logs app-dev" >&2
    exit 1
    ;;
  down)
    if [[ -d $workdir ]]; then
      compose down -v --remove-orphans || true
      git -C "$repo" worktree remove --force "$workdir"
    fi
    ;;
  *)
    usage
    ;;
esac
