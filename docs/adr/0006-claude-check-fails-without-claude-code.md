# ADR-0006: The Claude check fails when Claude Code can't validate the tree

**Decision:** The Claude tree check MUST report a problem, and so fail the tree, when it can't run `claude plugin validate`, and MUST NOT pass a tree on this repo's own rules alone.

**Reason:** Skipping Claude Code's validation when `claude` isn't installed, and passing on the repo's own rules, was weighed and lost. A check that quietly does half its job lets a release go out that Claude Code never read, and the gap shows only when a member's install breaks.

**Consequence:** Every place that runs the check, such as the release workflow, has to install Claude Code first. Its native installer needs no Node, so CI stays Python plus one install step. Tests hand the check a fake `claude` command instead of skipping. A skip or fallback added for a missing `claude` breaks this record.

**Scope:** `scripts/build-claude.py`, `check_tree`

**Date:** 2026-11-27
