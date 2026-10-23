# Actual integration ancestry

Full object identities and trees are in `integration-identities.json`; `dag.txt.gz`
is the recorded Git graph. Arrows run from parent to child. Both reviewed branch
histories are retained; PR150 is reference only and not an ancestor.

```mermaid
flowchart LR
  A["154: 91827360"] --> M1["merge147: 9c3de774"]
  B["147: e7762952"] --> M1
  M1 --> M2["merge144: 9f005eb2"]
  C["144: ededcd83"] --> M2
  M2 --> T["tested/published source: fb5d7b5a<br/>tree d2010275"]
  T --> E["evidence + verified skill prose<br/>493 execution inputs invariant"]
```

All three reviewed inputs share merge-base133 `f16e5b1713bde9a2f18263a25397c4b450fd5773`.
The actual initial CI checkout `c915fc731bd60339e681a6af8f86a470058a5e06` has
ordered parents154/source and exactly the tested source tree. Final evidence
publication HEAD/tree and its actual CI test-merge are externally bound in PR155.
