"""Independent fixtures built with Git plumbing, never with the app importer."""

import os
import subprocess
from pathlib import Path


def git(path, *args, input=None, extra=None):
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_AUTHOR_NAME": "Fixture",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
        "GIT_AUTHOR_DATE": "@1700000000 +0000",
        "GIT_COMMITTER_DATE": "@1700000000 +0000",
        **(extra or {}),
    }
    return subprocess.run(
        ["git", *map(str, args)],
        cwd=path,
        input=input,
        capture_output=True,
        check=True,
        env=env,
    ).stdout


class FixtureRepo:
    def __init__(self, path, fmt="sha1"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        git(
            self.path.parent,
            "init",
            "--bare",
            "--template=",
            "--object-format=" + fmt,
            self.path,
        )
        self.format = fmt
        self.raws = {}
        self._blob_oids = {}
        self.commits = {}
        self.trees = {}

    def blob(self, raw):
        oid = (
            git(self.path, "hash-object", "-w", "--stdin", "--no-filters", input=raw)
            .strip()
            .decode()
        )
        self.raws[oid] = raw
        if isinstance(raw, (bytes, bytearray, memoryview)):
            self._blob_oids[bytes(raw)] = oid
        return oid

    def _tree_blob(self, raw):
        # Repeated files/commits reuse objects actually written by Git in this
        # fixture, never another repository's objects or invented object IDs.
        key = bytes(raw) if isinstance(raw, (bytes, bytearray, memoryview)) else None
        oid = self._blob_oids.get(key)
        if oid is not None and (self.path / "objects" / oid[:2] / oid[2:]).is_file():
            return oid
        return self.blob(raw)

    def tree(self, files):
        nested = {}
        for name, value in files.items():
            parts = name.split(b"/")
            current = nested
            for p in parts[:-1]:
                current = current.setdefault(p, {})
            current[parts[-1]] = value

        def build(items):
            records = []
            for name, value in items.items():
                if isinstance(value, dict):
                    mode = "040000"
                    typ = "tree"
                    oid = build(value)
                else:
                    mode, raw = value if isinstance(value, tuple) else ("100644", value)
                    typ = "commit" if mode == "160000" else "blob"
                    oid = raw if mode == "160000" else self._tree_blob(raw)
                records.append(
                    mode.encode()
                    + b" "
                    + typ.encode()
                    + b" "
                    + oid.encode()
                    + b"\t"
                    + name
                    + b"\0"
                )
            return (
                git(self.path, "mktree", "-z", "--missing", input=b"".join(records))
                .strip()
                .decode()
            )

        return build(nested)

    def commit(self, label, files, parents=(), backdated=False):
        tree = self.tree(files)
        args = ["commit-tree", tree]
        for parent in parents:
            args.extend(["-p", self.commits[parent]])
        oid = (
            git(
                self.path,
                *args,
                input=(f"commit {label} 認証\n").encode(),
                extra={
                    "GIT_AUTHOR_DATE": "@1600000000 +0000",
                    "GIT_COMMITTER_DATE": "@1600000000 +0000",
                }
                if backdated
                else {},
            )
            .strip()
            .decode()
        )
        self.commits[label] = oid
        self.trees[label] = tree
        return oid

    def ref(self, name, label):
        git(self.path, "update-ref", name, self.commits.get(label, label))

    @property
    def url(self):
        return self.path.as_uri()


class GitFixture:
    def __init__(self, path):
        p = Path(path)
        self.alpha = FixtureRepo(p / "alpha.git")
        self.beta = FixtureRepo(p / "beta.git")
        self.empty = FixtureRepo(p / "empty.git")
        self.initial = {
            b"shared/a.txt": b"abc",
            b"shared/b.txt": b"abc",
            b"lf.txt": b"abc\n",
            b"crlf.txt": b"abc\r\n",
            b"empty.dat": b"",
            b"binary.bin": b"\0\xff" + b"X" * 2097152,
            b"odd/\xff\tline\n.txt": "固定UTF-8".encode(),
            b"exec.sh": ("100755", b"#!/bin/sh\nexit 0\n"),
            b"link": ("120000", b"shared/a.txt"),
            b"README.md": '認証 配分 X observed_in linkWithPopup AND "quote"\n'.encode(),
        }
        a = self.alpha
        a.commit("A", self.initial)
        self.b = {
            **self.initial,
            b"README.md": "認証 main 改訂 observed_in linkWithPopup\n".encode(),
            b"main.txt": b"main",
        }
        self.c = {**self.initial, b"feature.txt": b"feature"}
        self.m = {**self.b, b"feature.txt": b"feature"}
        a.commit("B", self.b, ("A",))
        a.commit("C", self.c, ("A",))
        a.commit("M", self.m, ("B", "C"))
        a.commit("N", self.m, ("M",))
        a.commit("D", {**self.initial, b"old-only.txt": b"old"}, ("A",))
        for ref, label in [
            ("main", "N"),
            ("alias", "M"),
            ("feature", "C"),
            ("rewrite", "D"),
        ]:
            a.ref("refs/heads/" + ref, label)
        self.beta.commit("root", {b"copy.txt": b"abc"})
        self.beta.ref("refs/heads/main", "root")

    def advance(self):
        a = self.alpha
        a.commit("E", {**self.initial, b"new-only.txt": b"new"}, ("A",), True)
        git(a.path, "update-ref", "-d", "refs/heads/feature")
        a.ref("refs/heads/rewrite", "E")
