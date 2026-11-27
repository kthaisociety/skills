# ADR-0005: The sync script rebuilds ais-max on every run

**Decision:** `scripts/sync-ais-max.py` MUST rebuild `ais-max/` on every run, and MUST NOT skip a run because the tag in `ais-max/.source.json` matches the tag it was given.

**Reason:** Stopping early when the recorded tag matches was weighed and lost. Under ADR-0003 an edit to an **ais** base file has to reach `ais-max` on the next sync, and a script that skips on an unchanged tag would leave that edit out until Custom-skills cuts a new tag. Rebuilding costs one clone, and the output is byte-identical when nothing changed, so a rerun with no change still leaves no diff.

**Consequence:** Deciding whether a sync is due belongs to whatever calls the script, such as the scheduled job. A caller that compares only tags misses **ais** base-file edits, so it has to rerun the script and look at the diff. An "already up to date" shortcut added to the script breaks this record.

**Scope:** `scripts/sync-ais-max.py`, `sync`

**Date:** 2026-11-27
