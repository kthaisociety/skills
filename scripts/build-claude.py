#!/usr/bin/env python3
"""Build the ais-claude marketplace tree for Claude Code, and check one. No extra packages.

Usage: python3 scripts/build-claude.py build 1.0.0
       python3 scripts/build-claude.py check [TREE]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ".claude-build"

MARKETPLACE_NAME = "ais-claude"
MARKETPLACE_DESCRIPTION = "KTHAIS skills for Claude Code: the ais plugin and its add-on, ais-max."
AUTHOR = "KTHAIS"
PLUGINS = ("ais", "ais-max")
DESCRIPTIONS = {
    "ais": "Write tickets and epics, grill plans into docs, amend conventions, and ready PRs.",
    "ais-max": "Max's TDD ticket chain, explainers and writing rules. Install ais first.",
}


class BuildError(Exception):
    """A check failed before anything was written. The message says which one."""


def build_tree(version, ais=ROOT / "ais", ais_max=ROOT / "ais-max", dest=ROOT / BUILD):
    """Write the ais-claude marketplace tree into dest, replacing any tree already there.

    version: str, required. The release version, of the form X.Y.Z, such as "1.0.0".
    ais: Path, default ROOT / "ais". The ais plugin folder. Read, never written.
    ais_max: Path, default ROOT / "ais-max". The ais-max plugin folder. Read,
        never written.
    dest: Path, default ROOT / BUILD. The folder this call replaces.

    Returns a dict mapping each plugin name in PLUGINS to the list of skill
    folder names written for it, sorted.

    On success dest holds, and holds only:
    - .claude-plugin/marketplace.json, a JSON object with the keys "name"
      (MARKETPLACE_NAME), "owner" ({"name": AUTHOR}), "description"
      (MARKETPLACE_DESCRIPTION) and "plugins", in that order. "plugins" lists
      one entry per plugin in PLUGINS order, each with the keys "name",
      "source" ("./<name>"), "version" (version) and "description"
      (DESCRIPTIONS[name]), in that order.
    - For each plugin, <name>/.claude-plugin/plugin.json, a JSON object with
      the keys "name", "version" (version), "description" (DESCRIPTIONS[name])
      and "author" ({"name": AUTHOR}), in that order.
    - For each plugin, <name>/skills/<skill>/ for every folder directly
      inside that plugin's source folder, copied byte for byte with every
      file or folder whose name starts with "." left out, at any depth. Files
      lying loose in the source folder, outside any skill folder, are not
      copied. So ais-max/.source.json never reaches the tree.

    Every JSON file is indented two spaces, keeps non-ASCII characters as
    written, and ends in a newline. Running it twice with the same version
    and inputs leaves dest byte-identical. Writes nothing outside dest,
    apart from temporary files it deletes before returning.

    Does not check the tree. A skill name in both plugins, or a skill with a
    bad frontmatter, is copied as is, for check_tree to report.

    Raises BuildError, with dest untouched, when:
    - version doesn't match X.Y.Z, where each part is digits only.
    - ais or ais_max is not an existing folder.
    Each message is one line naming the check that failed and the version or
    path that failed it.
    """
    raise NotImplementedError


def check_tree(tree=ROOT / BUILD, claude="claude"):
    """Return every rule the ais-claude tree at tree breaks, as messages.

    tree: Path, default ROOT / BUILD. A tree as build_tree writes it. Read,
        never written.
    claude: str, default "claude". The Claude Code command to run, as a name
        on PATH or a path to an executable. Tests pass a fake.

    Returns a list of str. An empty list means the tree passes. Each message
    is one line, starting with the file or folder it is about, relative to
    tree, then ": " and the rule it breaks. Messages come in this order:
    marketplace problems, then plugin manifest problems in PLUGINS order,
    then skill problems ordered by plugin and then skill folder name, then
    Claude Code's own.

    The rules:
    - .claude-plugin/marketplace.json exists, is a JSON object, and lists
      exactly the plugins in PLUGINS, each once.
    - Each listed plugin's source folder exists in the tree.
    - Each listed plugin's <name>/.claude-plugin/plugin.json exists, is a
      JSON object, and has a "name" equal to the plugin's name.
    - Every version agrees: each marketplace entry's "version" and each
      plugin.json "version" are one and the same X.Y.Z string.
    - Every folder in <plugin>/skills/ holds a SKILL.md whose frontmatter,
      between "---" lines at the top, has a "name" equal to the folder's name
      and a non-empty "description".
    - No skill folder name appears under both plugins. The message names the
      skill once and both plugins.
    - Claude Code accepts the tree. The check runs
      [claude, "plugin", "validate", "--strict", "--json", str(tree)].
      A zero exit adds nothing. A non-zero exit adds one message per error
      and warning in its JSON report, as "claude: <path>: <message>" using
      the report's own path and message. If the output is not that JSON, it
      adds one message holding the last line of stderr.
    - When claude can't be started, such as when it isn't installed, that is
      one message saying so. It is never skipped (ADR-0006).

    When tree is not an existing folder, returns exactly one message saying
    so, and runs nothing.

    Never raises for a problem in the tree. A problem is a message.
    """
    raise NotImplementedError


def main(argv=None):
    """Run a build or a check from the command line.

    argv: list[str] | None, default None, meaning sys.argv[1:]. One of:
        ["build", VERSION]   build_tree(VERSION) with the default folders.
        ["check"]            check_tree() on ROOT / BUILD.
        ["check", TREE]      check_tree(Path(TREE)).

    Returns the process exit code as an int, and never raises BuildError:
    - build, 0 after a build, having printed one line per plugin to stdout,
      in PLUGINS order, as "Wrote <count> skills to <BUILD>/<plugin>".
    - build, 1 when build_tree raised BuildError, having printed
      "error: <message>" to stderr. The build folder is then as it was.
    - check, 0 when check_tree returned no messages, having printed
      "Tree passes" to stdout.
    - check, 1 when it returned messages, having printed each one on its
      own line to stderr, in the order returned.
    - 2 when argv names no known subcommand or has the wrong number of
      arguments, per argparse.

    Build never runs the check. The release runs both, in turn.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
