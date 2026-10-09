"""Explicit parser registration, verification, trust, selection and offline reparse."""

import json
from pathlib import Path

from repo_catalog.adapters.filesystem.locks import FileLock
from repo_catalog.adapters.sqlite.parser_model import ParserModel
from repo_catalog.adapters.sqlite.store import Store
from repo_catalog.domain.models import CatalogError, Result


class ParserService:
    def __init__(self, state_dir):
        self.path = Path(state_dir)

    def execute(self, action, options):
        if action == "status":
            with (
                Store(self.path, readonly=True) as store,
                store.transaction(read=True),
            ):
                return Result(
                    {
                        table: [
                            dict(row) for row in store.all("SELECT * FROM " + table)
                        ]
                        for table in (
                            "parser_profiles",
                            "parser_profile_verifications",
                            "parser_profile_verification_invalidations",
                            "local_parser_profile_verification_trust",
                            "parser_profile_selection_scopes",
                            "active_parser_profile_selections",
                            "active_fact_selections",
                            "parser_profile_selection_staging",
                            "fact_selection_staging",
                        )
                    },
                    catalog=store.revision(),
                )
        data = {}
        if options.get("input"):
            try:
                data = json.loads(Path(options["input"]).read_text())
            except (ValueError, UnicodeError) as exc:
                raise CatalogError(
                    "INVALID_ARGUMENT", "Expected a JSON object"
                ) from exc
            if not isinstance(data, dict):
                raise CatalogError("INVALID_ARGUMENT", "Expected a JSON object")
        with FileLock(self.path / "locks/writer.lock"), Store(self.path) as store:
            if action == "reparse":
                from repo_catalog.application.parsing_service import ParsingService

                # Reparse owns the atomic fact/input publication transaction.
                value = ParsingService(store).reparse(
                    options["fetch_occurrence_uuidv4"],
                    select=options["select"],
                    profile_uuid=options.get("profile_uuidv4"),
                )
                with store.transaction():
                    ParserModel(store.connection).promote_staging()
                return Result(
                    {"action": action, "result": value}, catalog=store.revision()
                )
            with store.transaction():
                model = ParserModel(store.connection)
                methods = {
                    "register": model.register_profile,
                    "verify": model.verify_profile,
                    "select-profile": model.select_profile,
                    "select-fact": model.select_fact,
                }
                try:
                    if action in methods:
                        value = methods[action](**data)
                    elif action == "trust":
                        value = model.trust_verification(
                            options["verification_uuidv4"],
                            not options["revoke"],
                            rationale={"actor": "explicit-local-cli"},
                        )
                    elif action == "invalidate":
                        value = model.invalidate_verification(
                            options["verification_uuidv4"], options["reason"]
                        )
                    elif action == "admit-decision":
                        decision_kind = data.pop("decision_kind")
                        if decision_kind not in ("profile", "fact"):
                            raise CatalogError(
                                "INVALID_ARGUMENT",
                                "decision_kind must be profile or fact",
                            )
                        value = (
                            model.receive_profile_decision
                            if decision_kind == "profile"
                            else model.receive_fact_decision
                        )(data)
                    else:
                        raise CatalogError("INVALID_ARGUMENT", "Unknown parser action")
                except (TypeError, KeyError) as exc:
                    raise CatalogError(
                        "INVALID_ARGUMENT",
                        "Parser request fields do not match the action",
                    ) from exc
                model.promote_staging()
                response = Result(
                    {"action": action, "result": value}, catalog=store.revision()
                )
                if action == "admit-decision" and value == "staged":
                    response.status = "partial"
                    response.coverage.add("parser", "decision_staged")
                return response
