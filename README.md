# @kthais/skills

A collection of [Agent Skills](https://www.skills.sh/) for KTHAIS AI coding agents.

Skills are reusable capabilities that give agents procedural knowledge for specific tasks. Install them with the [skills CLI](https://github.com/vercel-labs/skills).

[![skills.sh](https://skills.sh/b/kthaisociety/skills)](https://skills.sh/kthaisociety/skills)

## Installation

```bash
npx skills add kthaisociety/skills
```

Install everything non-interactively:

```bash
npx skills add kthaisociety/skills --all
```

Or globally:

```bash
npx skills add kthaisociety/skills --all --global --yes
```

Install a single skill:

```bash
npx skills add kthaisociety/skills --skill <skill-name>
```

List skills in this repo:

```bash
npx skills add kthaisociety/skills --list
```

Browse the collection on [skills.sh/kthaisociety/skills](https://skills.sh/kthaisociety/skills).

## Usage

Skills are available to your agent after install. The agent loads them when the task matches a skill description.

## How this repository works

This is a **managed collection**, not a dump of `npx skills add` agent installs.

```text
Upstream repositories
        ↓
sources.json + npm run skill:sync
        ↓
kthaisociety/skills (this repo)
        ↓
npx skills add kthaisociety/skills --all
```

| Layer | Role |
| --- | --- |
| First-party | Authored here under `skills/internal/<name>/` |
| External | Vendored into `skills/external/<name>/`, pinned by commit in `sources.json` |
| Consumers | Install from this GitHub repo with the skills CLI |

Do **not** populate this repo by running `npx skills add` against other repositories. That installs into agent directories (`.agents/`, `.claude/`, etc.), not into this Git tree.

See [AGENTS.md](./AGENTS.md) for maintainer guidance.

## Skill layout

Each skill is a directory with a `SKILL.md` (YAML frontmatter + instructions), matching the [skills.sh](https://www.skills.sh/) / Agent Skills format:

```text
skills/
├── internal/
│   └── <first-party-skill>/SKILL.md
└── external/
    └── <vendored-skill>/
```

The CLI discovers catalog-nested skills under `skills/internal/` and `skills/external/`.

## Maintainer commands

```bash
# Vendor a new external skill (discovers nested paths like skills/productivity/<name>)
npm run skill:add -- owner/repo skill-name
npm run skill:add -- https://github.com/owner/repo --skill skill-name

# Override source path when needed
npm run skill:add -- owner/repo local-name path/to/skill

# Remove a vendored external skill
npm run skill:remove -- skill-name
npm run skill:remove -- --skill skill-name

# Update vendored skills to latest upstream commits
npm run skill:sync

# Check for updates without writing (exit 1 if outdated)
npm run skill:check

# Install this collection locally (for testing discovery)
npm run skills:install
```

A weekly GitHub Action runs `skill:sync` and opens a PR when upstream skills change.

## License

See [LICENSE](./LICENSE). Vendored skills keep their upstream licenses.
