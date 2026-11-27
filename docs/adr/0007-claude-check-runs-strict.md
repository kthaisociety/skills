# ADR-0007: The Claude check treats Claude Code's warnings as failures

**Decision:** The Claude tree check MUST run `claude plugin validate` with `--strict`, so any warning fails the tree.

**Reason:** Running it lenient, where only errors fail, was weighed and lost. Claude Code reports some real faults only as warnings, such as a marketplace entry whose version disagrees with its `plugin.json`, and a warning printed in a passing release log goes unread.

**Consequence:** The build has to write every field Claude Code warns about when it's missing, such as a marketplace description and each plugin's `author`. A new warning in a later Claude Code fails the release until the build writes the missing field. Dropping `--strict` to get a release through breaks this record. Fix the tree or amend this record instead.

**Scope:** `scripts/build-claude.py`, `check_tree`

**Date:** 2026-11-27
