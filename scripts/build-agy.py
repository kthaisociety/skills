#!/usr/bin/env python3
"""Build the ais-agy plugin tree for Antigravity, and check one. No extra packages.

Usage: python3 scripts/build-agy.py build 1.0.0
       python3 scripts/build-agy.py check [TREE]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ".agy-build"

PLUGINS = ("ais", "ais-max")
DISPLAY_NAMES = {
    "ais": "KTHAIS ais",
    "ais-max": "KTHAIS ais-max",
}
DESCRIPTIONS = {
    "ais": "Write tickets and epics, grill plans into docs, amend conventions, and ready PRs.",
    "ais-max": "Max's TDD ticket chain, explainers and writing rules. Install ais first.",
}


class BuildError(Exception):
    """A check failed before anything was written. The message says which one."""


def build_tree(version, ais=ROOT / "ais", ais_max=ROOT / "ais-max", dest=ROOT / BUILD):
    """Write the ais-agy plugin tree into dest, replacing any tree already there.

    version: str, required. The release version, of the form X.Y.Z, such as "1.0.0".
    ais: Path, default ROOT / "ais". The ais plugin folder. Read, never written.
    ais_max: Path, default ROOT / "ais-max". The ais-max plugin folder. Read,
        never written.
    dest: Path, default ROOT / BUILD. The folder this call replaces.

    Returns a dict mapping each plugin name in PLUGINS to the list of skill
    folder names written for it, sorted.

    On success dest holds, and holds only, one subfolder per plugin in
    PLUGINS, each an Antigravity plugin that installs on its own:
    - <name>/plugin.json, a JSON object with the keys "name" (the plugin's
      name), "version" (version), "displayName" (DISPLAY_NAMES[name]) and
      "description" (DESCRIPTIONS[name]), in that order, and no other key.
    - <name>/skills/<skill>/ for every folder directly inside that plugin's
      source folder, copied byte for byte with every file or folder whose
      name starts with "." left out, at any depth. Files lying loose in the
      source folder, outside any skill folder, are not copied. So
      ais-max/.source.json never reaches the tree.
    dest itself holds nothing but those subfolders, so it has no plugin.json
    of its own.

    Every JSON file is indented two spaces, keeps non-ASCII characters as
    written, and ends in a newline. Running it twice with the same version
    and inputs leaves dest byte-identical. Writes nothing outside dest,
    apart from temporary files it deletes before returning.

    Does not check the tree. A skill name in both plugins, or a skill with a
    bad frontmatter, is copied as is, for check_tree to report.

    Raises BuildError, with dest untouched, when:
    - version doesn't match X.Y.Z, where each part is digits only. Raised
      before reading ais or ais_max.
    - ais or ais_max is not an existing folder.
    Each message is one line naming the check that failed and the version or
    path that failed it.
    """
    raise NotImplementedError


def check_tree(tree=ROOT / BUILD, agy="agy"):
    """Return every rule the ais-agy tree at tree breaks, as messages.

    tree: Path, default ROOT / BUILD. A tree as build_tree writes it. Read,
        never written. The check reads only the tree, never the plugin
        source folders, so it can run on a tree fetched from the release
        repo.
    agy: str, default "agy". The Antigravity CLI command to run, as a name
        on PATH or a path to an executable. Tests pass a fake.

    Returns a list of str. An empty list means the tree passes. Each message
    is one line, starting with the file or folder it is about, relative to
    tree, then ": " and the rule it breaks. Messages come in this order:
    tree root problems, then plugin manifest problems in PLUGINS order, then
    skill problems ordered by plugin and then skill folder name, then skills
    found in both plugins, then agy's own, in PLUGINS order.

    The rules:
    - The tree root holds a folder for each plugin in PLUGINS, and nothing
      else.
    - Each plugin's <name>/plugin.json exists and is a JSON object.
    - Its "name" is lowercase kebab-case, ^[a-z0-9]+(-[a-z0-9]+)*$, and
      equals the plugin's folder name. A name that breaks both is one
      message, for kebab-case.
    - Its "version" is X.Y.Z, and both plugin.json files carry the same one.
    - <name>/skills/ holds at least one folder.
    - Every folder in <name>/skills/ holds a SKILL.md whose frontmatter,
      between "---" lines at the top, has a "name" equal to the folder's
      name and a non-empty "description". A folded or literal description
      (">" or "|", optionally followed by "-" or "+", with indented lines
      below) counts as non-empty when an indented line holds text.
    - No skill folder name appears under both plugins. The message names the
      skill once and both plugins.
    - Antigravity accepts each plugin. For each plugin whose plugin.json
      exists, the check runs
      [agy, "plugin", "validate", "--strict", "--json", str(tree / name)].
      A zero exit adds nothing. A non-zero exit adds one message per finding
      of severity "error" or "warning" in its JSON report, as
      "<name>/<file>: agy: <message>" using the report's own file and
      message. If stdout is not that JSON, it adds one message,
      "<name>: agy: <last line of stderr>". Whether a manifest key is in
      Antigravity's schema is left to this rule (ADR-0010).
    - When agy can't be started, such as when it isn't installed, that is
      one message saying so, given once, not once per plugin. It is never
      skipped (ADR-0009).

    One message per broken rule. A rule that depends on a missing file is
    not reported on top of it: a missing plugin.json is one message for
    that manifest, and a skill folder with no SKILL.md, or a SKILL.md with
    no frontmatter, is one message for that skill.

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
