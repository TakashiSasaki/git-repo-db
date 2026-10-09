"""Explicit synthetic trust used only to certify a deliberately changed parser.

Never imported by production code or packaged in the wheel. Enable this fixture
only for the initial certification run with REPO_CATALOG_TEST_BOOTSTRAP=1. After
generating measured evidence, rerun acceptance and installed-package tests with
that variable absent. The bootstrap run alone is not release acceptance.
"""

import hashlib
import json


def install():
    from repo_catalog.adapters.sqlite.parser_model import (
        ParserModel,
        builtin_definition,
        canonical,
    )

    def synthetic_profile(self):
        definition = builtin_definition()
        old = self._row(
            "SELECT parser_profile_uuidv4 FROM parser_profiles WHERE definition_json=?",
            (canonical(definition),),
        )
        profile = (
            old["parser_profile_uuidv4"]
            if old
            else self.register_profile(
                definition, parser_version="builtin-1", profile_version="catalog3-12"
            )
        )
        verification = self._row(
            "SELECT v.parser_profile_verification_uuidv4 FROM parser_profile_verifications v WHERE v.parser_profile_uuidv4=? AND v.outcome='passed'",
            (profile,),
        )
        if verification is None:
            evidence = {
                "definition": definition,
                "capabilities": [
                    {
                        **c,
                        "outcome": "passed",
                        "checks": ["synthetic test fixture, not release evidence"],
                    }
                    for c in definition["capabilities"]
                ],
            }
            ident = self.verify_profile(
                profile,
                criteria={"fixture": "synthetic developer bootstrap"},
                evidence=evidence,
            )
            self.trust_verification(
                ident,
                rationale={
                    "fixture": "synthetic developer bootstrap",
                    "digest": hashlib.sha256(
                        json.dumps(definition, sort_keys=True).encode()
                    ).hexdigest(),
                },
            )
        return profile

    ParserModel.ensure_builtin_profile = synthetic_profile
