"""Production Context is usable from both installed distribution variants."""

import sys

import pytest

from tests.packaging.test_p1_distribution import p1_distributions, run

__all__ = ["p1_distributions"]


@pytest.mark.parametrize("variant", [0, 1], ids=["wheel", "sdist-wheel"])
def test_installed_production_context(p1_distributions, tmp_path, variant):
    env, wheels = p1_distributions
    outside = tmp_path / "outside"
    outside.mkdir()
    venv = tmp_path / "venv"
    run(["uv", "venv", venv, "--python", sys.executable, "--offline"], outside, env)
    python = venv / "bin/python"
    run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            python,
            "--offline",
            "--no-deps",
            wheels[variant],
        ],
        outside,
        env,
    )
    script = """
from pathlib import Path
from uuid import uuid4
from repo_catalog.adapters.sqlite.p1_schema import initialize
from repo_catalog.adapters.sqlite.production_context import Context
from repo_catalog.domain.p1_context import FieldClock, ResourceKey, canonical
assert 'site-packages' in str(Path(__import__('repo_catalog.adapters.sqlite.production_context', fromlist=['']).__file__))
repo, instance, service = (str(uuid4()) for _ in range(3))
initialize(Path('context.sqlite3'), 'context', repo, instance)
key = ResourceKey.from_native(service, 'issue', 'real-provider-id')
with Context.transaction(Path('.')) as context:
    context.provider(service, 'github')
    context.resource(key)
    context.admit_text(key, 'exact\\x00é😀', FieldClock('provider.updated_at', 1), canonical({'source':'provider','evidence':'event-1'}), 10)
with Context.snapshot(Path('.')) as context:
    digest = __import__('json').loads(context.candidates(key, 'text_body_sha256')[0].value_json)
    assert context.read_text(digest) == 'exact\\x00é😀'
assert not Path('core.sqlite3').exists()
print('production Context installed smoke passed')
"""
    assert "smoke passed" in run([python, "-c", script], outside, env)
