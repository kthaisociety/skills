# ADR-0002: ais never follows Custom-skills after its seed

**Decision:** The sync from Custom-skills MUST NOT write to any **ais** skill; after the seed, **ais** skills change only through commits to this repo.

**Reason:** Syncing **ais** from Custom-skills along with **ais-max** was weighed and lost. KTHAIS owns its base set, and Custom-skills serves people outside KTHAIS on its own schedule, so a change made for one audience must not overwrite the other's.

**Consequence:** A fix made to a base skill in Custom-skills does not reach **ais** unless someone ports it here by hand. A sync job whose file list includes an **ais** skill is a bug.

**Date:** 2026-11-26
