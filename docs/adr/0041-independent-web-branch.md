---
status: accepted
date: 2026-11-17
replaces: []
refines: ["0035-independent-documentation-workspace.md", "0040-scoped-machine-readable-model-validation.md"]
---

# ADR 0041: Independent website authoring branch

- **Decision & Context:** Keep the website and its independent Node/Python authoring workspaces on the orphan `web` branch of `TakashiSasaki/resource-atlas`. Keep product code, canonical ADRs/contracts, neutral schema production, ownership/frozen-evidence checks and the maintained runtime reference on `main`. Remove transferred website/frontend files from `main` after preserving them on `web`. The `web` tree must contain at most 1,000 tracked files so Google AI Studio can import the selected branch. Its existing Node/Vite frontend must run without product code, Python, API credentials or live catalogs.
- **Constraints / Do NOT:** ADR 0035's independent environments, product-first workflow, full neutral IR, composite/partial/generated schema semantics, publication allowlist, source identities and independent local/hosted release obligations remain binding. Web source SHA/tree, selected product SHA/tree and IR digest remain distinct. Obtain canonical inputs from an explicitly pinned product checkout outside the web tree, using the verified product runtime in a fresh subprocess; retain historical citation objects and byte checks. Transfer only checked IR/producer metadata and source manifests into private build inputs. Website copies and diagrams never become editable canonical ADRs or product authority. Moving tests requires an explicit obligation map; no guard, frozen evidence, scope or historical failure is silently discarded. Production deployment is manual opt-in, separate from ordinary branch push/build and this migration.
- **Reason & Ref:** The owner reported Google AI Studio's 1,000-file import limit and approved the separate `web` branch, one-way canonical-input handoff and removal of transferred files from `main`: “この方針で作業を進めてください。ブランチ名も提案していただいた通で良いです。さらに、メインブランチからは、webブランチに移動したファイルを削除してください。” Approval was given in the 2026-11-17 task annotation `cb0150ab-b6b9-4020-a9c5-4a39ffe3f245`. This is a Level 2 workflow refinement in an unreleased single-user project; it introduces no product database migration or new service. The existing independent workspace now lives on a separate branch; ADR 0035's semantic and verification contract is preserved.

## Ownership and handoff

`docs/web-source-policy.json` is the product-owned publication selection. The web builder reads it from the selected product commit, and preserves the existing directory URL/viewer partitioning and output allowlist. `scripts/export_web_inputs.py` produces complete schema inputs plus canonical-source hashes after checking the selected committed source. The web preparation helper records its external product checkout and validates that checkout before use. Ordinary Node editing uses the existing derived JSON and never performs extraction.

Repository-wide ownership inventory and its tests move to `docs/content-inventory.json`, `scripts/content_inventory.py` and `tests/unit/test_content_ownership.py`. The current product runtime guide moves to `docs/current-runtime-reference.md`; frozen historical bodies retain their original bytes except their separate current-navigation banners. Source files transferred to `web` are recorded in the migration ledger, with main/web test obligations mapped in `docs/web-branch-test-map.json`.

The two branches are not merged into one another for routine site changes. Change product meaning on `main`, deliberately select a new full product SHA on `web`, regenerate/check its inputs and update derived presentation. Fetching the other branch's Git objects for provenance does not check its editable files into the current tree. Build success is scoped evidence, not acceptance of a design, a release or permission to publish.
