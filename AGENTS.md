# AGENTS.md

Guidance for maintainers of `kthaisociety/skills` and their agents. The member-facing description of the plugins and skills lives in [README.md](./README.md).

This repo is the source for two plugins, **ais** and **ais-max**. Build scripts turn them into one plugin tree per agent, and a release publishes each tree to that agent's release repo (`skills-claude`, `skills-codex`, `skills-agy`). Members install only from the release repos. Developers can also run `install.sh` from a clone (ADR-0004).

## Records to read first

- [CONTEXT.md](./CONTEXT.md) defines the project's terms: ais, ais-max, seed, sync, release repo, plugin tree, local install, release tag. Use them as written there.
- [docs/adr/](./docs/adr/) holds the decisions and the options that lost. Read the ADRs on the part you are changing before you change it.
- [docs/pcr/](./docs/pcr/) holds the project conventions. PCR-0001 keeps every script on the Python standard library.

## Source layout and who writes it

| Path | Written by |
| --- | --- |
| `ais/<skill>/` | Maintainers, by hand, only in this repo. Custom-skills never overwrites it (ADR-0002). |
| `ais-max/<skill>/` | Only the sync. Hand edits are lost on the next sync. Change the skill in Custom-skills and cut a tag there. |
| `ais-max/.source.json` | Only the sync. It records the Custom-skills tag and commit `ais-max` came from. |
| `ais-max/helper-skill/` | Only the sync. It holds copies of base files from `ais` (`ticket-shapes.md`, `RECORD-FORMAT.md`, `ticket-pr.md`), taken from this repo's `ais`, not from Custom-skills. |
| `scripts/` | Maintainers. One script per job, with its usage in the docstring. |
| `tests/` | Maintainers. One test file per script. |
| `.github/workflows/` | Maintainers. Each workflow's header comment says what it guarantees. |
| `install.sh` | Maintainers. Its header comment documents every option and the order of a run. |

Each skill is a folder with a `SKILL.md` whose frontmatter `name` matches the folder name and has a `description`. When you add, remove or rename an `ais` skill, update its row in the README's skill table too.

## Scripts and workflows

Run the tests after any change to `scripts/` or `install.sh`:

```bash
python3 -m unittest discover -s tests
```

Rebuild `ais-max` from one Custom-skills tag:

```bash
python3 scripts/sync-ais-max.py v2.1.0
```

Build and check each agent's plugin tree. Each build writes a git-ignored folder (`.claude-build/`, `.codex-build/`, `.agy-build/`) and each check reads only that folder. The Claude check needs Claude Code installed and the Antigravity check needs `agy` (ADR-0006, ADR-0009).

```bash
python3 scripts/build-claude.py build 1.0.0 && python3 scripts/build-claude.py check
python3 scripts/build-codex.py build 1.0.0 && python3 scripts/build-codex.py check
python3 scripts/build-agy.py build 1.0.0 && python3 scripts/build-agy.py check
```

Copy skills from your clone into one agent, to try them before a release. `AGENT` is `claude`, `codex` or `agy`, and `PLUGIN` is `ais` or `ais-max`:

```bash
./install.sh AGENT PLUGIN
```

Plan the next version from the commit titles since the last `vX.Y.Z` tag:

```bash
python3 scripts/plan-release.py
```

Two workflows run in GitHub Actions:

- **Release** (`release.yml`) starts by hand on `main` from the Actions tab. It runs the tests, plans the version, then builds and checks all three trees. Dry run is on by default and changes nothing. Publishing to the release repos isn't set up yet.
- **Sync ais-max** (`sync-ais-max.yml`) runs daily and by hand. When the newest Custom-skills `vX.Y.Z` tag differs from the one in `ais-max/.source.json`, it syncs, runs the tests and the three checks, and opens a PR (ADR-0011). It needs "Allow GitHub Actions to create and approve pull requests" on, under Settings, Actions, General.

## Commits and PRs

Commit titles follow Conventional Commits, since the release planner bumps the version from them: `!` after any type is a major bump, `feat:` a minor, and anything else a patch.
