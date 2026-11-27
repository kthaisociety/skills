#!/usr/bin/env python3
"""Build the ais-codex marketplace tree for Codex, and check one. No extra packages.

Usage: python3 scripts/build-codex.py build 1.0.0
       python3 scripts/build-codex.py check [TREE]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
BUILD = ".codex-build"

MARKETPLACE_NAME = "ais-codex"
MARKETPLACE_DISPLAY_NAME = "KTHAIS skills for Codex"
AUTHOR = "KTHAIS"
PLUGINS = ("ais", "ais-max")
DESCRIPTIONS = {
    "ais": "Write tickets and epics, grill plans into docs, amend conventions, and ready PRs.",
    "ais-max": "Max's TDD ticket chain, explainers and writing rules. Install ais first.",
}


class BuildError(Exception):
    """A check failed before anything was written. The message says which one."""


def build_tree(version, ais=ROOT / "ais", ais_max=ROOT / "ais-max", dest=ROOT / BUILD):
    """Write the ais-codex marketplace tree into dest, replacing any tree already there.

    version: str, required. The release version, of the form X.Y.Z, such as "1.0.0".
    ais: Path, default ROOT / "ais". The ais plugin folder. Read, never written.
    ais_max: Path, default ROOT / "ais-max". The ais-max plugin folder. Read,
        never written.
    dest: Path, default ROOT / BUILD. The folder this call replaces.

    Returns a dict mapping each plugin name in PLUGINS to the list of skill
    folder names written for it, sorted.

    On success dest holds, and holds only:
    - .agents/plugins/marketplace.json, a JSON object with the keys "name"
      (MARKETPLACE_NAME), "interface" ({"displayName":
      MARKETPLACE_DISPLAY_NAME}) and "plugins", in that order. "plugins"
      lists one entry per plugin in PLUGINS order, each with the keys
      "name", "source" ({"source": "local", "path": "./<name>"}), "policy"
      ({"installation": "AVAILABLE", "authentication": "ON_INSTALL"}) and
      "category" ("Productivity"), in that order. It carries no version.
    - For each plugin, <name>/.codex-plugin/plugin.json, a JSON object with
      the keys "name", "version" (version), "description" (DESCRIPTIONS[name])
      and "author" ({"name": AUTHOR}), in that order.
    - For each plugin, <name>/skills/<skill>/ for every folder directly
      inside that plugin's source folder, converted from it:
      - Every file or folder whose name starts with "." is left out, at any
        depth. Files lying loose in the source folder, outside any skill
        folder, are not copied. So ais-max/.source.json never reaches the
        tree.
      - SKILL.md's frontmatter keeps only its "name" and "description"
        lines, in their source order.
      - In every .md file, each "/<skill>" mention of a skill in either
        plugin becomes "$<owner>:<skill>", where owner is the plugin that
        holds it, per skill_owners. A "/<word>" that names no skill in
        either plugin stays as written.
      - A skill whose source frontmatter has "disable-model-invocation: true"
        gets agents/openai.yaml, holding exactly
        "policy:\\n  allow_implicit_invocation: false\\n".
      - Every other file is copied byte for byte.

    Every JSON file is indented two spaces, keeps non-ASCII characters as
    written, and ends in a newline. Running it twice with the same version
    and inputs leaves dest byte-identical. Writes nothing outside dest,
    apart from temporary files it deletes before returning.

    Does not run check_tree. The release runs both, in turn.

    Raises BuildError, with dest untouched, when:
    - version doesn't match X.Y.Z, where each part is digits only. Raised
      before reading ais or ais_max.
    - ais or ais_max is not an existing folder.
    - a skill folder name appears in both plugins, per skill_owners.
    - a "../<skill>/<file>" reference in a .md file points at a skill
      outside the referring file's own plugin, or at a file that doesn't
      exist in that skill's source folder.
    Each message is one line naming the check that failed and the version,
    path, skill or reference that failed it.
    """
    raise NotImplementedError


def skill_owners(ais=ROOT / "ais", ais_max=ROOT / "ais-max"):
    """Return which plugin owns each skill, read from the plugin source folders.

    ais: Path, default ROOT / "ais". The ais plugin folder. Read, never written.
    ais_max: Path, default ROOT / "ais-max". The ais-max plugin folder. Read,
        never written.

    Returns a dict mapping each skill name to the name of the plugin in
    PLUGINS that holds it. A skill is a folder directly inside a plugin
    folder whose name doesn't start with ".". Loose files and hidden folders
    are not skills. The dict's order is PLUGINS order, then skill name.

    Raises BuildError when:
    - ais or ais_max is not an existing folder. The message names the path.
    - a skill name is a folder in both plugins. The message names the skill
      once and both plugins. When several names clash, it names the first
      in sorted order.
    """
    raise NotImplementedError


def check_tree(tree=ROOT / BUILD):
    """Return every rule the ais-codex tree at tree breaks, as messages.

    tree: Path, default ROOT / BUILD. A tree as build_tree writes it. Read,
        never written. The check reads only the tree, never the plugin
        source folders, so it can run on a tree fetched from the release
        repo.

    Returns a list of str. An empty list means the tree passes. Each message
    is one line, starting with the file or folder it is about, relative to
    tree, then ": " and the rule it breaks. Messages come in this order:
    marketplace problems, then plugin manifest problems in PLUGINS order,
    then skill problems ordered by plugin and then skill folder name, and
    within one skill by file path.

    The rules:
    - .agents/plugins/marketplace.json exists, is a JSON object, has "name"
      equal to MARKETPLACE_NAME, and lists exactly the plugins in PLUGINS,
      each once.
    - Each listed plugin's "source" is {"source": "local", "path":
      "./<name>"}, and that folder exists in the tree.
    - Each plugin's <name>/.codex-plugin/plugin.json exists, is a JSON
      object, has "name" equal to the plugin's name, a non-empty
      "description", and a "version" of the form X.Y.Z.
    - Both plugin.json files carry one and the same version.
    - No file or folder under <plugin>/skills/ has a name starting with ".".
    - Every folder in <plugin>/skills/ holds a SKILL.md whose frontmatter,
      between "---" lines at the top, has exactly the keys "name" and
      "description", with "name" equal to the folder's name and
      "description" non-empty.
    - No skill folder name appears under both plugins. The message names the
      skill once and both plugins.
    - No .md file holds a "/<skill>" mention of a skill folder in the tree.
    - Every "$<plugin>:<skill>" mention in a .md file names a plugin in
      PLUGINS and a skill folder under that plugin in the tree.
    - Every "../<skill>/<file>" reference in a .md file resolves to an
      existing file inside the same plugin's skills folder.
    - Every agents/openai.yaml in a skill folder holds exactly
      "policy:\\n  allow_implicit_invocation: false\\n".

    When tree is not an existing folder, returns exactly one message saying
    so, and checks nothing else.

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
