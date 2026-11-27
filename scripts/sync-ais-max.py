#!/usr/bin/env python3
"""Rebuild ais-max/ from one Custom-skills release tag. No extra packages.

Usage: python3 scripts/sync-ais-max.py v2.1.0
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_REPO = "https://github.com/Maxastrand04/Custom-skills.git"
RECORD = ".source.json"
BASE_FILES = {
    "ticket-shapes.md": "new-ticket",
    "RECORD-FORMAT.md": "grill-docs",
    "ticket-pr.md": "pr-ticket",
}
_TAG_FORM = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+")
_MARKETPLACE = ".claude-plugin/marketplace.json"
_PLUGIN = "max"
_HELPER_SKILL = "helper-skill"


class SyncError(Exception):
    """A check failed before anything was written. The message says which one."""


def _clone(repo, tag, into):
    """Clone repo at tag into the folder into. Returns the commit the tag points at."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", tag, repo, str(into)],
                       check=True, capture_output=True, text=True, env=env)
        head = subprocess.run(["git", "-C", str(into), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True, env=env)
    except subprocess.CalledProcessError as error:
        lines = (error.stderr or "").strip().splitlines()
        detail = lines[-1] if lines else str(error)
        raise SyncError(f"could not fetch tag {tag} from {repo}: {detail}")
    except OSError as error:
        raise SyncError(f"could not run git to fetch tag {tag} from {repo}: {error}")
    return head.stdout.strip()


def sync(tag, repo=SOURCE_REPO, ais=ROOT / "ais", dest=ROOT / "ais-max"):
    """Replace dest with the max plugin's skills at tag, minus the ais skills.

    tag: str, required. A Custom-skills release tag of the form vX.Y.Z.
    repo: str, default SOURCE_REPO. Any git URL or local path git can clone
        without credentials.
    ais: Path, default ROOT / "ais". The ais plugin folder. Read, never written.
    dest: Path, default ROOT / "ais-max". The folder this call replaces.

    Returns the number of skill folders written to dest, as an int.

    On success dest holds, and holds only:
    - One folder per skill in the max plugin's list in
      .claude-plugin/marketplace.json at tag, named after the last part of
      its listed path, minus every skill whose name matches a folder in ais.
      Each is a copy of its source folder with every file or folder whose
      name starts with "." left out, at any depth.
    - In dest/helper-skill, each file named in BASE_FILES overwritten by
      ais/<skill>/<file> for the skill BASE_FILES maps it to.
    - dest/RECORD, a JSON object {"commit": <40-char sha>, "tag": <tag>},
      keys sorted, two-space indent, ending in a newline. The commit is the
      one tag points at.

    Running it twice with the same tag and inputs leaves dest byte-identical.
    Writes nothing outside dest, apart from temporary files it deletes
    before returning.

    Every SyncError message is one line naming the check that failed and
    the tag, path or name that failed it. Raises SyncError, with dest
    untouched, when:
    - tag doesn't match vX.Y.Z, before any network or git call.
    - repo can't be cloned at tag, including a tag that doesn't exist.
    - the marketplace file is missing, or lists no plugin named "max".
    - a listed skill folder doesn't exist at tag.
    - two listed skills share a folder name.
    - helper-skill is not in the list once the ais skills are dropped. The
      message reads "helper-skill is missing from the max plugin at <tag>,
      so ticket-shapes.md, RECORD-FORMAT.md and ticket-pr.md have nowhere
      to go".
    - any ais/<skill>/<file> that BASE_FILES names doesn't exist.
    """
    if not _TAG_FORM.fullmatch(tag):
        raise SyncError(f"tag {tag!r} is not a release tag of the form vX.Y.Z")

    with tempfile.TemporaryDirectory() as scratch:
        source = Path(scratch) / "source"
        commit = _clone(repo, tag, source)
        keep = _skills_to_keep(source, tag, ais)
        _check_base_files(ais)
        staging = _stage(source, keep, ais, Path(scratch) / "ais-max")
        _write_record(staging, tag, commit)
        _replace(dest, staging)
    return len(keep)


def _max_skill_list(source, tag):
    """Return the max plugin's listed skill paths in source's marketplace file, as Paths."""
    marketplace = source / _MARKETPLACE
    if not marketplace.is_file():
        raise SyncError(f"{_MARKETPLACE} is missing at tag {tag}")
    try:
        manifest = json.loads(marketplace.read_text())
    except (OSError, ValueError):
        raise SyncError(f"{_MARKETPLACE} at tag {tag} is not readable JSON")
    plugins = manifest.get("plugins", []) if isinstance(manifest, dict) else []
    plugin = next((p for p in plugins if isinstance(p, dict) and p.get("name") == _PLUGIN), None)
    if plugin is None:
        raise SyncError(f'{_MARKETPLACE} at tag {tag} lists no plugin named "{_PLUGIN}"')
    return [Path(entry) for entry in plugin.get("skills", [])]


def _skills_to_keep(source, tag, ais):
    """Return the max list's skill paths at tag, minus every skill named like a folder in ais."""
    listed = _max_skill_list(source, tag)
    seen = set()
    for path in listed:
        if path.name in seen:
            raise SyncError(f"two skills in the max list at tag {tag} share the folder name {path.name}")
        seen.add(path.name)

    ais_names = {p.name for p in ais.iterdir() if p.is_dir()} if ais.is_dir() else set()
    keep = [path for path in listed if path.name not in ais_names]

    for path in listed:
        if not (source / path).is_dir():
            raise SyncError(f"skill folder {path.as_posix()} is missing at tag {tag}")

    if _HELPER_SKILL not in {path.name for path in keep}:
        raise SyncError(
            f"{_HELPER_SKILL} is missing from the max plugin at {tag}, so ticket-shapes.md, "
            "RECORD-FORMAT.md and ticket-pr.md have nowhere to go")
    return keep


def _check_base_files(ais):
    """Raise SyncError if any ais base file named in BASE_FILES is missing."""
    for file, skill in BASE_FILES.items():
        if not (ais / skill / file).is_file():
            raise SyncError(f"ais base file ais/{skill}/{file} is missing")


def _stage(source, keep, ais, staging):
    """Build the new ais-max in staging from the kept skills and the ais base files. Returns staging."""
    staging.mkdir()
    for path in keep:
        shutil.copytree(source / path, staging / path.name,
                        ignore=shutil.ignore_patterns(".*"))
    for file, skill in BASE_FILES.items():
        shutil.copyfile(ais / skill / file, staging / _HELPER_SKILL / file)
    return staging


def _write_record(staging, tag, commit):
    """Write the RECORD file into staging, naming tag and the commit it points at."""
    (staging / RECORD).write_text(
        json.dumps({"commit": commit, "tag": tag}, indent=2, sort_keys=True) + "\n")


def _replace(dest, staging):
    """Swap staging in as dest, removing whatever dest held.

    The new tree is copied beside dest first, then renamed over it, so a
    failure at any point leaves dest as it was and re-raises the OSError.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fresh = dest.with_name(f".{dest.name}.new")
    old = dest.with_name(f".{dest.name}.old")
    for leftover in (fresh, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    try:
        shutil.copytree(staging, fresh)
        if dest.exists():
            os.replace(dest, old)
        try:
            os.replace(fresh, dest)
        except OSError:
            if old.exists():
                os.replace(old, dest)
            raise
    finally:
        if fresh.exists():
            shutil.rmtree(fresh)
    if old.exists():
        shutil.rmtree(old)


def main(argv=None):
    """Run the sync from the command line.

    argv: list[str] | None, default None, meaning sys.argv[1:]. Holds exactly
        one positional argument, the Custom-skills release tag, such as "v2.1.0".

    Returns the process exit code as an int, and never raises SyncError:
    - 0 after a sync, having printed one line to stdout naming how many
      skills it wrote, as "Wrote <count> skills to ais-max from <tag>".
    - 1 when the sync raised SyncError, having printed "error: <message>"
      to stderr. ais-max/ is then exactly as it was before the run.
    - 2 when argv doesn't hold exactly one argument, per argparse.

    Runs against SOURCE_REPO and the ais/ and ais-max/ folders under ROOT.
    """
    parser = argparse.ArgumentParser(description="Rebuild ais-max/ from one Custom-skills release tag.")
    parser.add_argument("tag", help='a Custom-skills release tag, such as "v2.1.0"')
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        return stop.code

    try:
        count = sync(args.tag)
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {count} skills to ais-max from {args.tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
