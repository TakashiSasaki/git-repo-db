"""Access registrations and settings; route configuration never grants execution."""

import argparse

from repo_catalog.cli.separated_io import emit, failure, invocation

# Explicit method allowlist prevents arbitrary attribute dispatch from input.
METHODS = {
    "register-scope": "register_scope",
    "rename-scope": "rename_scope",
    "register-locator": "register_locator",
    "set-locator-enabled": "set_locator_enabled",
    "configure-scope": "configure_scope",
    "bind-repository": "bind_repository",
    "configure-connection": "configure_connection",
    "assign-connection": "assign_connection",
    "set-preference": "set_preference",
    "revoke": "revoke_local_approval",
    "scope": "scope",
    "history": "history",
    "first-choices": "first_choices",
    "binding": "binding",
    "configuration": "configuration",
    "assignment": "assignment",
    "scope-context": "scope_context",
    "current-grant": "current_grant",
}
READS = {
    "scope",
    "history",
    "first-choices",
    "binding",
    "configuration",
    "assignment",
    "scope-context",
    "current-grant",
}


def main(argv=None):
    import sys

    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "maintenance":
        from repo_catalog.cli.access_maintenance import main as maintenance

        return maintenance(values[1:])
    if values and values[0] in ("review", "approve", "preflight"):
        from repo_catalog.cli.access_workflow import main as workflow

        return workflow(values)
    if values and values[0] in ("backup", "inspect", "restore", "fork"):
        from repo_catalog.cli.access_maintenance import main as maintenance

        return maintenance(values)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            *METHODS,
            "review",
            "approve",
            "preflight",
            "backup",
            "inspect",
            "restore",
            "fork",
            "maintenance",
        ),
    )
    parser.add_argument("--access-db", required=True)
    parser.add_argument(
        "--input",
        required=True,
        help='JSON {"args": [...], "kwargs": {...}}; public DTOs use $type/fields',
    )
    args = parser.parse_args(values)
    from repo_catalog.adapters.sqlite.access_connections import AccessConnections

    try:
        positional, keywords = invocation(args.input)
        with AccessConnections(
            args.access_db, writable=args.command not in READS
        ) as store:
            result = getattr(store, METHODS[args.command])(*positional, **keywords)
        emit({"operation": args.command, "result": result})
        return 0
    except (ValueError, OSError, TypeError, KeyError) as error:
        return failure(error)


if __name__ == "__main__":
    raise SystemExit(main())
