#!/usr/bin/env python3
"""Build the ais-agy plugin tree for Antigravity, and check one. No extra packages.

Usage: python3 scripts/build-agy.py build 1.0.0
       python3 scripts/build-agy.py check [TREE]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
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


_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_KEBAB_RE = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
_FIELD_RE = re.compile(r"([A-Za-z_][\w-]*):(.*)")
_BLOCK_INDICATORS = (">", "|", ">-", "|-", ">+", "|+")
_MANIFEST = "plugin.json"
_SKILLS = "skills"
_FAILING_SEVERITIES = ("error", "warning")
_STAGE_PREFIX = ".agy-stage-"
_TREE_MODE = 0o755


def _dump(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _is_hidden(name):
    return name.startswith(".")


def _skip_hidden(folder, names):
    return [name for name in names if _is_hidden(name)]


def _one_line(text):
    return " ".join(str(text).split())


def _check_manifest(tree, plugin):
    """Messages for one plugin.json, and its version when it is valid X.Y.Z, else None."""
    rel = f"{plugin}/{_MANIFEST}"
    path = tree / plugin / _MANIFEST
    if not path.is_file():
        return [f"{rel}: missing"], None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return [f"{rel}: not valid JSON"], None
    if not isinstance(data, dict):
        return [f"{rel}: not a JSON object"], None
    messages = []
    name = data.get("name")
    if name is None:
        messages.append(f"{rel}: no name")
    elif not isinstance(name, str) or not _KEBAB_RE.fullmatch(name):
        messages.append(f"{rel}: name {name!r} is not lowercase kebab-case")
    elif name != plugin:
        messages.append(f"{rel}: name {name!r} does not match the folder {plugin!r}")
    if "version" not in data:
        messages.append(f"{rel}: no version")
        return messages, None
    version = data["version"]
    if not _is_version(version):
        messages.append(f"{rel}: version {version!r} is not X.Y.Z")
        return messages, None
    return messages, version


def _is_version(value):
    return isinstance(value, str) and bool(_VERSION_RE.fullmatch(value))


def _frontmatter_fields(lines):
    """Map each top-level key to (scalar value, whether an indented line holds text)."""
    fields = {}
    current = None
    for line in lines:
        if line[:1] in (" ", "\t"):
            if current is not None and line.strip():
                value, _ = fields[current]
                fields[current] = (value, True)
            continue
        match = _FIELD_RE.fullmatch(line)
        if match:
            current = match.group(1)
            fields[current] = (match.group(2).strip().strip("\"'").strip(), False)
        else:
            current = None
    return fields


def _check_skill(plugin, folder):
    """Messages for one skill folder's SKILL.md."""
    rel = f"{plugin}/{_SKILLS}/{folder.name}"
    md = folder / "SKILL.md"
    if not md.is_file():
        return [f"{rel}: no SKILL.md"]
    try:
        lines = md.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return [f"{rel}/SKILL.md: not readable as UTF-8 text"]
    if not lines or lines[0].rstrip() != "---":
        return [f"{rel}/SKILL.md: no frontmatter"]
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None:
        return [f"{rel}/SKILL.md: frontmatter is not closed by ---"]
    fields = _frontmatter_fields(lines[1:end])
    messages = []
    name, _ = fields.get("name", ("", False))
    if not name:
        messages.append(f"{rel}/SKILL.md: frontmatter has no name")
    elif name != folder.name:
        messages.append(f"{rel}/SKILL.md: name {name!r} does not match the folder {folder.name!r}")
    if "description" not in fields:
        messages.append(f"{rel}/SKILL.md: frontmatter has no description")
    else:
        value, block_text = fields["description"]
        has_text = (value and value not in _BLOCK_INDICATORS) or block_text
        if not has_text:
            messages.append(f"{rel}/SKILL.md: description is empty")
    return messages


def _agy_findings(plugin, stdout):
    """One message per error or warning in agy's JSON report, or none if stdout is not that."""
    try:
        report = json.loads(stdout)
    except ValueError:
        return []
    if not isinstance(report, dict) or not isinstance(report.get("findings"), list):
        return []
    messages = []
    for finding in report["findings"]:
        if isinstance(finding, dict) and finding.get("severity") in _FAILING_SEVERITIES:
            messages.append(_one_line(
                f"{plugin}/{finding.get('file', '?')}: agy: {finding.get('message', '')}"))
    return messages


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
    if not _is_version(version):
        raise BuildError(f"version {version!r} is not X.Y.Z, with digits only")
    sources = {"ais": Path(ais), "ais-max": Path(ais_max)}
    for plugin in PLUGINS:
        if not sources[plugin].is_dir():
            raise BuildError(f"{plugin} is not an existing folder: {sources[plugin]}")

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=_STAGE_PREFIX, dir=dest.parent))
    try:
        written = {plugin: _stage_plugin(stage / plugin, plugin, sources[plugin], version)
                   for plugin in PLUGINS}
        _replace(dest, stage)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return written


def _stage_plugin(plugin_dir, plugin, source, version):
    """Write one plugin's skills and manifest into plugin_dir, and return its skill names."""
    skills_dir = plugin_dir / _SKILLS
    skills_dir.mkdir(parents=True)
    names = sorted(p.name for p in source.iterdir() if p.is_dir() and not _is_hidden(p.name))
    for name in names:
        shutil.copytree(source / name, skills_dir / name, ignore=_skip_hidden)
    manifest = {"name": plugin, "version": version,
                "displayName": DISPLAY_NAMES[plugin], "description": DESCRIPTIONS[plugin]}
    (plugin_dir / _MANIFEST).write_bytes(_dump(manifest))
    return names


def _replace(dest, stage):
    """Swap the staged tree in at dest, removing whatever dest held."""
    if dest.is_dir() and not dest.is_symlink():
        shutil.rmtree(dest)
    elif dest.exists() or dest.is_symlink():
        dest.unlink()
    stage.chmod(_TREE_MODE)
    stage.rename(dest)


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
    tree = Path(tree)
    if not tree.is_dir():
        return [f"{tree}: not an existing folder"]

    messages, present = _check_root(tree)
    messages += _check_manifests(tree, present)
    found, skill_names = _check_skills(tree, present)
    messages += found
    messages += _check_shared_skills(skill_names)
    messages += _run_agy(tree, agy)
    return messages


def _check_root(tree):
    """Messages for the tree root, and the plugins whose folders are present, in PLUGINS order."""
    messages = []
    for entry in sorted(tree.iterdir(), key=lambda p: p.name):
        if entry.name not in PLUGINS:
            messages.append(f"{entry.name}: not allowed at the tree root, which holds only "
                            "the plugin folders")
    present = []
    for plugin in PLUGINS:
        if (tree / plugin).is_dir():
            present.append(plugin)
        else:
            messages.append(f"{plugin}: plugin folder is missing")
    return messages, present


def _check_manifests(tree, present):
    """Messages for each present plugin's manifest, then for versions that disagree."""
    messages = []
    versions = {}
    for plugin in present:
        found, versions[plugin] = _check_manifest(tree, plugin)
        messages += found
    first, second = PLUGINS
    if versions.get(first) and versions.get(second) and versions[first] != versions[second]:
        messages.append(f"{second}/{_MANIFEST}: version {versions[second]} differs from "
                        f"version {versions[first]} in {first}")
    return messages


def _check_skills(tree, present):
    """Messages for each present plugin's skills, and its skill folder names."""
    messages = []
    skill_names = {}
    for plugin in present:
        skills_dir = tree / plugin / _SKILLS
        if not skills_dir.is_dir():
            messages.append(f"{plugin}/{_SKILLS}: missing")
            skill_names[plugin] = []
            continue
        folders = sorted(p for p in skills_dir.iterdir() if p.is_dir())
        if not folders:
            messages.append(f"{plugin}/{_SKILLS}: holds no skill folder")
        skill_names[plugin] = [p.name for p in folders]
        for folder in folders:
            messages += _check_skill(plugin, folder)
    return messages, skill_names


def _check_shared_skills(skill_names):
    """One message per skill folder name found under both plugins."""
    first, second = PLUGINS
    shared = sorted(set(skill_names.get(first, [])) & set(skill_names.get(second, [])))
    return [f"{skill}: in both {first} and {second}" for skill in shared]


def _run_agy(tree, agy):
    """Messages from agy's strict validation of each plugin that has a manifest."""
    messages = []
    for plugin in PLUGINS:
        if not (tree / plugin / _MANIFEST).is_file():
            continue
        command = [agy, "plugin", "validate", "--strict", "--json", str(tree / plugin)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        except OSError as problem:
            messages.append(f"agy: could not run {agy!r} ({problem.strerror or problem}), "
                            "so the tree cannot be checked; install agy first")
            break
        if proc.returncode == 0:
            continue
        findings = _agy_findings(plugin, proc.stdout)
        if findings:
            messages += findings
            continue
        messages.append(_agy_failure(plugin, proc))
    return messages


def _agy_failure(plugin, proc):
    """One message for a failed agy run whose stdout held no findings."""
    stderr_lines = [line for line in proc.stderr.splitlines() if line.strip()]
    detail = stderr_lines[-1] if stderr_lines else f"exited with code {proc.returncode}"
    return _one_line(f"{plugin}: agy: {detail}")


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
    parser = argparse.ArgumentParser(description="Build or check the ais-agy plugin tree.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="write the tree for a version")
    build.add_argument("version", help="the release version, X.Y.Z")
    check = commands.add_parser("check", help="check a tree")
    check.add_argument("tree", nargs="?", help=f"the tree to check, default {BUILD}")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2

    if args.command == "build":
        try:
            written = build_tree(args.version)
        except BuildError as problem:
            print(f"error: {problem}", file=sys.stderr)
            return 1
        for plugin in PLUGINS:
            print(f"Wrote {len(written[plugin])} skills to {BUILD}/{plugin}")
        return 0

    tree = ROOT / BUILD if args.tree is None else Path(args.tree)
    messages = check_tree(tree)
    if messages:
        for message in messages:
            print(message, file=sys.stderr)
        return 1
    print("Tree passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
