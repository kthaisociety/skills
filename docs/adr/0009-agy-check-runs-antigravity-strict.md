# ADR-0009: The Antigravity check fails unless agy validates each plugin strictly

**Decision:** The Antigravity tree check MUST run `agy plugin validate --strict` on each plugin subfolder, and MUST report a problem, and so fail the tree, when it can't run `agy`.

**Reason:** Two alternatives were weighed and lost. Skipping agy's validation when `agy` isn't installed, and passing on this repo's own rules, lets a release go out that Antigravity never read. Running it lenient, where only errors fail, lets real faults through, such as a manifest key Antigravity ignores, which agy reports only as a warning that nobody reads in a passing log. This matches the Claude check's ADR-0006 and ADR-0007.

**Consequence:** Every place that runs the check, such as the release workflow, has to install agy first with its native installer. Tests hand the check a fake `agy` instead of skipping. A new warning in a later agy fails the release until the build writes what it asks for. A skip or fallback for a missing `agy`, or dropping `--strict` to get a release through, breaks this record.

**Scope:** `scripts/build-agy.py`, `check_tree`

**Date:** 2026-11-27
