# AGENTS.md

Guidance for AI coding agents working in the `kthaisociety/skills` repository.

This repo is a **skills source** for the [open agent skills ecosystem](https://www.skills.sh/). Consumers install from GitHub with:

```bash
npx skills add kthaisociety/skills --all
```

They do **not** clone this repo into `.agents/` / `.claude/` via ad-hoc `npx skills add` against upstreams. That is a consumer install path, not how this collection is maintained.

## What lives here

| Path | Purpose |
| --- | --- |
| `skills/internal/<name>/SKILL.md` | First-party KTHAIS skills |
| `skills/external/<name>/` | Vendored upstream skills (committed copies) |
| `sources.json` | Manifest + commit pins for external skills |
| `scripts/add-external-skill.mjs` | Add/update one external skill |
| `scripts/sync-external-skills.mjs` | Sync all external skills (or `--check`) |
| `skills.sh.json` | Groupings for the [skills.sh](https://www.skills.sh/) repo page |
| `package.json` | npm scripts for maintainers |

## Skill format (skills.sh / Agent Skills)

Every skill directory must contain `SKILL.md` with YAML frontmatter:

```yaml
---
name: skill-slug
description: What it does and when to use it (agents match on this)
---
```

- `name`: lowercase, hyphens; must match the folder name consumers will install
- `description`: required; used for discovery and invocation
- Optional: `scripts/`, `references/`, other supporting files next to `SKILL.md`

The skills CLI discovers:

1. `skills/internal/<skill>/SKILL.md`
2. `skills/external/<skill>/SKILL.md`
3. Also flat `skills/<skill>/SKILL.md` if present

After changing skills, verify discovery:

```bash
npx skills add . --list
```

## First-party vs external

**First-party** (`skills/internal/*`): edit `SKILL.md` in place. Do not add these to `sources.json`.

**External** (`skills/external/*`): never hand-edit to “improve” upstream content. Change via:

```bash
npm run skill:add -- owner/repo skill-name [source-path]
npm run skill:add -- https://github.com/owner/repo --skill skill-name
npm run skill:remove -- skill-name
npm run skill:sync
```

`sources.json` entries look like:

```json
{
  "name": "frontend-design",
  "repository": "anthropics/skills",
  "path": "skills/frontend-design",
  "destination": "skills/external/frontend-design",
  "commit": "<resolved-sha>"
}
```

Pin to the resolved SHA after add/sync so installs are reproducible.

## Do / don’t

**Do**

- Keep first-party skills focused; put procedural knowledge in `SKILL.md`
- Vendor externals only through the scripts so `sources.json` stays accurate
- Update `skills.sh.json` when adding/removing skills (README stays install-focused, not a skill catalog)
- Prefer `npx skills add kthaisociety/skills` language in docs (skills.sh install UX)

**Don’t**

- Commit `.agents/`, `.claude/`, `.cursor/`, or `skills-lock.json` (local installs; gitignored)
- Run `npx skills add other/repo` expecting that to import files into this Git repo
- Rename a vendored skill folder without updating `sources.json` `destination` / `name`

## Maintainer scripts

```bash
npm run skill:add -- https://github.com/shadcn/ui --skill shadcn
npm run skill:add -- https://github.com/vercel-labs/agent-skills --skill vercel-react-best-practices
npm run skill:remove -- shadcn
npm run skill:sync
npm run skill:check
npm run skills:install
```

CI: `.github/workflows/update-external-skills.yml` syncs weekly and opens a PR.

## Docs to keep in sync

When adding, removing, or renaming a skill:

1. Skill directory + valid `SKILL.md`
2. `sources.json` (external only)
3. [skills.sh.json](./skills.sh.json) groupings
4. This file if layout or workflow changes

## Ecosystem links

- Directory: https://www.skills.sh/
- CLI: https://github.com/vercel-labs/skills
- Customize repo page: https://skills.sh/docs/customize
