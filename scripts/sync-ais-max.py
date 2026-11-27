#!/usr/bin/env python3
"""Rebuild ais-max/ from one Custom-skills release tag. No extra packages.

Usage: python3 scripts/sync-ais-max.py v2.1.0
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_REPO = "https://github.com/Maxastrand04/Custom-skills.git"
RECORD = ".source.json"
BASE_FILES = {
    "ticket-shapes.md": "new-ticket",
    "RECORD-FORMAT.md": "grill-docs",
    "ticket-pr.md": "pr-ticket",
}


class SyncError(Exception):
    """A check failed before anything was written. The message says which one."""


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
    raise NotImplementedError


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
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
