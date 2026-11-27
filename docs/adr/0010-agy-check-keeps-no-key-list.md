# ADR-0010: agy owns the Antigravity manifest schema

**Decision:** The Antigravity build script MUST NOT keep its own list of the keys Antigravity's `plugin.json` allows. A key outside the schema fails the tree through agy's strict validation alone.

**Reason:** Porting Custom-skills' hand-written list of schema keys was weighed and lost. agy knows its own schema, and a copied list drifts as agy changes: `category` was added to agy after Custom-skills wrote its list of 14. Under ADR-0009 agy already fails an unknown key, so a second list adds only a second place to update.

**Consequence:** The check's own rules cover only what agy doesn't check: kebab-case plugin names, skill frontmatter, and a skill in both plugins. A key list added back to the script breaks this record. If agy stops warning on unknown keys, amend this record before adding one.

**Scope:** `scripts/build-agy.py`, `check_tree`

**Date:** 2026-11-27
