# ADR-0003: ais-max reads the ais formats, not Custom-skills'

**Decision:** The sync MUST replace every base-file copy in `ais-max`'s `helper-skill` (`ticket-shapes.md`, `RECORD-FORMAT.md`, `ticket-pr.md`) with the file from the matching **ais** skill.

**Reason:** Keeping Custom-skills' copies and failing CI when they differ from **ais** was weighed and lost. An **ais-max** user writes tickets, records and PRs with **ais**, so the chain has to read those shapes, and a check would only block syncs that the override fixes anyway.

**Consequence:** Changing a format in **ais** changes what the **ais-max** chain reads from the next sync on. Custom-skills' own copies of these files never ship here, and a hand edit to them in `ais-max` is lost on the next sync.

**Date:** 2026-11-26
