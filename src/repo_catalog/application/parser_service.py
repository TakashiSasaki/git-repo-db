"""Legacy parser administration, Git reanalysis and external message inspection."""

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
        if action in ("inspect-message", "reparse-message"):
            return self._message(action, options)
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
                    options["git_acquisition_id"],
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

    def _message(self, action, options):
        """Bounded supplementary inspection never acquires or admits domain state."""
        from repo_catalog.adapters.recording import LocalArchiveReader, RecordingError

        try:
            recorded = LocalArchiveReader(self.path / "transport-archive").read(
                options["archive_reference"], max_body_bytes=options["max_bytes"]
            )
        except RecordingError as error:
            raise CatalogError(error.code, str(error)) from error
        data = {
            "archive_reference": options["archive_reference"],
            "context": recorded.context,
            "body_bytes": len(recorded.body) if recorded.body is not None else None,
            "admitted": False,
        }
        if action == "reparse-message":
            from repo_catalog.adapters.github import current_parser
            from repo_catalog.domain.time import now_us

            try:
                spec = json.loads(Path(options["context"]).read_text())
                kind = spec["resource_kind"]
                context = spec["context"]
                if not isinstance(context, dict) or not isinstance(
                    context.get("acquisition_scope"), dict
                ):
                    raise ValueError()
                if (
                    recorded.body is None
                    or recorded.context.get("response_status") != 200
                ):
                    raise ValueError()
                payload = json.loads(recorded.body)
            except (KeyError, ValueError, TypeError, UnicodeError) as error:
                raise CatalogError(
                    "INVALID_ARGUMENT",
                    "Reparse requires a saved successful JSON body and explicit provider context",
                ) from error
            functions = {
                "issue": current_parser.issue,
                "issue-comment": current_parser.issue_comment,
                "review": current_parser.review,
                "review-comment": current_parser.review_comment,
            }
            if kind not in functions:
                raise CatalogError(
                    "INVALID_ARGUMENT", "Unsupported current resource kind"
                )
            values = payload if isinstance(payload, list) else [payload]
            if len(values) > 1000:
                raise CatalogError(
                    "ARCHIVE_LIMIT", "Reparse member count exceeds the read bound"
                )
            projections = []
            for value in values:
                args = [value, context, recorded.context["observed_at_us"]]
                if kind == "issue-comment":
                    if not isinstance(spec.get("parent_provider_resource_id"), str):
                        raise CatalogError(
                            "INVALID_ARGUMENT",
                            "Issue comment reparse requires an explicit parent provider ID",
                        )
                    args.append(spec["parent_provider_resource_id"])
                projection = functions[kind](*args)
                if projection is not None:
                    projection["parsed_at_us"] = now_us()
                    projections.append(projection)
            data.update(resource_kind=kind, projections=projections, source="replay")
        return Result(data)
