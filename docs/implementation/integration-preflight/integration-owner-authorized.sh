#!/usr/bin/env bash
# NOT EXECUTED by this task. Requires separate owner authorization of all four merges AND Pages.
set -euo pipefail
: "${OWNER_AUTHORIZED_INTEGRATION_AND_PAGES:?Set only after explicit owner authorization of PR71,70,72,73 and Pages}"
test "$OWNER_AUTHORIZED_INTEGRATION_AND_PAGES" = yes
repo=TakashiSasaki/git-repo-db
assert_eq() { test "$1" = "$2" || { echo "Mismatch: expected $2, actual $1" >&2; exit 1; }; }
assert_no_new_protection() {
  # Fail closed on policy change; do not enqueue, auto-merge or bypass protections.
  assert_eq "$(gh api "repos/$repo/branches/main" --jq .protected)" false
  assert_eq "$(gh api "repos/$repo/rulesets" --jq length)" 0
}
assert_head() {
  assert_eq "$(gh pr view "$1" -R "$repo" --json state --jq .state)" OPEN
  assert_eq "$(gh pr view "$1" -R "$repo" --json headRefOid --jq .headRefOid)" "$2"
  assert_eq "$(gh pr view "$1" -R "$repo" --json baseRefName --jq .baseRefName)" "$3"
  assert_eq "$(gh pr view "$1" -R "$repo" --json mergeable --jq .mergeable)" MERGEABLE
}
assert_eq "$(gh repo view --json nameWithOwner --jq .nameWithOwner)" "$repo"
assert_eq "$(git remote get-url origin)" "https://github.com/$repo.git"
git fetch origin refs/heads/main:refs/remotes/origin/main refs/heads/fix/core-only-schema-test:refs/remotes/origin/fix/core-only-schema-test refs/heads/feat/implementation-boundary-spikes:refs/remotes/origin/feat/implementation-boundary-spikes refs/heads/feat/p1-four-store-schema-contracts:refs/remotes/origin/feat/p1-four-store-schema-contracts refs/heads/fix/p1-intrinsic-provenance:refs/remotes/origin/fix/p1-intrinsic-provenance
assert_eq "$(git rev-parse origin/main)" 57de60b65c2ef29420a885b0c2102dc90e11fa75
assert_eq "$(git rev-parse 'origin/main^{tree}')" 20d4b5bc6137a66e026748f8aa2eef2afced18d5
assert_no_new_protection
assert_head 71 155645c03417905fcb1a6485e916c10aef371318 main
assert_head 70 eb84be9b2061b026ad82b780cc95e062928f838a main
assert_head 72 67e8be65c3061b494c2c7373e2fd151398435f62 feat/implementation-boundary-spikes
assert_head 73 06a4ccd432476af15ee942e8cfcd9fbdf42357c7 feat/p1-four-store-schema-contracts
# Require ALL current checks green before starting; especially final PR73 Pages.
for number in 71 70 72 73; do
  gh pr checks "$number" -R "$repo" --watch
 done
current_expected_main=57de60b65c2ef29420a885b0c2102dc90e11fa75
merge_one() {
  local number=$1 feature=$2 expected_base_tree=$3 expected_result_tree=$4
  assert_no_new_protection
  assert_head "$number" "$feature" main
  gh pr checks "$number" -R "$repo" --watch
  git fetch origin refs/heads/main:refs/remotes/origin/main
  assert_eq "$(git rev-parse origin/main)" "$current_expected_main"
  assert_eq "$(git rev-parse 'origin/main^{tree}')" "$expected_base_tree"
  git fetch origin "refs/pull/$number/merge"
  assert_eq "$(git rev-parse FETCH_HEAD^1)" "$current_expected_main"
  assert_eq "$(git rev-parse FETCH_HEAD^2)" "$feature"
  assert_eq "$(git rev-parse 'FETCH_HEAD^{tree}')" "$expected_result_tree"
  gh pr merge "$number" -R "$repo" --merge --match-head-commit "$feature"
  git fetch origin refs/heads/main:refs/remotes/origin/main
  assert_eq "$(git rev-parse origin/main^1)" "$current_expected_main"
  assert_eq "$(git rev-parse origin/main^2)" "$feature"
  assert_eq "$(git rev-parse 'origin/main^{tree}')" "$expected_result_tree"
  git merge-base --is-ancestor "$feature" origin/main
  current_expected_main=$(git rev-parse origin/main)
}
retarget_related_after_dependency() {
  local number=$1 expected_previous_base=$2
  local actual_base
  actual_base=$(gh pr view "$number" -R "$repo" --json baseRefName --jq .baseRefName)
  if test "$actual_base" = "$expected_previous_base"; then
    gh api "repos/$repo/pulls/$number" --method PATCH -f base=main >/dev/null
  else
    assert_eq "$actual_base" main
  fi
  # If GitHub reports UNKNOWN during recalculation, rerun the assertions later.
  # Never weaken head/tree/check assertions to force progress.
}
merge_one 71 155645c03417905fcb1a6485e916c10aef371318 20d4b5bc6137a66e026748f8aa2eef2afced18d5 e0ff950e755bc5b9fed18cecc83f26625434ffcc
merge_one 70 eb84be9b2061b026ad82b780cc95e062928f838a e0ff950e755bc5b9fed18cecc83f26625434ffcc e3bf1f0aeb3e0f0f16c445ced9f2ef7c6896f5c9
retarget_related_after_dependency 72 feat/implementation-boundary-spikes
merge_one 72 67e8be65c3061b494c2c7373e2fd151398435f62 e3bf1f0aeb3e0f0f16c445ced9f2ef7c6896f5c9 aea20a9aa4ff178b54119936a121fde761bcd001
retarget_related_after_dependency 73 feat/p1-four-store-schema-contracts
merge_one 73 06a4ccd432476af15ee942e8cfcd9fbdf42357c7 aea20a9aa4ff178b54119936a121fde761bcd001 819178212290bc8473bbc31e4a78e95bf125ebc0
for feature in 155645c03417905fcb1a6485e916c10aef371318 eb84be9b2061b026ad82b780cc95e062928f838a 67e8be65c3061b494c2c7373e2fd151398435f62 06a4ccd432476af15ee942e8cfcd9fbdf42357c7; do
  git merge-base --is-ancestor "$feature" origin/main
done
# Existing main push workflows run normally. This script dispatches none.
gh run list -R "$repo" --branch main --limit 10
