# ADR 0031 I2 — independent Task G review publication

**Verdict: READY WITH CONDITIONS for bounded I2 persistence and mandatory staged refusals. Whole-product acceptance remains NOT READY.** This independent review of [PR #124](https://github.com/TakashiSasaki/git-repo-db/pull/124) is published in a new owner-authorized Draft PR. It changes only review documentation/evidence; no product implementation, existing test, accepted ADR, dependency, workflow or predecessor evidence is changed.

Read the [independent report](REPORT.md), [machine-readable summary](summary.json), [existing-failure classification](failure-classification.json) and [publication binding](publication.json).

## Executed evidence

The reviewed HEAD is `4cb90d35bd9c572239496a24cb0dd62049029235`, tree `991d588051766ef1b6ba7c1db9309d60caf47fee`. The Task E executed source `cb1df83afc543d74df8b16327bfb2c418786b3b2` has the same executable inputs. The final publication commit is a later documentation-only descendant, not a newly executed runtime checkout.

Fresh independent official-source SQLite 3.51.3 and 3.53.1 builds produced identical outcomes:

| Lane per runtime | Actual result | Exit |
| --- | --- | ---: |
| Broad retained regressions | 2,747 pass, 59 fail, 20 setup errors; 2,826 executed | **1** |
| Existing product SQL diagnostic groups | 301/301 pass; overlaps requirements above | **0** |
| Reviewer-authored counterexamples | 44 pass, 2 fail; 46 executed | **1** |

The 86 dedicated I2/P1-installed cases are included in the broad count. Of its 79 non-successes, 45 call failures plus 20 setup errors are intended I3–I5 Transfer dependencies; 14 call failures are I6 identification Wire dependencies. Later assertions and all 20 blocked test bodies remain unexecuted. A further 2,541 ordinary nodes were outside the executed cohort.

G-R1 independently reproduces incomplete stored-identification verification in direct `Context.candidates()` reads: Global/Scoped corruption is returned through that facade without a stop, while subsequent `identification()` detects it and persists Recovery Stop. This is an explicit I7 follow-up. It is not counted as a passing probe or confused with the successfully enforced minimal I2 Transfer-storage invariant. The report explains the scope judgment and its conditions.

Both direct-wheel and sdist-wheel were independently built and installed outside checkout on both runtimes. All four ordinary I2 probes exit 0; all four unchanged original Access smokes exit 1 at Provider Transfer preflight. The additional installed G-R1 probe also exits 1 in all four combinations. These remain incomplete acceptance results.

## Preserved archive and reproduction

Download [task-g-review-evidence.zip](task-g-review-evidence.zip). Its exact size is **3,309,284 bytes**, SHA-256 **`5aa95ce552c357f7a13aefe969015ea050b1825a8202e7a9f87a79e76a6161ca`**. All **210 indexed payload members** verify; the ZIP contains those members plus its index. See the unchanged [archive receipt](archive-receipt.json) and [member index](artifact-index.json).

The ZIP contains the original frozen `REPORT.md` and `README.md`, complete broad logs/JUnit/phase journals and node inventories, SQL/errors/full rowsets, runtime source IDs/options/PRAGMAs, build provenance, input manifests, package receipts, reviewer scripts and initial failed attempts. Statements in the original report that no publication was performed describe the review freeze before this later owner authorization. The public report adapts those historical statements and links, without rewriting the archived original.

Extract the ZIP into a dedicated review directory. Follow its original `README.md` and `runtime/provenance.json`; create a separate checkout at the exact reviewed HEAD and a locked environment using a dynamically linked interpreter. Set the workspace paths in the reproduction drivers to your extracted directory. Do not spoof SQLite version constants. `reproduction/distributions.py` needs the exact reviewed source, a fresh output directory and the two version-named library directories.

The independently authored [46-case source](test_independent.py.txt) and [installed counterexample driver](installed_independent.py.txt) are exposed as byte-identical text copies for review; their executable originals and hashes are in the ZIP. They are evidence, not added product tests. The original sealed recorder exits 0 after successfully capturing child results; its child exits and the separate assessment exit 1 are the acceptance evidence.

The archive intentionally excludes venvs, SQLite runtime binaries, databases, full extracted sources and the large source sdist. It retains reproducible source URLs/hashes, both built wheels, installed-file hash manifests and the sdist receipt. No product runtime test is claimed to have been rerun merely to publish this review.

## Publication boundary

This Draft PR stacks on the exact reviewed #124 branch. Its new files are confined to `docs/implementation/evidence/adr0031-i2-task-g/`. All predecessor files must remain byte-identical; final commit/tree and local publication-check results are recorded in the PR description.

Retain both Transfer SQL fences until reviewed I3–I5 and matching routes replace them coherently. Complete I6 Wire, I7 recovery including G-R1, and I8 query/Search remain separate. Neither this verdict nor lightweight Development CI authorizes merge, release, deployment or P8 activation.
