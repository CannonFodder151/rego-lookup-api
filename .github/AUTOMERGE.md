# Approval-gated automerge

`CannonFodder151` private repos run on the free GitHub plan, where
`allow_auto_merge` cannot be enabled (GitHub Pro required). `.github/workflows/automerge.yml`
replaces it: the workflow performs the squash-merge itself, deterministically,
once every gate below passes. Same behaviour as GitHub native auto-merge,
no plan dependency.

Ported from `CannonFodder151/autobrain-shop-website` (merge `9b3e86f3`, PR #22).

## Gates

A PR is squash-merged only when **all** of these hold:

| Gate | Check |
| --- | --- |
| Default branch | `.base.ref` equals the repo default branch |
| Not a draft | `.draft` is not `true` |
| Mergeable | `.mergeable_state` is `clean` |
| Approved | latest review from a non-author is `APPROVED` |
| No hold | no `hold` label on the PR |
| Green | every status check is `SUCCESS`, `SKIPPED` or `NEUTRAL` |

Anything else logs `skip: <reason>` and exits 0. The workflow never force-merges.

## Triggers

`pull_request_review` (submitted), `pull_request` (ready_for_review),
`check_run` (completed), `status`. The job is skipped for its own `check_run`
named `automerge` to avoid recursion.

## Hold

```bash
gh pr edit <PR> --add-label hold
```

Dismisses the merge without closing the PR.

## Review identity caveat

The approval gate requires a review from an account **other than the PR author**.
Agents in this company author PRs as `CannonFodder151`, so an approval submitted
from that same account is filtered out and the PR will not auto-merge.
Keep that in mind when the only available identity is also the author.

Refs: AUT-2230, AUT-5328, AUT-5336