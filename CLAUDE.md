# CLAUDE.md

This repository is the KTHAIS managed [Agent Skills](https://www.skills.sh/) collection (`kthaisociety/skills`).

Read and follow [AGENTS.md](./AGENTS.md) for full maintainer guidance. Summary:

## Consumer install

```bash
npx skills add kthaisociety/skills --all
```

## Layout

- First-party skills: `skills/internal/<name>/SKILL.md`
- Vendored external skills: `skills/external/<name>/` (pinned in `sources.json`)
- Do not commit local agent installs (`.agents/`, `.claude/`, `skills-lock.json`)

## Maintaining external skills

```bash
npm run skill:add -- owner/repo skill-name [source-path]
npm run skill:remove -- skill-name
npm run skill:sync
npm run skill:check
```

Never use `npx skills add` against other repos to populate this Git tree — that installs into agent directories, not into `skills/external/`.

## When changing skills

Update `SKILL.md` and `skills.sh.json` together. For externals, only change files via the sync scripts so commit pins stay correct.

Verify discovery with:

```bash
npx skills add . --list
```
