#!/usr/bin/env python3
"""Pick the next release version from this repo's tags and commit titles. No extra packages.

Usage: python3 scripts/plan-release.py
"""

import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent
RECORD = Path("ais-max") / ".source.json"

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
    raise NotImplementedError


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
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
