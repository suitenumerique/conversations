"""Guard tests ensuring the Test settings never read from the environment.

Every setting ``Base`` derives from an environment variable is redefined with an
explicit literal in ``Test`` (see ``conversations.settings.Test``), so tests are
deterministic regardless of the developer-local ``env.d/development/common``
file. These tests fail loudly if that invariant is broken — for instance when a
new env-backed setting is added to ``Base`` without a matching literal in
``Test``.

The check is done against the source AST rather than the live classes because
django-configuration resolves (and replaces) the ``values.Value`` descriptors at
import time, so they are no longer introspectable at runtime.
"""

import ast
from pathlib import Path

from django.conf import settings

import pytest

import conversations.settings


@pytest.fixture(name="settings_module")
def settings_module_fixture():
    """Parse the settings module source into an AST module."""
    source = Path(conversations.settings.__file__).read_text(encoding="utf-8")
    return ast.parse(source)


def _class_def(module, name):
    """Return the ClassDef node for the given top-level class name."""
    return next(
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == name
    )


def _is_values_call(node):
    """True for a ``values.<X>Value(...)`` call node."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "values"
    )


def _reads_environment(node):
    """True if the assigned value contains any ``values.Value`` call."""
    return any(_is_values_call(child) for child in ast.walk(node))


def _assigned_names(class_def):
    """Yield the upper-case setting names assigned directly on the class."""
    for statement in class_def.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    yield target.id, statement.value


def _env_backed_settings(class_def):
    """Names of settings the class derives from an environment variable."""
    return {name for name, value in _assigned_names(class_def) if _reads_environment(value)}


def test_every_env_backed_base_setting_is_pinned_in_test(settings_module):
    """Test must redefine every env-backed Base setting with a literal."""
    base = _class_def(settings_module, "Base")
    test = _class_def(settings_module, "Test")

    base_env_backed = _env_backed_settings(base)
    test_overrides = {name for name, _ in _assigned_names(test)}

    missing = sorted(base_env_backed - test_overrides)
    assert not missing, (
        "These env-backed Base settings are not pinned in Test and would be read "
        f"from the environment: {missing}"
    )


def test_test_overrides_use_literals_not_environment(settings_module):
    """No Test override may itself read from the environment."""
    test = _class_def(settings_module, "Test")

    env_reading = sorted(_env_backed_settings(test))
    assert not env_reading, (
        "These Test overrides still read from the environment instead of using a "
        f"literal: {env_reading}"
    )


def test_infra_settings_point_at_the_docker_topology():
    """Sanity check the pinned infra values resolve to the compose services."""
    assert settings.DATABASES["default"]["HOST"] == "postgresql"
    assert settings.AWS_S3_ENDPOINT_URL == "http://minio:9000"
    assert settings.SECRET_KEY
    assert settings.CACHES["default"]["BACKEND"].endswith("LocMemCache")
