#!/usr/bin/env python3
"""Build the ais-codex marketplace tree for Codex, and check one. No extra packages.

Usage: python3 scripts/build-codex.py build 1.0.0
       python3 scripts/build-codex.py check [TREE]
       python3 scripts/build-codex.py local
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
BUILD = ".codex-build"
LOCAL_BUILD = ".codex-local"
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


def _json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _is_hidden(rel):
    return any(part.startswith(".") for part in rel.parts)


def _skill_folders(folder):
    """Return the names of the folders directly inside folder that aren't hidden, sorted."""
    return sorted(p.name for p in folder.iterdir() if p.is_dir() and not p.name.startswith("."))


def _visible_files(folder):
    """Yield every file under folder, sorted, leaving out anything on a hidden path."""
    for path in sorted(folder.rglob("*")):
        if not path.is_dir() and not _is_hidden(path.relative_to(folder)):
            yield path


def _references(text):
    """Yield (skill, file) for every "../<skill>/<file>" reference in text."""
    for match in REF_RE.finditer(text):
        yield match.group(1), match.group(2).rstrip(".")


def _plugin_source(name):
    return {"source": "local", "path": f"./{name}"}


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


def _rewrite_mentions(text, owners, prefixed=True):
    if not owners:
        return text
    pattern = _mention_pattern(owners)
    if prefixed:
        return pattern.sub(lambda m: f"${owners[m.group(1)]}:{m.group(1)}", text)
    return pattern.sub(lambda m: f"${m.group(1)}", text)


def _check_references(text, plugin, label, owners, sources):
    for skill, target in _references(text):
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
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError):
        loaded = None
    if not isinstance(loaded, dict):
        messages.append(f"{rel}: is not a JSON object")
        return None
    return loaded


def _strip_frontmatter(text):
    """Return (text, disable): SKILL.md text keeping only the name and description
    frontmatter lines, and whether it set disable-model-invocation to true."""
    split = _split_frontmatter(text)
    if split is None:
        return text, False
    block, body = split
    kept, disable = [], False
    for key, value, raw in _keys(block):
        if key in ("name", "description"):
            kept.extend(raw)
        if key == "disable-model-invocation" and value.strip("'\"") == "true":
            disable = True
    return "---\n" + "".join(line + "\n" for line in kept) + "---\n" + "\n".join(body), disable


def _convert_skill(plugin, skill, owners, sources, files, prefix=None, prefixed=True):
    """Add one skill's converted files to files, keyed by their path in the tree."""
    skill_src = sources[plugin] / skill
    if prefix is None:
        prefix = f"{plugin}/skills/{skill}"
    for path in _visible_files(skill_src):
        rel = path.relative_to(skill_src)
        out = f"{prefix}/{rel.as_posix()}"
        text = _read_text(path) if path.suffix == ".md" else None
        if text is None:
            files[out] = path.read_bytes()
            continue
        _check_references(text, plugin, out, owners, sources)
        text = _rewrite_mentions(text, owners, prefixed)
        if rel == Path("SKILL.md"):
            text, disable = _strip_frontmatter(text)
            if disable:
                files[f"{prefix}/agents/openai.yaml"] = POLICY_TEXT.encode("utf-8")
        files[out] = text.encode("utf-8")


def _marketplace():
    return {
        "name": MARKETPLACE_NAME,
        "interface": {"displayName": MARKETPLACE_DISPLAY_NAME},
        "plugins": [
            {
                "name": name,
                "source": _plugin_source(name),
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
            for name in PLUGINS
        ],
    }


def _manifest(name, version):
    return {
        "name": name,
        "version": version,
        "description": DESCRIPTIONS[name],
        "author": {"name": AUTHOR},
    }


def _write_tree(files, dest):
    if dest.exists():
        shutil.rmtree(dest)
    for rel, content in files.items():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


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
    files, written = {}, {}
    for plugin in PLUGINS:
        written[plugin] = sorted(name for name, owner in owners.items() if owner == plugin)
        for skill in written[plugin]:
            _convert_skill(plugin, skill, owners, sources, files)
    files[MARKETPLACE_FILE] = _json_bytes(_marketplace())
    for name in PLUGINS:
        files[f"{name}/.codex-plugin/plugin.json"] = _json_bytes(_manifest(name, version))
    _write_tree(files, dest)
    return written


def build_local(ais=ROOT / "ais", ais_max=ROOT / "ais-max", dest=ROOT / LOCAL_BUILD):
    """Write every ais and ais-max skill, converted for Codex, flat into dest,
    for install.sh to copy. Replaces any folder already at dest.

    ais: Path, default ROOT / "ais". The ais plugin folder. Read, never written.
    ais_max: Path, default ROOT / "ais-max". The ais-max plugin folder. Read,
        never written.
    dest: Path, default ROOT / LOCAL_BUILD, which git ignores. The folder this
        call replaces. Never ROOT / BUILD, so a local build and a release
        build never touch each other's output.

    Returns a list of every skill folder name written, sorted.

    On success dest holds, and holds only, one folder <skill>/ per skill in
    skill_owners, from either plugin, converted as build_tree converts it,
    with one difference: each "/<skill>" mention of a skill in either plugin
    becomes "$<skill>", with no plugin prefix. So hidden files and folders
    are left out, SKILL.md's frontmatter keeps only "name" and
    "description", a skill with "disable-model-invocation: true" gets
    agents/openai.yaml, and every other file is copied byte for byte. dest
    holds no marketplace or plugin manifest.

    Running it twice with the same inputs leaves dest byte-identical. Writes
    nothing outside dest, apart from temporary files it deletes before
    returning.

    Raises BuildError, with dest untouched, in the cases build_tree raises
    for, other than the version: a missing plugin folder, a skill in both
    plugins, or a "../<skill>/<file>" reference to a skill outside the
    referring file's plugin or to a file that doesn't exist.
    """
    sources = _sources(ais, ais_max)
    owners = skill_owners(ais, ais_max)
    files = {}
    for skill, plugin in owners.items():
        _convert_skill(plugin, skill, owners, sources, files, prefix=skill, prefixed=False)
    _write_tree(files, Path(dest))
    return sorted(owners)


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
    names = {plugin: _skill_folders(sources[plugin]) for plugin in PLUGINS}
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
    _check_marketplace(tree, messages)
    _check_manifests(tree, messages)
    tree_skills = {plugin: _tree_skills(tree, plugin) for plugin in PLUGINS}
    all_names = {name for found in tree_skills.values() for name in found}
    mention = _mention_pattern(all_names) if all_names else None
    owner_seen = {}
    for plugin in PLUGINS:
        root = tree / plugin / "skills"
        _check_hidden(tree, root, messages)
        for name in tree_skills[plugin]:
            label = f"{plugin}/skills/{name}"
            if name in owner_seen:
                messages.append(f"{label}: skill {name} is in both {owner_seen[name]} and {plugin}")
            else:
                owner_seen[name] = plugin
            _check_skill_md(root / name / "SKILL.md", name, label, messages)
            for path in _visible_files(root / name):
                _check_skill_file(tree, root / name, path, tree_skills, mention, messages)
    return messages


def _check_marketplace(tree, messages):
    market = _load_object(tree / MARKETPLACE_FILE, MARKETPLACE_FILE, messages)
    if market is None:
        return
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
        if entry.get("source") != _plugin_source(name):
            messages.append(f"{MARKETPLACE_FILE}: {name} source is not local ./{name}")
        if not (tree / name).is_dir():
            messages.append(f"{name}: plugin folder is missing from the tree")


def _check_manifests(tree, messages):
    versions = {}
    for plugin in PLUGINS:
        rel = f"{plugin}/.codex-plugin/plugin.json"
        manifest = _load_object(tree / rel, rel, messages)
        if manifest is None:
            continue
        if manifest.get("name") != plugin:
            messages.append(f"{rel}: name is {manifest.get('name')!r}, not {plugin}")
        description = manifest.get("description")
        if not isinstance(description, str) or not description.strip():
            messages.append(f"{rel}: description is empty")
        version = manifest.get("version")
        if isinstance(version, str) and VERSION_RE.fullmatch(version):
            versions[plugin] = version
        else:
            messages.append(f"{rel}: version {version!r} is not X.Y.Z")
    if versions:
        shared = next(iter(versions.values()))
        for plugin, version in versions.items():
            if version != shared:
                messages.append(f"{plugin}/.codex-plugin/plugin.json: version {version} is not the shared {shared}")


def _tree_skills(tree, plugin):
    root = tree / plugin / "skills"
    return _skill_folders(root) if root.is_dir() else []


def _check_hidden(tree, root, messages):
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if _is_hidden(path.relative_to(root)):
            messages.append(f"{path.relative_to(tree).as_posix()}: hidden files and folders do not belong in a skill")


def _has_description(entries):
    """Return whether the first description key has a value, inline or on continuation lines."""
    for key, value, raw in entries:
        if key == "description":
            return bool(value) or len(raw) > 1
    return False


def _check_skill_md(skill_md, name, label, messages):
    if not skill_md.is_file():
        messages.append(f"{label}: has no SKILL.md")
        return
    text = _read_text(skill_md)
    split = _split_frontmatter(text) if text is not None else None
    skill_label = f"{label}/SKILL.md"
    if split is None:
        messages.append(f"{skill_label}: has no frontmatter between --- lines")
        return
    entries = _keys(split[0])
    keys = sorted(key for key, _, _ in entries)
    if keys != ["description", "name"]:
        messages.append(f"{skill_label}: frontmatter keys are {keys}, not name and description")
    values = {key: value for key, value, _ in entries}
    if values.get("name") != name:
        messages.append(f"{skill_label}: name {values.get('name')!r} is not the folder name {name}")
    if not _has_description(entries):
        messages.append(f"{skill_label}: description is empty")


def _check_skill_file(tree, skill_dir, path, tree_skills, mention, messages):
    file_label = path.relative_to(tree).as_posix()
    if path.relative_to(skill_dir) == Path("agents/openai.yaml"):
        if path.read_bytes() != POLICY_TEXT.encode("utf-8"):
            messages.append(f"{file_label}: does not hold exactly the blocking policy")
    if path.suffix != ".md":
        return
    text = _read_text(path)
    if text is None:
        messages.append(f"{file_label}: is not UTF-8 text")
        return
    found = mention.search(text) if mention else None
    if found:
        messages.append(f"{file_label}: /{found.group(1)} was not rewritten to $<plugin>:{found.group(1)}")
    for match in PLUGIN_MENTION_RE.finditer(text):
        owner, skill = match.group(1), match.group(2)
        if owner not in PLUGINS or skill not in tree_skills.get(owner, []):
            messages.append(f"{file_label}: ${owner}:{skill} names no skill in that plugin")
    plugin = skill_dir.parent.parent.name
    for ref_skill, ref_file in _references(text):
        if not (skill_dir.parent / ref_skill / ref_file).is_file():
            messages.append(f"{file_label}: ../{ref_skill}/{ref_file} is not a file in {plugin}'s skills")

def main(argv=None):
    """Run a build or a check from the command line.

    argv: list[str] | None, default None, meaning sys.argv[1:]. One of:
        ["build", VERSION]   build_tree(VERSION) with the default folders.
        ["check"]            check_tree() on ROOT / BUILD.
        ["check", TREE]      check_tree(Path(TREE)).
        ["local"]            build_local() with the default folders.

    Returns the process exit code as an int, and never raises BuildError:
    - build, 0 after a build, having printed one line per plugin to stdout,
      in PLUGINS order, as "Wrote <count> skills to <BUILD>/<plugin>".
    - build, 1 when build_tree raised BuildError, having printed
      "error: <message>" to stderr. The build folder is then as it was.
    - local, 0 after a local build, having printed
      "Wrote <count> skills to <LOCAL_BUILD>" to stdout.
    - local, 1 when build_local raised BuildError, having printed
      "error: <message>" to stderr. The local folder is then as it was.
    - check, 0 when check_tree returned no messages, having printed
      "Tree passes" to stdout.
    - check, 1 when it returned messages, having printed each one on its
      own line to stderr, in the order returned.
    - 2 when argv names no known subcommand or has the wrong number of
      arguments, per argparse.

    Build never runs the check. The release runs both, in turn.
    """
    try:
        args = _build_parser().parse_args(argv)
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

    if args.command == "local":
        try:
            written = build_local()
        except BuildError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"Wrote {len(written)} skills to {LOCAL_BUILD}")
        return 0

    messages = check_tree(ROOT / BUILD if args.tree is None else Path(args.tree))
    if not messages:
        print("Tree passes")
        return 0
    for message in messages:
        print(message, file=sys.stderr)
    return 1


def _build_parser():
    parser = argparse.ArgumentParser(prog="build-codex.py", description="Build or check the ais-codex tree.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("build").add_argument("version")
    commands.add_parser("check").add_argument("tree", nargs="?", default=None)
    commands.add_parser("local")
    return parser


if __name__ == "__main__":
    sys.exit(main())
