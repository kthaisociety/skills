# KTHAIS skills

The skills KTHAIS ships to its coding agents, packed as two plugins for Claude Code, Codex and Antigravity.

- **ais** is the base plugin. It files tickets and epics, opens PRs, and keeps a repo's glossary, ADRs and PCRs.
- **ais-max** is an add-on with Max's kanban chain and some writing and explaining extras. It needs **ais** installed first, because its skills call skills that only **ais** ships.

## Install

Each agent has its own release repo, and that repo's README has the install and update steps for that agent.

| Agent | Release repo |
| --- | --- |
| Claude Code | [kthaisociety/skills-claude](https://github.com/kthaisociety/skills-claude) |
| Codex | [kthaisociety/skills-codex](https://github.com/kthaisociety/skills-codex) |
| Antigravity | [kthaisociety/skills-agy](https://github.com/kthaisociety/skills-agy) |

Install **ais** first, then **ais-max** if you want it.

## Skills in ais

| Skill | What it does |
| --- | --- |
| `new-ticket` | Grills standalone work down to what, not how, and files it as a GitHub issue with an effort level. |
| `map-epic` | Files an epic and grills it into task, research and prototype sub-issues, breadth first. |
| `pr-ticket` | Pushes a finished branch and rewrites its PR into a body a reviewer can read cold. |
| `grill-docs` | Grills you on a plan or decision and writes the settled terms, ADRs and PCRs to the repo. |
| `amend-pcr` | Weighs a change to a project convention record and amends or retires it once you approve. |

## Skills in ais-max

| Skill | What it does |
| --- | --- |
| `brainstorming` | Grills a raw idea until it dies or holds, then names the skill that should pick it up. |
| `architect-ticket` | Turns a ticket into a red branch of interface stubs and failing acceptance tests. |
| `implement-ticket` | Fills in the stubs on a red branch until the acceptance tests pass. |
| `refactor-ticket` | Checks a green branch against its ticket and refactors the code under it. |
| `unit-test-ticket` | Folds the acceptance tests into the unit suite and tidies the changed tests. |
| `execute-ticket` | Runs a small ticket from red to refactored in one unattended session. |
| `review-diff` | Reviews a branch's diff against its ticket and the project records, and fixes what it finds. |
| `pro-con` | Weighs the pros and cons of a decision and commits to a recommendation. |
| `unslop` | Cuts AI tells from any writing. |
| `gloss-me` | Explains each term missing from your personal glossary before using it. |
| `eli5` | Explains a topic to a curious middle schooler. |
| `eli10` | Explains a topic to a sharp high schooler. |
| `talk-to-middleschooler` | Words an explanation for a complete beginner. Other skills call it. |
| `talk-to-highschooler` | Words an explanation for a capable learner new to the field. Other skills call it. |
| `helper-skill` | Carries copies of **ais** files the kanban skills read. You never run it. |

## Try skills from a clone

Developers can copy the skills from a local clone into an agent before a release:

```bash
git clone https://github.com/kthaisociety/skills.git
cd skills
./install.sh AGENT PLUGIN
```

`AGENT` is `claude`, `codex` or `agy`. `PLUGIN` is `ais` or `ais-max`, and `ais-max` copies `ais` too. The script prints what it will add, update and remove, and asks before writing. It copies rather than links, so rerun it after each edit or pull. `./install.sh --help` lists every option.

Maintainers, see [AGENTS.md](./AGENTS.md).

## License

See [LICENSE](./LICENSE). Skills that came from elsewhere keep their own license file.
