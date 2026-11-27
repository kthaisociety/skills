#!/usr/bin/env python3
"""Build the ais-codex marketplace tree for Codex, and check one. No extra packages.

Usage: python3 scripts/build-codex.py build 1.0.0
       python3 scripts/build-codex.py check [TREE]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
BUILD = ".codex-build"
MARKETPLACE_FILE = ".agents/plugins/marketplace.json"
POLICY_TEXT = "policy:\n  allow_implicit_invocation: false\n"
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
REF_RE = re.compile(r"(?<![\w./])\.\./([A-Za-z0-9_-]+)/([A-Za-z0-9_./-]+)")
PLUGIN_MENTION_RE = re.compile(r"\$([A-Za-z0-9-]+):([A-Za-z0-9_-]+)")

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


def _sources(ais, ais_max):
    return {"ais": Path(ais), "ais-max": Path(ais_max)}


def _dumps(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _read_text(path):
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


def _split_frontmatter(text):
    """Return (frontmatter lines, body lines) or None when there is no frontmatter."""
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r") == "---":
            return lines[1:i], lines[i + 1:]
    return None


def _keys(block):
    """Group frontmatter lines into (key, value, raw lines) entries, continuation lines included."""
    entries = []
    for line in block:
        if line[:1] in (" ", "\t") and entries:
            entries[-1][2].append(line)
        elif ":" in line:
            key, _, value = line.partition(":")
            entries.append((key.strip(), value.strip(), [line]))
    return entries


def _mention_pattern(names):
    alternatives = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.compile(r"(?<![\w./-])/(" + alternatives + r")(?![\w/-]|\.\w)")


def _rewrite_mentions(text, owners):
    if not owners:
        return text
    pattern = _mention_pattern(owners)
    return pattern.sub(lambda m: f"${owners[m.group(1)]}:{m.group(1)}", text)


def _check_references(text, plugin, label, owners, sources):
    for match in REF_RE.finditer(text):
        skill, target = match.group(1), match.group(2).rstrip(".")
        owner = owners.get(skill)
        where = f"{label}: ../{skill}/{target}"
        if owner is None:
            raise BuildError(f"{where} names no skill in either plugin")
        if owner != plugin:
            raise BuildError(f"{where} points at a skill outside {plugin}")
        if not (sources[plugin] / skill / target).is_file():
            raise BuildError(f"{where} points at a file that doesn't exist")


def _load_object(path, rel, messages):
    if not path.is_file():
        messages.append(f"{rel}: is missing")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        data = None
    if not isinstance(data, dict):
        messages.append(f"{rel}: is not a JSON object")
        return None
    return data


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
    if not VERSION_RE.fullmatch(version):
        raise BuildError(f"version {version!r} is not X.Y.Z")
    sources = _sources(ais, ais_max)
    owners = skill_owners(ais, ais_max)
    plan = {}
    written = {}
    for plugin in PLUGINS:
        source = sources[plugin]
        skills = sorted(name for name, owner in owners.items() if owner == plugin)
        written[plugin] = skills
        for skill in skills:
            skill_src = source / skill
            for path in sorted(skill_src.rglob("*")):
                rel = path.relative_to(skill_src)
                if path.is_dir() or any(part.startswith(".") for part in rel.parts):
                    continue
                out = f"{plugin}/skills/{skill}/{rel.as_posix()}"
                label = f"{plugin}/skills/{skill}/{rel.as_posix()}"
                data = path.read_bytes()
                text = _read_text(path) if path.suffix == ".md" else None
                if text is None:
                    plan[out] = data
                    continue
                _check_references(text, plugin, label, owners, sources)
                text = _rewrite_mentions(text, owners)
                if rel == Path("SKILL.md"):
                    split = _split_frontmatter(text)
                    if split is not None:
                        block, body = split
                        kept, disable = [], False
                        for key, value, raw in _keys(block):
                            if key in ("name", "description"):
                                kept.extend(raw)
                            if key == "disable-model-invocation" and value.strip("'\"") == "true":
                                disable = True
                        text = "---\n" + "".join(line + "\n" for line in kept) + "---\n" + "\n".join(body)
                        if disable:
                            plan[f"{plugin}/skills/{skill}/agents/openai.yaml"] = POLICY_TEXT.encode("utf-8")
                plan[out] = text.encode("utf-8")

    marketplace = {
        "name": MARKETPLACE_NAME,
        "interface": {"displayName": MARKETPLACE_DISPLAY_NAME},
        "plugins": [
            {
                "name": name,
                "source": {"source": "local", "path": f"./{name}"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
            for name in PLUGINS
        ],
    }
    plan[MARKETPLACE_FILE] = _dumps(marketplace).encode("utf-8")
    for name in PLUGINS:
        manifest = {
            "name": name,
            "version": version,
            "description": DESCRIPTIONS[name],
            "author": {"name": AUTHOR},
        }
        plan[f"{name}/.codex-plugin/plugin.json"] = _dumps(manifest).encode("utf-8")

    if dest.exists():
        shutil.rmtree(dest)
    for rel, data in plan.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return written


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
    sources = _sources(ais, ais_max)
    for plugin in PLUGINS:
        if not sources[plugin].is_dir():
            raise BuildError(f"{sources[plugin]} is not a folder")
    names = {
        plugin: sorted(p.name for p in sources[plugin].iterdir()
                       if p.is_dir() and not p.name.startswith("."))
        for plugin in PLUGINS
    }
    holders = {}
    for plugin in PLUGINS:
        for name in names[plugin]:
            holders.setdefault(name, []).append(plugin)
    clashes = sorted(name for name, found in holders.items() if len(found) > 1)
    if clashes:
        first, second = holders[clashes[0]][:2]
        raise BuildError(f"skill {clashes[0]} is in both {first} and {second}")
    return {name: plugin for plugin in PLUGINS for name in names[plugin]}


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
    tree = Path(tree)
    if not tree.is_dir():
        return [f"{tree}: is not a folder"]
    messages = []

    market = _load_object(tree / MARKETPLACE_FILE, MARKETPLACE_FILE, messages)
    if market is not None:
        if market.get("name") != MARKETPLACE_NAME:
            messages.append(f"{MARKETPLACE_FILE}: name is {market.get('name')!r}, not {MARKETPLACE_NAME}")
        entries = market.get("plugins")
        if not isinstance(entries, list):
            entries = []
            messages.append(f"{MARKETPLACE_FILE}: plugins is not a list")
        listed = [e.get("name") if isinstance(e, dict) else None for e in entries]
        if sorted(listed, key=str) != sorted(PLUGINS):
            messages.append(f"{MARKETPLACE_FILE}: plugins must list {', '.join(PLUGINS)} once each and no other")
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("name") not in PLUGINS:
                continue
            name = entry["name"]
            if entry.get("source") != {"source": "local", "path": f"./{name}"}:
                messages.append(f"{MARKETPLACE_FILE}: {name} source is not local ./{name}")
            if not (tree / name).is_dir():
                messages.append(f"{name}: plugin folder is missing from the tree")

    versions = {}
    for plugin in PLUGINS:
        rel = f"{plugin}/.codex-plugin/plugin.json"
        data = _load_object(tree / rel, rel, messages)
        if data is None:
            continue
        if data.get("name") != plugin:
            messages.append(f"{rel}: name is {data.get('name')!r}, not {plugin}")
        description = data.get("description")
        if not isinstance(description, str) or not description.strip():
            messages.append(f"{rel}: description is empty")
        version = data.get("version")
        if isinstance(version, str) and VERSION_RE.fullmatch(version):
            versions[plugin] = version
        else:
            messages.append(f"{rel}: version {version!r} is not X.Y.Z")
    if versions:
        shared = next(iter(versions.values()))
        for plugin, version in versions.items():
            if version != shared:
                messages.append(f"{plugin}/.codex-plugin/plugin.json: version {version} is not the shared {shared}")

    tree_skills = {}
    for plugin in PLUGINS:
        root = tree / plugin / "skills"
        tree_skills[plugin] = sorted(p.name for p in root.iterdir()
                                     if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []
    all_names = {name for found in tree_skills.values() for name in found}
    mention = _mention_pattern(all_names) if all_names else None

    owner_seen = {}
    for plugin in PLUGINS:
        root = tree / plugin / "skills"
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if any(part.startswith(".") for part in path.relative_to(root).parts):
                    messages.append(f"{path.relative_to(tree).as_posix()}: hidden files and folders do not belong in a skill")
        for name in tree_skills[plugin]:
            skill_dir = root / name
            label = f"{plugin}/skills/{name}"
            if name in owner_seen:
                messages.append(f"{label}: skill {name} is in both {owner_seen[name]} and {plugin}")
            else:
                owner_seen[name] = plugin

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                messages.append(f"{label}: has no SKILL.md")
            else:
                text = _read_text(skill_md)
                split = _split_frontmatter(text) if text is not None else None
                skill_label = f"{label}/SKILL.md"
                if split is None:
                    messages.append(f"{skill_label}: has no frontmatter between --- lines")
                else:
                    entries = _keys(split[0])
                    keys = sorted(key for key, _, _ in entries)
                    if keys != ["description", "name"]:
                        messages.append(f"{skill_label}: frontmatter keys are {keys}, not name and description")
                    values = {key: value for key, value, _ in entries}
                    if values.get("name") != name:
                        messages.append(f"{skill_label}: name {values.get('name')!r} is not the folder name {name}")
                    description = [raw for key, _, raw in entries if key == "description"]
                    if not description or not (description[0][0].partition(":")[2].strip() or len(description[0]) > 1):
                        messages.append(f"{skill_label}: description is empty")

            for path in sorted(skill_dir.rglob("*")):
                if path.is_dir() or any(part.startswith(".") for part in path.relative_to(skill_dir).parts):
                    continue
                file_label = path.relative_to(tree).as_posix()
                if path.relative_to(skill_dir) == Path("agents/openai.yaml"):
                    if path.read_bytes() != POLICY_TEXT.encode("utf-8"):
                        messages.append(f"{file_label}: does not hold exactly the blocking policy")
                if path.suffix != ".md":
                    continue
                text = _read_text(path)
                if text is None:
                    messages.append(f"{file_label}: is not UTF-8 text")
                    continue
                found = mention.search(text) if mention else None
                if found:
                    messages.append(f"{file_label}: /{found.group(1)} was not rewritten to $<plugin>:{found.group(1)}")
                for match in PLUGIN_MENTION_RE.finditer(text):
                    owner, skill = match.group(1), match.group(2)
                    if owner not in PLUGINS or skill not in tree_skills.get(owner, []):
                        messages.append(f"{file_label}: ${owner}:{skill} names no skill in that plugin")
                for match in REF_RE.finditer(text):
                    ref_skill, ref_file = match.group(1), match.group(2).rstrip(".")
                    if not (root / ref_skill / ref_file).is_file():
                        messages.append(f"{file_label}: ../{ref_skill}/{ref_file} is not a file in {plugin}'s skills")
    return messages


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
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exit_:
        return exit_.code

    if args.command == "build":
        try:
            written = build_tree(args.version)
        except BuildError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        for plugin in PLUGINS:
            print(f"Wrote {len(written[plugin])} skills to {BUILD}/{plugin}")
        return 0

    messages = check_tree(ROOT / BUILD if args.tree is None else Path(args.tree))
    if not messages:
        print("Tree passes")
        return 0
    for message in messages:
        print(message, file=sys.stderr)
    return 1


def build_parser():
    parser = argparse.ArgumentParser(prog="build-codex.py", description="Build or check the ais-codex tree.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build").add_argument("version")
    commands.add_parser("check").add_argument("tree", nargs="?", default=None)
    return parser


if __name__ == "__main__":
    sys.exit(main())
