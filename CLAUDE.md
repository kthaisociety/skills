# CLAUDE.md

This repo is the source for the KTHAIS plugins **ais** and **ais-max**, built per agent and published to the release repos `skills-claude`, `skills-codex` and `skills-agy`.

- Edit `ais/` by hand. `ais-max/` is written only by `scripts/sync-ais-max.py`.
- Run `python3 -m unittest discover -s tests` after changing `scripts/` or `install.sh`.

Read [AGENTS.md](./AGENTS.md) before changing anything. It covers the layout, the scripts and workflows, and the records in `CONTEXT.md`, `docs/adr/` and `docs/pcr/`.
