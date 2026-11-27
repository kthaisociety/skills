# KTHAIS skills

The source repo for the skills KTHAIS ships, and for the plugins built from them for each coding agent.

## Language

**ais**:
The base plugin, owned by this repo: `new-ticket`, `map-epic`, `pr-ticket`, `grill-docs` and `amend-pcr`.
_Avoid_: base skills, core plugin

**ais-max**:
The add-on plugin holding Max's kanban chain and extras, which needs **ais** installed and never repeats a skill **ais** holds.
_Avoid_: max plugin (that is the Custom-skills plugin), full plugin

**Seed**:
The one-time copy of a Custom-skills skill into **ais**, after which this repo alone edits it.
_Avoid_: import, fork

**Sync**:
A run of `scripts/sync-ais-max.py` that rebuilds **ais-max** from one Custom-skills release tag. The scheduled job runs it against the latest tag and opens a PR only when the rebuild leaves a diff.
_Avoid_: update, pull, mirror

**Release repo**:
A repo that holds only the built plugins for one agent, published from this repo.
_Avoid_: mirror, dist repo

## Relationships

- **ais-max** depends on exactly one **ais**
- Each agent has exactly one **Release repo**, holding both **ais** and **ais-max**
- Every skill in **ais** came from one **Seed**; a **Sync** never touches **ais**
- A **Sync** replaces the base-file copies in `ais-max`'s `helper-skill` with the **ais** versions

## Example dialogue

> **Dev:** "Can a member install **ais-max** without **ais**?"
> **Maintainer:** "No. `architect-ticket` in **ais-max** calls `new-ticket`, and only **ais** ships that."

## Flagged ambiguities

- "max" named both the Custom-skills plugin and the add-on built here. Resolved: the add-on here is **ais-max**, and `max` means only the Custom-skills plugin.
