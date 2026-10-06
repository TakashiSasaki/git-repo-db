"""Launch the packaged offline importer in its dedicated guarded process."""

import copy
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.config import DEFAULTS, load, serialize
from repo_catalog.domain.models import CancellationToken, CatalogError


def import_catalog(
    source_path,
    state_dir,
    *,
    source_caches=(),
    batch_size=100,
    max_batches=None,
    token=None,
):
    token = token or CancellationToken()
    token.check()
    state_dir = Path(state_dir).expanduser().resolve()
    source_path = Path(source_path).expanduser().absolute()
    source_caches = [Path(p).expanduser().absolute() for p in source_caches]
    protected = [source_path.resolve(), *(p.resolve() for p in source_caches)]
    if any(
        state_dir == p or state_dir.is_relative_to(p) or p.is_relative_to(state_dir)
        for p in protected
    ):
        raise CatalogError(
            "SOURCE_WORKSPACE_OVERLAP",
            "Import requires separate source and destination storage",
        )
    state_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(state_dir / "locks/writer.lock"):
        config_path = state_dir / "catalog.toml"
        if not config_path.exists():
            config = copy.deepcopy(DEFAULTS)
            config["cache"].update(max_bytes=1073741824, min_free_bytes=67108864)
            with config_path.open("x", encoding="utf-8") as stream:
                stream.write(serialize(config))
        config = load(state_dir)
        if config["database"]["filename"] != "catalog.sqlite3":
            raise CatalogError(
                "CONFIG_ERROR", "Import target filename must be catalog.sqlite3"
            )
        (state_dir / "cache").mkdir(exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "repo_catalog.adapters.import_v2.worker",
        "--source",
        str(source_path),
        "--state-dir",
        str(state_dir),
        "--batch-size",
        str(batch_size),
    ]
    for cache in source_caches:
        command.extend(["--source-cache", str(cache)])
    if max_batches is not None:
        command.extend(["--max-batches", str(max_batches)])
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    token.check()
    child = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        start_new_session=True,
    )
    try:
        while True:
            token.check()
            try:
                stdout, _ = child.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        token.check()
    except (CatalogError, KeyboardInterrupt):
        _stop_worker(child)
        raise CatalogError(
            "CANCELLED",
            "Import interrupted; committed batches can be resumed",
            retryable=True,
        ) from None
    try:
        report = json.loads(stdout)
    except (ValueError, TypeError):
        raise CatalogError(
            "IMPORT_WORKER_FAILED",
            "Guarded import worker failed before reporting a result",
        ) from None
    if child.returncode == -signal.SIGINT or report.get("code") == "IMPORT_INTERRUPTED":
        raise CatalogError(
            "CANCELLED",
            "Import interrupted; committed batches can be resumed",
            retryable=True,
        )
    if child.returncode or not report.get("ok"):
        raise CatalogError(
            report.get("code", "IMPORT_WORKER_FAILED"),
            "Offline import stopped; source bytes remain protected",
        )
    return report["result"]


def _stop_worker(child):
    """Interrupt first, then bound cleanup if a native call cannot cooperate."""
    if child.poll() is None:
        child.send_signal(signal.SIGINT)
    try:
        child.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        child.terminate()
        try:
            child.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate(timeout=5)
