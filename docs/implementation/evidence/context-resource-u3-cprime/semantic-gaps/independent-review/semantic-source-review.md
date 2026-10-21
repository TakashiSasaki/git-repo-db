# Independent semantic source review

Reviewer: separate agent from the candidate and author probes. This is a
source interpretation receipt, not an execution receipt or owner decision.
The reviewer did not edit candidate files, production files, or accepted ADRs.

Inspected source pins:

- Product `efb55af84ccbf1183d47547d22bb6c57d8fbc8f9`.
- Previous experiment `22b58ce7ff59478f1a4c8c8ef89b17d2f0068590`, tree
  `fcc55256de88c711379d27e38b7eed0c63db6c4a`.
- Proposed design `5244b98a9a302f082a07a526480faf438fc91838`.

## G1: independently identified Document

The existing predicate requires namespace and document coordinates for every
`document`. That excludes a genuine Provider-global scalar or composite Document.
The owner-fixed B3 and proposed schema lines 18–35 and 46–49 permit independent
identification and nonleaf Documents while preserving the PR-scoped contract.

A generic syntax predicate cannot distinguish a native global scalar from a
malformed PR-scoped local ID whose required coordinates were omitted. Correct
admission must select the genuine native contract explicitly and must never
retry a failing known PR contract as generic. Such selection is an admission
responsibility, not proof supplied by SQL FKs. This initial source interpretation required no namespace/subtype coordinates
for independently identified Documents, while a typed coordinate form must remain
complete and consistent. The final reviewed implementation uses NULL for those
three columns and additionally requires `provider_document_id` to repeat the full
canonical native ID; it does not accept all four metadata columns as NULL. Shape heuristics must not reserve every
four-element array, since a native global composite can genuinely have that shape.

An extra identifier discriminator is necessary only when genuine native namespaces
would otherwise collide under the same Provider and kind. It is not needed merely
to describe which validator was used, and must not be fabricated as a storage key.

## G2: encoding Parent identity

Let `J` be the canonical identity encoder and `V` a valid native Parent identity.
For fixed namespace kind, document kind and document coordinate, both `J(V)` as a
string component and `V` as a nested component preserve the same four semantic
coordinates. Both are injective and reversible under their own fixed encoding
contract. ADR 0017 preserves the semantic coordinates, not a particular escaping
strategy. Proposed schema lines 25–35 explicitly favor the Parent's canonical
TEXT as the string component and warn against an incidental representation swap.

The profiles cannot be mixed. They produce different keys for the same native
Resource, including scalar Parents. Mixing them can also alias *different*
Parents: the text-profile key for native `V` equals the nested-profile key for a
Parent whose native scalar identity is the literal text `J(V)`. Therefore specify
one profile and reject the other under that contract; do not guess by shape or
accept both as aliases. No additional semantic coordinate is required to solve
this encoding choice. Native namespace collisions are a separate issue.

## G3: native I7 namespace, attributed I8 Parent

Accepted ADR 0030 line 57 requires an Issue-parented `comment` / `timeline_event`
through the typed FK, plus actual-event admission. Its linked physical design is
explicitly an engineering proposal (ADR lines 28–29). That proposal's lines
357–360 describe the real parent Issue inside the Event identity and retaining
those columns and FK. Product `EventReportKey.issue_parent` (domain/p1_context.py
lines 1624–1629) derives the Issue from those same identity coordinates.

The proposed generalized schema lines 199–203 separates genuine namespace
coordinates from semantic Parent facts. Lines 252–260 nevertheless require
preserved typed SQL references and rejection of a “different Issue”. These texts
do not resolve which Issue that phrase means once namespace and Parent differ.

The concrete competing interpretations are:

1. The I7 coordinate remains the Q-S10 semantic Issue for this native Event
   contract. An I8 Parent report may be retained as an attributed alternative,
   without becoming eligible support for that Event's Transfer. Q-S10-specific
   support validation must reject/withhold it; general relations remain separate.
2. I7 is solely a native identity namespace. A separately qualified report that
   the Event semantically parents to I8 may support a Transfer for I8. This needs
   an explicit statement that Q-S10 follows the qualified relation, and an audit
   of whether that is a refinement or a substantive change to the accepted rule.

B3 permits the distinction; it does not select interpretation 2 or justify
unqualified I8 Transfer admission. A structural FK can prove exact typed report
existence without proving current truth. Parent-report retention, exact-support
SQL validity, actual-event admission, and current qualification must be reported
separately. Universal namespace/Parent equality would wrongly erase B3.

**Source-review conclusion: OWNER DECISION REQUIRED for G3's durable semantic
meaning.** The current investigation introduces one specifically scoped potential
owner blocker; this does not reopen the earlier zero-blocker migration scope.
Pending that resolution, withhold/qualify the mismatched dependent operation and
preserve both the complete Event identity and admissible attributed Parent report.
Do not claim broader ADR 0031 acceptance from the earlier subset demonstration.
