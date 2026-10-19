"""Check that selected contract tests reject deliberately weakened SQL variants.

These are fault-injection experiments, not independent-agent review. A failed
selected test is expected evidence that a mutated contract was detected.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path
import unittest
import contract_probe as p


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args()
    original=p.DDL
    variants=[
        ('profile_aba_revival','DROP TRIGGER profile_revoke;', 'test_profile_aba_does_not_revive_grant'),
        ('repository_aba_revival','DROP TRIGGER binding_revoke;', 'test_binding_aba_does_not_revive_grant'),
        ('context_aba_revival','DROP TRIGGER context_revoke;', 'test_context_aba_does_not_revive_grant'),
        ('registration_replace','DROP TRIGGER registration_no_delete;', 'test_registration_write_attack_02'),
        ('grant_snapshot_omitted','DROP TRIGGER grant_checked;', 'test_grant_requires_current_profile'),
        ('rank_after_enable_filter', '''DROP VIEW scope_first_choices;
        CREATE VIEW scope_first_choices AS
        SELECT l.* FROM scope_locators l JOIN scope_locator_controls c USING(scope_uuidv4,registered_at_us,scope_locator_uri)
        WHERE c.enabled=1 AND l.registered_at_us=(SELECT MAX(m.registered_at_us) FROM scope_locators m
        JOIN scope_locator_controls d USING(scope_uuidv4,registered_at_us,scope_locator_uri)
        WHERE m.scope_uuidv4=l.scope_uuidv4 AND d.enabled=1);''', 'test_newest_disabled_does_not_fallback'),
    ]
    records=[]
    try:
        for name,mutation,test_name in variants:
            p.DDL=original+'\n'+mutation
            out=io.StringIO()
            result=unittest.TextTestRunner(stream=out).run(unittest.TestSuite([p.ContractTests(test_name)]))
            assertion_detected=len(result.failures)==1 and not result.errors
            fk_blocked=(name=='repository_aba_revival' and not result.failures and len(result.errors)==1
                        and 'sqlite3.IntegrityError: FOREIGN KEY constraint failed' in result.errors[0][1])
            detected=assertion_detected or fk_blocked
            records.append({'variant':name,'test':test_name,'detected':detected,'mechanism':'foreign_key_defense' if fk_blocked else 'invariant_assertion','failures':len(result.failures),'errors':len(result.errors),'output':out.getvalue()})
    finally:
        p.DDL=original
    report={'scope':'deliberately weakened SQL; five invariant assertion failures and one redundant FK rejection are expected; arbitrary setup errors do not pass',
            'schema_sha256':hashlib.sha256(original.encode()).hexdigest(),
            'variants':len(records),'detected':sum(r['detected'] for r in records),'records':records}
    args.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
    return report['detected']!=report['variants']
if __name__=='__main__': raise SystemExit(main())
