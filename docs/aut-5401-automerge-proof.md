# AUT-5401 automerge proof

E2E evidence that `.github/workflows/automerge.yml` squash-merges a PR
authorised by a Paperclip approval-marker comment, with no human running
`gh pr merge`. The merge commit is authored by `web-flow` (the workflow's
`GITHUB_TOKEN`), not by the PR author.

Run logs and the two refusal/approval cases are recorded on AUT-5401.
