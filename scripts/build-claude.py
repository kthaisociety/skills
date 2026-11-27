#!/usr/bin/env python3
"""Build the ais-claude marketplace tree for Claude Code, and check one. No extra packages.

Usage: python3 scripts/build-claude.py build 1.0.0
       python3 scripts/build-claude.py check [TREE]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
BUILD = ".claude-build"

MARKETPLACE_NAME = "ais-claude"
MARKETPLACE_DESCRIPTION = "KTHAIS skills for Claude Code: the ais plugin and its add-on, ais-max."
AUTHOR = "KTHAIS"
PLUGINS = ("ais", "ais-max")
DESCRIPTIONS = {
    "ais": "Write tickets and epics, grill plans into docs, amend conventions, and ready PRs.",
    "ais-max": "Max's TDD ticket chain, explainers and writing rules. Install ais first.",
}

_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_MARKETPLACE_JSON = ".claude-plugin/marketplace.json"


class BuildError(Exception):
    """A check failed before anything was written. The message says which one."""


class _Unreadable(Exception):
    """A manifest that is missing, not JSON, or not a JSON object. The message names it."""


def _dump(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_dump(obj))


def _skip_hidden(_folder, names):
    return [n for n in names if n.startswith(".")]


def _skill_folders(folder):
    return sorted(p for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def _is_version(version):
    return isinstance(version, str) and _VERSION_RE.fullmatch(version) is not None


def _plugin_json(plugin):
    return f"{plugin}/.claude-plugin/plugin.json"


def _read_json(tree, rel):
    """Return the JSON object in tree / rel. Raises _Unreadable naming rel and what is wrong."""
    path = tree / rel
    if not path.is_file():
        raise _Unreadable(f"{rel}: file is missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _Unreadable(f"{rel}: is not valid JSON") from None
    if not isinstance(data, dict):
        raise _Unreadable(f"{rel}: is not a JSON object")
    return data


def _frontmatter(text):
    """Return the top-level frontmatter keys and values, or None when there is no block."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return None
    body = lines[1:end]
    fields = {}
    i = 0
    while i < len(body):
        match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", body[i])
        i += 1
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value[:1] in (">", "|"):
            parts = []
            while i < len(body) and (body[i][:1].isspace() or not body[i].strip()):
                parts.append(body[i].strip())
                i += 1
            value = " ".join(p for p in parts if p)
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key] = value
    return fields


def _write_tree(root, version, sources):
    """Write every file of the tree under root. sources maps plugin name to its source folder.

    Returns a dict mapping each plugin name to the sorted skill folder names written for it.
    """
    manifest = {
        "name": MARKETPLACE_NAME,
        "owner": {"name": AUTHOR},
        "description": MARKETPLACE_DESCRIPTION,
        "plugins": [
            {"name": p, "source": f"./{p}", "version": version, "description": DESCRIPTIONS[p]}
            for p in PLUGINS
        ],
    }
    _write_json(root / _MARKETPLACE_JSON, manifest)
    written = {}
    for plugin in PLUGINS:
        _write_json(root / _plugin_json(plugin), {
            "name": plugin, "version": version, "description": DESCRIPTIONS[plugin],
            "author": {"name": AUTHOR},
        })
        skills = root / plugin / "skills"
        skills.mkdir(parents=True)
        folders = _skill_folders(sources[plugin])
        for folder in folders:
            shutil.copytree(folder, skills / folder.name, ignore=_skip_hidden)
        written[plugin] = [folder.name for folder in folders]
    return written


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
    if not _is_version(version):
        raise BuildError(f"version {version!r} is not X.Y.Z, such as 1.0.0")
    sources = {"ais": Path(ais), "ais-max": Path(ais_max)}
    for plugin, folder in sources.items():
        if not folder.is_dir():
            raise BuildError(f"source folder {folder} for {plugin} is not a folder")

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.with_name(dest.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    try:
        written = _write_tree(staging, version, sources)
        if dest.exists():
            shutil.rmtree(dest)
        staging.rename(dest)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return written


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
    tree = Path(tree)
    if not tree.is_dir():
        return [f"{tree}: is not a folder, so nothing was checked"]

    listed, messages = _marketplace_listing(tree)
    manifests, unreadable = _plugin_manifests(tree)
    reference = _reference_version(listed, manifests)
    messages += _listed_plugin_problems(tree, listed, reference)
    messages += _plugin_manifest_problems(manifests, unreadable, reference)
    messages += _skill_problems(tree)
    messages += _claude_problems(tree, claude)
    return messages


def _marketplace_listing(tree):
    """Return the marketplace entries by plugin name, and the problems with the listing."""
    try:
        marketplace = _read_json(tree, _MARKETPLACE_JSON)
    except _Unreadable as exc:
        return {}, [str(exc)]
    if not isinstance(marketplace.get("plugins"), list):
        return {}, [f"{_MARKETPLACE_JSON}: plugins is not a list"]
    listed = {}
    problems = []
    for entry in marketplace["plugins"]:
        name = entry.get("name") if isinstance(entry, dict) else None
        if name not in PLUGINS:
            problems.append(f"{_MARKETPLACE_JSON}: lists {name!r}, which is not a plugin of this tree")
        elif name in listed:
            problems.append(f"{_MARKETPLACE_JSON}: lists {name} more than once")
        else:
            listed[name] = entry
    for name in PLUGINS:
        if name not in listed:
            problems.append(f"{_MARKETPLACE_JSON}: lists no plugin named {name}")
    return listed, problems


def _plugin_manifests(tree):
    """Return each readable plugin.json by plugin name, and each unreadable one's problem by name."""
    manifests = {}
    unreadable = {}
    for name in PLUGINS:
        try:
            manifests[name] = _read_json(tree, _plugin_json(name))
        except _Unreadable as exc:
            unreadable[name] = str(exc)
    return manifests, unreadable


def _reference_version(listed, manifests):
    """Return the version string the manifests state most often, or None when none states one."""
    stated = [entry.get("version") for entry in listed.values()]
    stated += [manifests[name].get("version") for name in PLUGINS if name in manifests]
    most_common = Counter(v for v in stated if isinstance(v, str)).most_common(1)
    return most_common[0][0] if most_common else None


def _version_problem(rel, version, reference):
    """Return the problem with a version stated in rel, or None when it is X.Y.Z and agrees."""
    if not _is_version(version):
        return f"{rel}: version {version!r} is not X.Y.Z"
    if version != reference:
        return f"{rel}: version {version} disagrees with {reference}, the version the other manifests state"
    return None


def _source_problem(tree, name, source):
    """Return the problem with a marketplace entry's source, or None when it names a folder in tree."""
    if not isinstance(source, str) or not source:
        return f"{_MARKETPLACE_JSON}: entry {name} has no source"
    folder = (tree / source).resolve()
    if not folder.is_relative_to(tree.resolve()):
        return f"{_MARKETPLACE_JSON}: entry {name} has source {source}, which is outside the tree"
    if not folder.is_dir():
        return f"{Path(source).as_posix().removeprefix('./')}: listed in the marketplace as {name}, but the folder is missing"
    return None


def _listed_plugin_problems(tree, listed, reference):
    """Return the problems with each marketplace entry's plugin folder and version."""
    problems = []
    for name, entry in listed.items():
        found = _source_problem(tree, name, entry.get("source"))
        if found:
            problems.append(found)
        found = _version_problem(f"{_MARKETPLACE_JSON} entry {name}", entry.get("version"), reference)
        if found:
            problems.append(found)
    return problems


def _plugin_manifest_problems(manifests, unreadable, reference):
    """Return the problems with each plugin.json, in PLUGINS order."""
    problems = []
    for name in PLUGINS:
        rel = _plugin_json(name)
        if name in unreadable:
            problems.append(unreadable[name])
            continue
        data = manifests[name]
        if data.get("name") != name:
            problems.append(f"{rel}: name is {data.get('name')!r}, not {name!r}")
        found = _version_problem(rel, data.get("version"), reference)
        if found:
            problems.append(found)
    return problems


def _skill_problems(tree):
    """Return the problems with every skill folder, by plugin and then folder name."""
    problems = []
    owners = {}
    for plugin in PLUGINS:
        skills_dir = tree / plugin / "skills"
        if not skills_dir.is_dir():
            continue
        for folder in _skill_folders(skills_dir):
            skill = folder.name
            if skill in owners:
                problems.append(f"{plugin}/skills/{skill}: skill {skill} is in both {owners[skill]} and {plugin}")
            owners.setdefault(skill, plugin)
            problems += _skill_md_problems(folder, f"{plugin}/skills/{skill}/SKILL.md")
    return problems


def _skill_md_problems(folder, rel):
    """Return the problems with the SKILL.md in a skill folder, named rel in each message."""
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        return [f"{rel}: file is missing"]
    fields = _frontmatter(skill_md.read_text(encoding="utf-8", errors="replace"))
    if fields is None:
        return [f"{rel}: has no frontmatter between --- lines"]
    problems = []
    if "name" not in fields:
        problems.append(f"{rel}: frontmatter has no name")
    elif fields["name"] != folder.name:
        problems.append(f"{rel}: frontmatter name {fields['name']!r} is not the folder name {folder.name!r}")
    if not fields.get("description"):
        problems.append(f"{rel}: frontmatter has no description")
    return problems


def _claude_problems(tree, claude):
    """Return Claude Code's own problems with the tree, or one saying claude can't be run."""
    cmd = [claude, "plugin", "validate", "--strict", "--json", str(tree)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return [f"claude: cannot run {claude}: {exc.strerror or exc}"]
    if result.returncode == 0:
        return []
    return _claude_messages(result)


def _claude_messages(result):
    """Turn a failed `claude plugin validate` run into messages, one per error or warning."""
    try:
        manifest = json.loads(result.stdout)["manifest"]
        found = [f"claude: {item['path']}: {item['message']}"
                 for key in ("errors", "warnings") for item in manifest.get(key, [])]
    except (ValueError, KeyError, TypeError, AttributeError):
        found = []
    if found:
        return [m.replace("\n", " ") for m in found]
    lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    detail = lines[-1] if lines else f"exited with status {result.returncode} and printed no report"
    return [f"claude: {detail}"]


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
    parser = argparse.ArgumentParser(description="Build or check the ais-claude marketplace tree.")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="write the tree for a version")
    build.add_argument("version", help="the release version, X.Y.Z")
    check = commands.add_parser("check", help="check a built tree")
    check.add_argument("tree", nargs="?", help=f"the tree to check, default {BUILD}")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code

    if args.command == "build":
        try:
            counts = build_tree(args.version)
        except BuildError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for plugin in PLUGINS:
            print(f"Wrote {len(counts[plugin])} skills to {BUILD}/{plugin}")
        return 0

    tree = Path(args.tree) if args.tree else ROOT / BUILD
    messages = check_tree(tree)
    if messages:
        for message in messages:
            print(message, file=sys.stderr)
        return 1
    print("Tree passes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
