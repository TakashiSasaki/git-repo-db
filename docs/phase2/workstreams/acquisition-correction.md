# Determined Phase 2 correction: current collection observation boundaries

**Status:** implemented corrective work under the existing signed-int64 time,
maximum-time Coverage v2, typed scope, no-original rejection and restart
contracts. This change does not choose a Phase 2 lifecycle, publication identity,
collection replacement, cache or checkpoint policy.

The independently investigated baseline lost a current REST collection's known
newer rejected-resource boundary: page 150 committed, identified malformed member
200 rejected, then terminal retry 175 incorrectly made current coverage complete
at 175. Equal-time retry 200 similarly lost the contradictory candidate. The
baseline characterization and its six passed probe receipts remain recorded in
[the acquisition report](acquisition.md) and
[baseline evidence](acquisition-baseline-evidence.json).

The correction in `GitHubCollector.current_collection` distinguishes an actual
uncommitted response containing a decoded empty collection or recognized current
resource from a transport-only failure. A recognized ordinary Issue requires a
canonical provider ID, positive Issue number and absence of the PR discriminator;
current comment/review IDs must be canonical positive database IDs. Failed
admission stores only the bounded reason and actual observation instant, without
response content, HTTP envelope, fake occurrence, admitted members or a terminal
assertion. Malformed raw JSON, nonlist/error envelopes, missing/Node IDs, explicit
scope mismatch, cancellation and stale attempts cannot manufacture an observed
rejection time. Earlier accepted prefix transactions survive; a rejected page
rolls back every member and body in that page.

Issue summary clocks now include those partial boundaries only while failures
remain, and read the exact repository/Source/job's scoped collections through
indexed page/marker lookups. Completion clocks still come only from accepted
receipts. Consequently retry 175 keeps partial@200 current; retry 200 produces
conflict@200; valid retry 300 produces complete@300. A second Source's observation
cannot lend its instant to the first Source's summary. An incremental scan still
records its original start as the safe watermark only after successful terminal
completion; resuming it does not substitute the later response time.

A related baseline defect was reproduced by executing the exact main
`current_collection` method under the new terminal-cancellation regression. It
created partial coverage after a committed terminal receipt, so a local resume
at the same original time conflicted with that false partial. The corrected
handler keeps this cancellation as operational progress; local finish acquires
nothing and emits complete at the original accepted time. Cancellation of a
nonterminal prefix preserves its partial bound.

Independent malformed-clock review also exposed Boolean coercion in a custom
adapter response: an identified rejected body with observation extension False
or True could persist 0 or 1 as its time. Normal `GitHubTransport` already
validates its clock. Shared `ApiFacts.response_time` now additionally validates
the signed-int64 integer contract before response-clock use, reporting
`API_SCHEMA` for Boolean, float and out-of-range inputs. This preserves valid
zero/negative instants and creates no new observation from a malformed clock.

Verification is **development evidence**, with
`REPO_CATALOG_TEST_BOOTSTRAP=1` explicitly used because changed collector source
invalidates the retained historical parser certificate until the integrated
source tree is frozen and regenerated:

- 28 focused regression/characterization cases passed in 14.61s.
- 182 acquisition, current projection/collection, nested Coverage, Phase 1
  retirement and job-plan cases passed in 40.11s on the final scoped source bytes.
- Ruff lint/format and diff checks passed on the changed Python/files.
- Fresh packaged schema 18 initialized; FK check empty; integrity check `ok`;
  unchanged DDL SHA-256
  `16110944d4b6a0942657644fe80383394210af1218a3e7111e331a1651fa211e`.
- SQLite 3.53.1 EXPLAIN confirmed indexed scoped collection/page/marker searches
  and no whole current-page or completion-marker table scan.

The earlier five malformed-clock failures and deliberately failing baseline
terminal-cancellation reproduction are counterexample evidence, not successful
acceptance. An earlier 175-case development run precedes the final Source-scoped
SQL and clock guard; it is superseded by the final 182-case receipt. The first
fresh-schema probe stopped at missing explicit configuration before initialization
and was rerun with a disposable configured capacity budget. No authenticated
provider, retained catalog, raw/private data or deployment was used.

The root integration must regenerate the legacy certificate from a frozen
successful test definition, run ordinary and isolated package acceptance without
bootstrap, record the actual submitted SHAs/effective trees and obtain hosted CI.
This scoped receipt does not substitute for that acceptance. No PR merge is
performed or authorized here.
