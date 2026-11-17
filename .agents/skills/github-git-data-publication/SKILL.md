---
name: github-git-data-publication
description: Publish an authorized, tested branch through connected GitHub Git-data tools when the cloud CLI keeps stale credentials, preserving exact trees and cross-branch source identities.
---

# Publish the exact tested tree

Use the normal Git transport when it works. A connected GitHub app and the
container's GH_TOKEN can have different authentication states; reconnecting the
app need not replace a running container's token. Never print credentials, ask
for tokens in chat, disable TLS, or claim a failed CLI login succeeded.

For an already authorized publication, the connected Git-data tools can upload
UTF-8 tree entries and base64 binary blobs. Preserve modes and paths. Check every
binary blob ID and require the resulting remote tree ID to equal the tested
local tree. Read large payloads in bounded chunks without printing their contents.
Do not include caches, private source checkouts, catalogs or credential files.

The create_commit wrapper accepted an empty parent_sha for a root commit during
this migration. Verify the actual Git-data response has an empty parents array
before describing a published branch as orphan; do not infer it from a name.
Ordinary feature commits retain the actual current product parent.

API commits can have different author/time metadata and therefore different IDs
from locally created commits, even when their trees match. Read the complete
Git-data commit with the connected GET tool. An unsigned commit may be imported
locally only after reconstructing its exact bytes and reproducing its SHA. The
API normalizes date fields to UTC and loses the original offset: this migration's
client timezone produced +0900 headers. Verify the object ID rather than assuming
that offset for other users. Signed or otherwise unreproducible objects need an
exact supported representation; never relabel a local commit as the remote one.

Preserve existing local branches before switching to equivalent API-created
commits. Pin product-source.json to the actual published product commit and
prepare its inputs again. Keep product/web/IR identities separate and compare
working executable bytes with the committed product closure before imports and
before/after execution; git-diff alone can miss hidden index flags.

Create refs only after reviewing the candidate, check expected existing heads,
and verify refs afterward. Preserve the user's merge/publication authorization
boundaries. For this migration, web must be preserved remotely before the main
removal is integrated; pushing the branch does not authorize site deployment.
Canonical branch responsibilities are specified by ADR 0041 on main.
