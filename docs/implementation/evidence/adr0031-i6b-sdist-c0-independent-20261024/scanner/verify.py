"""Check the independent observations without an Author classifier."""

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
LABELS = ("source155", "source154", "direct", "derived")


def main():
    studies = {
        label: json.loads((HERE / (label + ".json")).read_text()) for label in LABELS
    }
    stores = {
        label: json.loads((HERE / ("store-" + label + ".json")).read_text())
        for label in LABELS
    }
    executions = json.loads((HERE / "executions.json").read_text())
    assert len(executions) == 8 and all(x["exit"] == 0 for x in executions)
    for execution in executions:
        script = Path(execution["command"][1])
        assert (
            hashlib.sha256(script.read_bytes()).hexdigest()
            == execution["script_sha256"]
        )
        assert (
            hashlib.sha256((HERE / "study.py").read_bytes()).hexdigest()
            == execution["observer_sha256"]
        )
        output = Path(execution["command"][-1])
        assert (
            hashlib.sha256(output.read_bytes()).hexdigest()
            == execution["output_sha256"]
        )
    bindings = {}
    for label in LABELS:
        study, store = studies[label], stores[label]
        assert len(study["admission"]) == 17
        assert len(study["bounded_json"]) == 22
        assert len(study["planner"]) == 6
        assert len(store["cases"]) == 4
        assert all(x["policy_calls"] == 0 for x in study["admission"])
        for record in store["cases"]:
            assert record["result"]["code"] == "INPUT_LIMIT"
            assert record["policy_calls"] == 0
            assert record["rows_before"] == record["rows_after"] == 0
            assert not record["in_transaction"]
            assert record["exact_transfer_fences_preserved"]
            assert record["sql"][-1] == "ROLLBACK"
            assert not any(
                x.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
                for x in record["sql"]
            )
        case = store["cases"][1]
        expansion = [
            x
            for x in case["events"]
            if x["event"] == "c_return:list.extend" and x["length"] == 1002
        ]
        assert len(expansion) == 1 and expansion[0]["used_work"] == 10000
        assert not expansion[0]["after_refusal"]
        assert case["used_work"] == 10001 and case["prior_work"] == 9992
        assert case["input_json_bytes"] == 58891
        assert store["cases"][2]["maxima"]["charge_input:queue_length"] == 1
        selected = store["cases"][3]
        assert selected["selection_work_limit"] == 7 and selected["used_work"] == 8
        assert selected["maxima"]["charge_input:queue_length"] == 1002
        # Properly pre-reserved codec controls refuse before queuing any of1000 children.
        for record in study["bounded_json"]:
            if (
                record.get("label")
                in ("list1000", "dict1000", "embedded_json", "typed_identity")
                and record["work_limit"] <= 17
            ):
                assert record["outcome"] == "Refused"
                assert record["maxima"]["_bounded_json:queue_length"] <= 2
                assert record["calls"].get("parser:loads", 0) == 0
                assert record["calls"].get("parser:parse_identity", 0) == 0
        late, full = study["planner"][-2:]
        assert (
            late["result"]["emitted_units"] == 2
            and full["result"]["emitted_units"] == 3
        )
        assert late["result"]["section_counts"]["providers"] == 1
        assert late["result"]["section_counts"]["resources"] == 1
        assert late["result"]["omission_reasons"] == ["work_limit"]
        bindings[label] = study["binding"]
    hashes = [
        {k: v["sha256"] for k, v in studies[label]["binding"]["modules"].items()}
        for label in LABELS
    ]
    assert all(x == hashes[0] for x in hashes)
    module_git = {}
    for module, receipt in studies["source155"]["binding"]["modules"].items():
        relative = Path(receipt["path"]).relative_to(ROOT).as_posix()
        module_git[relative] = {}
        for revision in (
            "fee364c6d61a5feebf08dbdd830a5a57ee2d872b",
            "91827360c185cbf813277bf32a6627d894b1b20a",
        ):
            body = subprocess.check_output(
                ["git", "show", revision + ":" + relative], cwd=ROOT
            )
            digest = hashlib.sha256(body).hexdigest()
            assert digest == receipt["sha256"]
            module_git[relative][revision] = digest
    result = dict(
        verified=True,
        verdict="FAIL",
        finding="I155-M01",
        severity="Medium",
        labels=list(LABELS),
        per_form=dict(admission=17, bounded_json=22, planner=6, real_store=4),
        source_and_installed_module_hashes_equal=True,
        source_binding=module_git,
        real_store_expansion=expansion[0],
        bindings=bindings,
        limits="Bounded observations only; no claim of unlimited scanner absence or allocation accounting beyond recorded cases.",
    )
    (HERE / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("verified", "verdict", "finding", "severity", "per_form")
            }
        )
    )


if __name__ == "__main__":
    main()
