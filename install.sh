#!/usr/bin/env bash
# Copy the ais or ais-max skills from this clone into one coding agent's
# skills folder. For developers only: members install the plugins from the
# release repos (ADR-0004). Copies, never symlinks (ADR-0011).
#
# Usage: ./install.sh [--yes] [AGENT] [PLUGIN]
#
#   AGENT    claude   Claude Code   ~/.claude/skills
#            agy      Antigravity   ~/.gemini/config/skills
#            codex    Codex         ~/.agents/skills
#   PLUGIN   ais      every skill in ais/
#            ais-max  every skill in ais-max/, and every skill in ais/ too,
#                     since ais-max needs ais
#   --yes    apply the plan without asking. Flags may come before, between
#            or after AGENT and PLUGIN.
#   -h, --help  print this usage to stdout and exit 0
#
# Every folder is resolved from $HOME, so pointing HOME elsewhere moves all
# three targets.
#
# Ownership. Every skill folder this script writes holds a file named
# .ais-install. A folder in the agent's skills folder is "ours" when it holds
# that file, whichever clone wrote it, and is never ours otherwise. The script
# only ever replaces or removes folders that are ours.
#
# A run, in order:
#   1. Missing AGENT or PLUGIN: on a terminal (stdin and stdout both ttys) it
#      asks for the agent, then the plugin. Each prompt takes the name or its
#      number in the list, and asks again on anything else. Without a
#      terminal it prints this usage to stderr and exits 1.
#   2. Reads every skill folder directly inside the chosen plugin folders,
#      skipping names that start with ".". A skill whose SKILL.md is missing,
#      or whose frontmatter lacks a name or a description, or whose name
#      differs from its folder name, is reported on stderr as
#      "error: <plugin>/<skill>: <what is wrong>" and not copied.
#   3. For codex only, runs `python3 scripts/build-codex.py local` and copies
#      from .codex-local/<skill> instead of the plugin folder. When python3 is
#      missing or the build fails, it prints why on stderr, writes nothing
#      and exits 1.
#   4. Prints the plan, one line per folder, adds first, then updates, then
#      removals, each group sorted by skill name:
#        "  + <skill>"   no folder of that name yet, will be copied
#        "  ~ <skill>"   ours, will be replaced by a fresh copy
#        "  - <skill>"   ours, but no folder of that name exists in ais/ or
#                        ais-max/ of this clone, so will be removed. This holds
#                        whichever PLUGIN was chosen.
#      A folder of a valid skill's name that is not ours goes on stderr as
#      "warning: <path> is not from install.sh, skipping" and is left alone.
#      When the plan is empty it prints "Nothing to change" and exits.
#   5. Asks "Apply? [y/N] " on a terminal. Anything but y or Y writes nothing,
#      prints "Nothing written" and ends the run. Without a terminal it applies
#      only with --yes, and otherwise writes nothing and exits 1.
#   6. Applies the plan. Each copy holds every file of the source skill folder
#      except those on a path with a part starting with ".", plus .ais-install.
#      A replaced folder holds nothing from its earlier copy. Prints one line
#      per folder touched: "added <path>", "updated <path>" or
#      "removed <path>", where path is the folder's full path.
#
# Exit status: 1 when any skill was invalid, any folder was skipped as not
# ours, an argument was unknown, or step 1, 3 or 5 stopped the run without a
# terminal. 0 otherwise, which includes an empty plan and a declined one. An
# unknown AGENT, PLUGIN or flag prints "error: <what>" and the usage on
# stderr, and writes nothing.

set -euo pipefail

echo "install.sh: not implemented" >&2
exit 1
