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
npx skills add kthaisociety/skills --skill kthais-nextjs
```

Browse this collection on [skills.sh/kthaisociety/skills](https://skills.sh/kthaisociety/skills).

## Available Skills

### kthais-nextjs

Next.js conventions and patterns for KTHAIS projects.

**Use when:**

- Building or modifying Next.js apps in the KTHAIS ecosystem
- Choosing App Router patterns, server vs client components, or project layout

### kthais-code-review

Code review standards for KTHAIS projects.

**Use when:**

- Reviewing pull requests or diffs
- Drafting review feedback for KTHAIS repositories

### frontend-design

Guidance for distinctive, intentional visual design when building new UI or reshaping an existing one.

**Use when:**

- Designing new UI or redesigning an interface
- Choosing typography, palette, layout, or aesthetic direction
- Avoiding generic, templated-looking interfaces

Upstream: [anthropics/skills](https://github.com/anthropics/skills)

### vercel-react-best-practices

React and Next.js performance optimization guidelines from Vercel Engineering.

**Use when:**

- Writing or reviewing React / Next.js code
- Optimizing data fetching, bundle size, or render performance

Upstream: [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) (`skills/react-best-practices`)

### web-design-guidelines

Review UI code for Web Interface Guidelines compliance (accessibility, UX, performance).

**Use when:**

- "Review my UI"
- "Check accessibility"
- "Audit design"
- "Review UX"

Upstream: [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills)

## Usage

Skills are available to your agent after install. The agent loads them when the task matches a skill description.

Examples:

```
Review this PR against KTHAIS standards
```

```
Build this Next.js page using our conventions
```

```
Review my UI for accessibility and design guidelines
```

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
| First-party | Authored here under `skills/<name>/` |
| External | Vendored into `skills/external/<name>/`, pinned by commit in `sources.json` |
| Consumers | Install from this GitHub repo with the skills CLI |

Do **not** populate this repo by running `npx skills add` against other repositories. That installs into agent directories (`.agents/`, `.claude/`, etc.), not into this Git tree.

See [AGENTS.md](./AGENTS.md) for maintainer guidance.

## Skill layout

Each skill is a directory with a `SKILL.md` (YAML frontmatter + instructions), matching the [skills.sh](https://www.skills.sh/) / Agent Skills format:

```text
skills/
├── kthais-nextjs/SKILL.md
├── kthais-code-review/SKILL.md
└── external/
    ├── frontend-design/
    ├── vercel-react-best-practices/
    └── web-design-guidelines/
```

The CLI discovers both flat skills (`skills/<name>/`) and catalog-nested skills (`skills/external/<name>/`).

## Maintainer commands

```bash
# Vendor a new external skill
npm run skill:add -- owner/repo skill-name

# Nonstandard source path
npm run skill:add -- owner/repo local-name path/to/skill

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
