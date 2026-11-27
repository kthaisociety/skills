# ADR-0011: The scheduled sync decides on tags alone

**Decision:** The scheduled sync job MUST decide whether to sync by comparing the newest `vX.Y.Z` tag on Custom-skills with the tag in `ais-max/.source.json`, and MUST NOT rerun the sync on a matching tag to look for other changes.

**Reason:** Rerunning the sync every day and opening a PR whenever it leaves a diff was weighed and lost. The only diff a matching tag can leave is an **ais** base-file edit, and keeping those in step with `ais` belongs to an overwrite that runs on every merge to main, not to a daily job. A sync PR is also named after the tag it brings in, and a tag that hasn't moved gives it nothing to name.

**Consequence:** The scheduled job opens a PR only when Custom-skills cuts a new release tag. Base-file copies in `ais-max/helper-skill` reach main through the merge-time overwrite, or through `test_helper_skill_matches_ais` until that overwrite exists. A scheduled job that syncs on a matching tag, or that opens a PR for a diff no new tag caused, breaks this record.

**Scope:** `.github/workflows/sync-ais-max.yml`, `scripts/scheduled-sync.py`

**Date:** 2026-11-27
