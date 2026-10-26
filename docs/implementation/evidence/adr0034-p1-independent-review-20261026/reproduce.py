"""Independent warm-cache challenges; run through verified local-run.sh.

Copies product inputs into disposable trees. Uses the repository's prepared
locked wheelhouse and actual backend; never edits the checkout or SQLite.
Historical implementations produce a nonzero result with factual JSON output.
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parents[4]
    )
    parser.add_argument("--wheelhouse", type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    wheels = (args.wheelhouse or repository / "artifacts/wheelhouse").resolve()
    if not (wheels / "manifest.json").is_file():
        parser.error("Prepare the locked wheelhouse before running this check")
    sys.path.insert(0, str(repository))
    from tests.support.distributions import (
        build_once,
        make_package_distributions,
        package_build_environment,
        package_build_inputs,
    )

    with tempfile.TemporaryDirectory(prefix="independent-build-review-") as temporary:
        base = Path(temporary)
        source = base / "source"
        shutil.copytree(
            repository / "src",
            source / "src",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        for name in ("pyproject.toml", "README.md", ".gitignore", "uv.lock"):
            shutil.copyfile(repository / name, source / name)
        env = package_build_environment()
        env.update(
            HOME=str(base / "home"),
            XDG_CONFIG_HOME=str(base / "user"),
            XDG_CONFIG_DIRS=str(base / "system"),
        )
        for name in (
            "UV_CONFIG_FILE",
            "UV_NO_CONFIG",
            "UV_NO_SYSTEM_CONFIG",
            "UV_PROJECT",
            "UV_WORKING_DIR",
        ):
            env.pop(name, None)

        def inputs():
            return package_build_inputs(source, env, wheels)

        cache = base / "cache"

        def build(work):
            return make_package_distributions(work, source, env, wheels)

        initial = inputs()
        first = build_once(cache, build, inputs=inputs)
        results = {}
        for label, target, content in (
            (
                "R192-01",
                source / ".hgignore",
                "syntax: glob\nsrc/repo_catalog/__init__.py\n",
            ),
            ("R192-02", base / "system/uv/uv.toml", "not valid TOML\n"),
        ):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            changed = inputs() != initial
            try:
                build_once(cache, build, inputs=inputs)
                cached_refused = False
            except (ValueError, RuntimeError):
                cached_refused = True
            try:
                build(base / ("fresh-" + label))
                fresh_refused = False
            except (ValueError, RuntimeError):
                fresh_refused = True
            target.unlink()

            def forbidden(_):
                raise AssertionError(
                    "Original inputs must reuse their sealed artifacts"
                )

            restored = (
                inputs() == initial
                and build_once(cache, forbidden, inputs=inputs) == first
            )
            results[label] = dict(
                identity_changed=changed,
                cached_refused=cached_refused,
                fresh_refused=fresh_refused,
                removal_restores_reuse=restored,
            )
        control = cache / "uv.toml"
        control.write_text("not valid TOML\n")
        source_unchanged = inputs() == initial
        try:
            build_once(cache, build, inputs=inputs)
            context_refused = False
        except RuntimeError:
            context_refused = True
        control.unlink()
        results["sdist-context"] = dict(
            source_identity_unchanged=source_unchanged,
            cached_refused=context_refused,
            removal_restores_reuse=build_once(cache, forbidden, inputs=inputs) == first,
        )
        print(json.dumps(results, indent=2, sort_keys=True))
        return 0 if all(all(case.values()) for case in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
