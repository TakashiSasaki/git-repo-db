"""Linux uv 0.12.19 discovery contract; all settings are synthetic test data."""

import json
from pathlib import Path

import pytest

from tests.support.distributions import backend_control_inputs, uv_configuration_files


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, ["/etc/xdg"]),
        ("", ["/etc/xdg"]),
        (":", []),
        ("/one:/two", ["/one", "/two"]),
        ("/one::/two", ["/one"]),
    ],
)
def test_system_candidate_order_and_default(value, expected):
    env = {"HOME": "/synthetic-home"}
    if value is not None:
        env["XDG_CONFIG_DIRS"] = value
    paths = uv_configuration_files(env)
    assert [
        str(path.parent.parent)
        for key, path in paths.items()
        if key.startswith("system-xdg/")
    ] == expected
    assert paths["system-fallback"] == Path("/etc/uv/uv.toml")


@pytest.mark.parametrize("value", [None, "", "relative", "/absolute"])
def test_user_config_home_follows_linux_xdg_absolute_rule(value):
    env = {"HOME": "/synthetic-home"}
    if value is not None:
        env["XDG_CONFIG_HOME"] = value
    expected = (
        "/absolute/uv/uv.toml"
        if value == "/absolute"
        else "/synthetic-home/.config/uv/uv.toml"
    )
    assert uv_configuration_files(env)["user"] == Path(expected)


@pytest.mark.parametrize(
    "variable,value",
    [
        ("XDG_CONFIG_DIRS", "relative"),
        ("UV_CONFIG_FILE", "relative.toml"),
        ("UV_PROJECT", "/redirected"),
        ("UV_WORKING_DIR", "/redirected"),
    ],
)
def test_ambiguous_multi_cwd_config_contract_refuses_reuse(variable, value):
    with pytest.raises(ValueError):
        uv_configuration_files({"HOME": "/synthetic-home", variable: value})


def test_discovery_snapshot_binds_each_ordered_candidate_without_leaking_values(
    tmp_path,
):
    source = tmp_path / "source"
    source.mkdir()
    first, second = tmp_path / "first", tmp_path / "second"
    user, explicit = tmp_path / "user", tmp_path / "explicit.toml"
    env = {
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(user),
        "XDG_CONFIG_DIRS": f"{first}:{second}",
        "UV_CONFIG_FILE": str(explicit),
    }
    snapshot = backend_control_inputs(source, env)
    for candidate in (
        second / "uv/uv.toml",
        first / "uv/uv.toml",
        user / "uv/uv.toml",
        explicit,
    ):
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("synthetic-private-content-a")
        added = backend_control_inputs(source, env)
        assert added != snapshot
        candidate.write_text("synthetic-private-content-b")
        changed = backend_control_inputs(source, env)
        assert changed != added
        assert "synthetic-private-content" not in json.dumps(changed)
        snapshot = changed
    assert uv_configuration_files(
        {**env, "XDG_CONFIG_DIRS": f"{second}:{first}"}
    ) != uv_configuration_files(env)


def test_non_linux_discovery_is_not_claimed(monkeypatch):
    from tests.support import distributions

    monkeypatch.setattr(distributions.sys, "platform", "win32")
    with pytest.raises(ValueError, match="Linux only"):
        uv_configuration_files({})


@pytest.mark.parametrize(
    "name",
    [
        "uv.toml",
        "pyproject.toml",
        "hatch.toml",
        ".gitignore",
        ".hgignore",
        ".python-version",
    ],
)
def test_generated_build_ancestor_controls_invalidate_warm_cache(tmp_path, name):
    from tests.support.distributions import build_once
    from tests.unit.test_build_input_identity import products

    cache = tmp_path / "external-cache"

    def inputs():
        return "e" * 64

    first = build_once(cache, products, inputs=inputs)
    (tmp_path / name).write_text("new ambient build input")

    def reject(_):
        raise ValueError("fresh build rejects ambient configuration")

    with pytest.raises(ValueError, match="fresh build rejects"):
        build_once(cache, reject, inputs=inputs)
    (tmp_path / name).unlink()
    assert (
        build_once(
            cache, lambda _: pytest.fail("equal inputs should reuse"), inputs=inputs
        )
        == first
    )


@pytest.mark.parametrize("location", ["key-ancestor", "generated-source"])
def test_prepared_build_context_changes_refuse_cached_artifacts(tmp_path, location):
    from tests.support.distributions import build_once
    from tests.unit.test_build_input_identity import products

    def inputs():
        return "f" * 64

    files = build_once(tmp_path, products, inputs=inputs)
    root = files["wheel"].parent
    target = (
        root.parent / "uv.toml"
        if location == "key-ancestor"
        else root / "generated/package/uv.toml"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("a changed build setting")
    with pytest.raises(ValueError, match="configuration changed"):
        build_once(
            tmp_path, lambda _: pytest.fail("must not silently rebuild"), inputs=inputs
        )
    target.unlink()
    assert (
        build_once(
            tmp_path, lambda _: pytest.fail("unchanged inputs reuse"), inputs=inputs
        )
        == files
    )
