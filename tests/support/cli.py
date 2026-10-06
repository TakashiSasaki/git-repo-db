import json
import os
import subprocess
from functools import lru_cache
from importlib.resources import files

import jsonschema


@lru_cache(maxsize=1)
def response_validator():
    schema = json.loads(
        files("repo_catalog")
        .joinpath("resources/schemas/cli-v1.schema.json")
        .read_text()
    )
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)  # Once per process; validate EVERY response.
    return validator(schema)


def run(state, *args, expected=0, env=None):
    child = {
        k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")
    }
    child.update(env or {})
    p = subprocess.run(
        [
            "repo-catalog",
            "--state-dir",
            str(state),
            "--format",
            "json",
            *map(str, args),
        ],
        capture_output=True,
        text=True,
        env=child,
        timeout=60,
    )
    try:
        value = json.loads(p.stdout)
    except ValueError:
        raise AssertionError((p.returncode, p.stdout, p.stderr))
    response_validator().validate(value)
    if expected is not None:
        assert p.returncode == expected, (p.returncode, value, p.stderr)
    return value


def pages(state, *args, expected=0, limit=2):
    items = []
    cursor = None
    while True:
        page = run(
            state,
            *args,
            "--limit",
            limit,
            *(["--cursor", cursor] if cursor else []),
            expected=expected,
        )
        items.extend(page["data"]["items"])
        cursor = page["data"]["page"]["next_cursor"]
        if cursor is None:
            return items


def add_local(state, name, url):
    source = run(state, "sources", "add", "local-git", "--name", name, "--url", url)[
        "data"
    ]["source_id"]
    return run(state, "discover", "--source", source)["data"]["repositories"][0][
        "repo_id"
    ]
