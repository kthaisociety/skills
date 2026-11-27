#!/usr/bin/env python3
"""Sync ais-max to the newest Custom-skills release tag, check it, and open a PR. No extra packages.

The scheduled workflow .github/workflows/sync-ais-max.yml runs this once a
day. It decides on tags alone (ADR-0011).

Usage: python3 scripts/scheduled-sync.py
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent

_spec = importlib.util.spec_from_file_location("sync_ais_max", ROOT / "scripts" / "sync-ais-max.py")
_sync_ais_max = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sync_ais_max)
SOURCE_REPO = _sync_ais_max.SOURCE_REPO


class JobError(Exception):
    """The job stopped before opening or updating a PR. The message says why, in one line."""


def latest_tag(repo):
    """Return the newest release tag on repo, or None when it has none.

    repo: str, required. Any git URL or local path git can list tags from
        without credentials, such as sync-ais-max.py's SOURCE_REPO.

    A release tag is a tag named exactly vX.Y.Z, where X, Y and Z are
    non-negative integers. Every other tag is ignored, including v1.2,
    v1.2.3-rc1, 1.2.3 and v1.2.3.4. "Newest" means highest by version
    number, comparing X, then Y, then Z as integers, so v2.10.0 is newer
    than v2.9.0. Tag dates and commit dates play no part.

    Reads only the remote's tag list. Clones nothing and writes nothing.

    Raises JobError when git can't list repo's tags, such as an unreachable
    URL or a path that is not a git repo. The message names repo.
    """
    raise NotImplementedError


# The checks a synced ais-max has to pass before the job pushes anything.
# Each entry is one command, run in order from the repo root; a non-zero
# exit fails the job. Add future checks here.
CHECKS = (
    (sys.executable, "-m", "unittest", "discover", "-s", "tests"),
    (sys.executable, "scripts/build-claude.py", "build", "0.0.0"),
    (sys.executable, "scripts/build-claude.py", "check"),
    (sys.executable, "scripts/build-codex.py", "build", "0.0.0"),
    (sys.executable, "scripts/build-codex.py", "check"),
    (sys.executable, "scripts/build-agy.py", "build", "0.0.0"),
    (sys.executable, "scripts/build-agy.py", "check"),
)

# Turn on to have GitHub merge a sync PR by itself once its required checks pass.
AUTO_MERGE = False

# Every sync PR's branch is this prefix plus the tag it brings in.
BRANCH_PREFIX = "sync/ais-max-"

UP_TO_DATE = "up to date"
OPENED = "opened"
UPDATED = "updated"


def run(repo=SOURCE_REPO, root=ROOT, gh="gh", checks=CHECKS, auto_merge=AUTO_MERGE):
    """Sync root's ais-max to repo's newest release tag and open or update its PR.

    repo: str, default SOURCE_REPO from sync-ais-max.py. The Custom-skills
        git URL or local path. Read without credentials.
    root: Path, default ROOT. A git checkout of this repo on the PR base
        branch, with a remote named origin to push to. Holds ais/ and ais-max/.
    gh: str, default "gh". The GitHub CLI command, already authenticated
        for origin's repo.
    checks: sequence of sequences of str, default CHECKS. Commands run in
        order from root after the sync.
    auto_merge: bool, default AUTO_MERGE. When true, the PR is set to merge
        itself once its required checks pass. When false, the job never
        asks for that.

    Returns, as a str:
    - UP_TO_DATE when latest_tag(repo) equals the tag in
      root/ais-max/.source.json. Nothing is synced, checked, committed,
      pushed, or asked of gh.
    - OPENED when it opened a new PR.
    - UPDATED when an open PR already had branch BRANCH_PREFIX + <new tag>.
      That PR is updated in place, and no second PR is opened.

    When the tags differ, in this order:
    1. Runs the ais-max sync for the new tag against repo, writing root/ais-max.
    2. Fails if the working tree differs from HEAD anywhere outside
       root/ais-max, untracked files included.
    3. Runs each command in checks, from root.
    4. Commits root/ais-max, and nothing else, on branch
       BRANCH_PREFIX + <new tag>, and force-pushes it to origin. Sets its
       own commit author, so it needs no git identity configured.
    5. Opens, or updates, the PR against the branch root had checked out.
       Its title reads "Sync ais-max from <old tag> to <new tag>", and its
       body names both tags.
    6. Closes every other open PR whose branch starts with BRANCH_PREFIX,
       with a comment linking the new one, and deletes its branch from
       origin. PRs on other branches are left alone.

    Reaches GitHub only through these gh forms, with any extra flags:
    - "pr list", reading the JSON array it prints, whose objects carry
      number, headRefName and url.
    - "pr create" with --base, --head, --title, and --body or --body-file,
      reading the new PR's URL from the last line it prints.
    - "pr close <number>" with --comment holding the new PR's URL.
    - "pr merge <number or URL> --auto", only when auto_merge is true.
    - "pr edit", optionally, to refresh an updated PR's title and body.

    Raises JobError, having pushed nothing and called no gh command that
    opens, edits or closes a PR, when:
    - repo has no release tag.
    - root/ais-max/.source.json is missing or names no tag.
    - the sync fails. The message carries the sync's own message.
    - after the sync, any path outside root/ais-max differs from HEAD or
      is untracked. The message names every such path.
    - a command in checks exits non-zero. The message names the command.
    Raises JobError when a git push or gh command fails. The message names it.
    """
    raise NotImplementedError


def main(argv=None):
    """Run the job from the command line.

    argv: list[str] | None, default None, meaning sys.argv[1:]. Takes no
        arguments.

    Returns the process exit code as an int, and never raises JobError:
    - 0 after run() returned, having printed "Sync ais-max: <outcome>" to
      stdout as its last line, where <outcome> is run()'s return value.
    - 1 when run() raised JobError, having printed "error: <message>" to stderr.
    - 2 when argv holds any argument, per argparse.
    """
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())
