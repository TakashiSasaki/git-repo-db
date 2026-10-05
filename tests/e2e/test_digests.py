import hashlib
import subprocess

from tests.support.cli import run


def test_all_raw_digests(catalog):
    state, fixture, repos = catalog
    run(state, "sync", "git")
    for raw in fixture.alpha.raws.values():
        digest = hashlib.sha256(raw).hexdigest()
        matches = run(
            state,
            "search",
            "hash",
            "--repo",
            repos["alpha"],
            "--algorithm",
            "raw-sha256",
            "--digest",
            digest,
        )["data"]["items"]
        assert len(matches) == 1
        content = matches[0]
        assert content["byte_length"] == len(raw)
        for algo in ("md5", "sha1", "sha256"):
            external = (
                subprocess.run(
                    [algo + "sum"], input=raw, capture_output=True, check=True
                )
                .stdout.split()[0]
                .decode()
            )
            assert (
                external
                == content["digests"][algo]
                == hashlib.new(algo, raw).hexdigest()
            )
