"""The git ref's stack HTTP-driven datasets talk to, set by run_evals."""

from dataclasses import dataclass

# Superuser created by run_target.sh on a local throwaway target.
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin"  # noqa: S105


@dataclass(frozen=True)
class Target:
    """One running target: where it is, which code it runs, which model answers."""

    url: str
    tag: str
    model: str
    admin_email: str = ADMIN_EMAIL
    admin_password: str = ADMIN_PASSWORD


_STATE: dict[str, Target] = {}


def configure_target(target: Target | None) -> None:
    """Set (or clear) the target for this process."""
    _STATE.clear()
    if target is not None:
        _STATE["target"] = target


def current_target() -> Target:
    """Return the configured target or fail with how to configure one."""
    if "target" not in _STATE:
        raise RuntimeError(
            "No eval target configured: pass --target-url, --target-tag and --target-model."
        )
    return _STATE["target"]
