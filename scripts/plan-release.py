#!/usr/bin/env python3
"""Pick the next release version from this repo's tags and commit titles. No extra packages.

Usage: python3 scripts/plan-release.py
"""

import argparse
import json
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
RECORD = Path("ais-max") / ".source.json"
_RELEASE_TAG = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")
_BREAKING = re.compile(r"[a-z]+(\([^()]*\))?!:")
_FEAT = re.compile(r"feat(\([^()]*\))?:")

Plan = namedtuple("Plan", ["version", "last_tag", "source_tag"])
Plan.__doc__ = """What a release would be, read from the repo without changing it.

version     str, the next version, "X.Y.Z" with no leading v.
last_tag    str | None, the release tag the version counts from, such as
            "v1.2.0", or None when the repo has no release tag yet.
source_tag  str, the Custom-skills tag in the ais-max sync record, such as "v2.1.0".
"""


class PlanError(Exception):
    """No plan could be made. The message says why, in words a maintainer can act on."""


def plan(repo=ROOT, record=None):
    """Plan the release of the commit checked out in repo.

    repo: Path, default ROOT. A git work tree. The plan is for its HEAD.
    record: Path | None, default None, meaning repo / RECORD. The ais-max
        sync record, a JSON object whose "tag" is a string.

    Returns a Plan.

    The last release tag is the highest "vX.Y.Z" by version number, X, Y and Z
    compared as integers, among the tags reachable from HEAD. A tag of any
    other shape is ignored, and so is a release tag HEAD doesn't contain.

    The version:
    - "1.0.0" when there is no last release tag, whatever the commit titles.
    - Otherwise the last tag bumped by the titles of every commit reachable
      from HEAD and not from the last tag:
      - major, Y and Z reset to 0, when any title has "!" just before its
        first colon after a lowercase type and an optional "(scope)", as in
        "feat!: ..." or "fix(build)!: ...";
      - else minor, Z reset to 0, when any title starts "feat:" or "feat(scope):";
      - else patch, including titles with no type at all.

    Raises PlanError, naming the first problem in this order:
    - repo isn't a git work tree, or HEAD has no commit. The message carries git's.
    - there is a last release tag and no commit since it. The message is
      exactly "nothing to release since <last tag>".
    - record is missing, isn't JSON, isn't a JSON object, or has no string
      "tag". The message names the record's path.

    Reads only. It writes nothing, fetches nothing, and runs only local git,
    so the caller must have every tag and the full history checked out.
    """
    repo = Path(repo)
    if _git(repo, "rev-parse", "--is-inside-work-tree").strip() != "true":
        raise PlanError(f"{repo} is not a git work tree")
    try:
        _git(repo, "rev-parse", "--verify", "HEAD")
    except PlanError as error:
        raise PlanError(f"{repo} has no commit to plan from: {error}") from error

    last = None
    for name in _git(repo, "tag", "--merged", "HEAD").splitlines():
        match = _RELEASE_TAG.fullmatch(name)
        if match:
            key = tuple(int(part) for part in match.groups())
            if last is None or key > last[0]:
                last = (key, name)

    if last is None:
        version, last_tag = "1.0.0", None
    else:
        (major, minor, patch), last_tag = last
        span = f"{last_tag}..HEAD"
        if not _git(repo, "rev-list", span).strip():
            raise PlanError(f"nothing to release since {last_tag}")
        titles = _git(repo, "log", "--format=%s", span).splitlines()
        if any(_BREAKING.match(title) for title in titles):
            major, minor, patch = major + 1, 0, 0
        elif any(_FEAT.match(title) for title in titles):
            minor, patch = minor + 1, 0
        else:
            patch += 1
        version = f"{major}.{minor}.{patch}"

    path = (repo / RECORD) if record is None else Path(record)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise PlanError(f"sync record {path} can't be read: {error}") from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise PlanError(f"sync record {path} isn't JSON: {error}") from error
    if not isinstance(data, dict) or not isinstance(data.get("tag"), str):
        raise PlanError(f"sync record {path} must be a JSON object with a string \"tag\"")

    return Plan(version, last_tag, data["tag"])


def _git(repo, *args):
    """Run git with args in repo and return its stdout. Raise PlanError with git's last stderr line."""
    try:
        done = subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, text=True, check=False)
    except OSError as error:
        raise PlanError(f"could not run git for {repo}: {error}") from error
    if done.returncode != 0:
        lines = done.stderr.strip().splitlines()
        raise PlanError(lines[-1] if lines else f"git {' '.join(args)} failed in {repo}")
    return done.stdout


def main(argv=None):
    """Plan the release of this repo's HEAD from the command line.

    argv: list[str] | None, default None, meaning sys.argv[1:]. Must be empty.

    Returns the process exit code as an int, and never raises PlanError:
    - 0 after plan() returned, having printed exactly three lines to stdout,
      in this order, each in the KEY=VALUE form GitHub Actions reads from
      $GITHUB_OUTPUT:
          version=<version>
          last_tag=<last tag, or nothing after the = when there is none>
          source_tag=<Custom-skills tag>
    - 1 when plan() raised PlanError, having printed "error: <message>" to
      stderr and nothing to stdout, as in
      "error: nothing to release since v1.2.0".
    - 2 when argv isn't empty, per argparse.
    """
    parser = argparse.ArgumentParser(description="Plan the next release version of this repo's HEAD.")
    try:
        parser.parse_args(argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 2
    try:
        result = plan(ROOT)
    except PlanError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"version={result.version}")
    print(f"last_tag={result.last_tag or ''}")
    print(f"source_tag={result.source_tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
