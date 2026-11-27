#!/usr/bin/env python3
"""Sync ais-max to the newest Custom-skills release tag, check it, and open a PR. No extra packages.

The scheduled workflow .github/workflows/sync-ais-max.yml runs this once a
day. It decides on tags alone (ADR-0011).

Usage: python3 scripts/scheduled-sync.py
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).absolute().parent.parent

_spec = importlib.util.spec_from_file_location("sync_ais_max", ROOT / "scripts" / "sync-ais-max.py")
_sync_ais_max = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sync_ais_max)
SOURCE_REPO = _sync_ais_max.SOURCE_REPO


_RELEASE_TAG = re.compile(r"v([0-9]+)\.([0-9]+)\.([0-9]+)")


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
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        out = subprocess.run(["git", "ls-remote", "--tags", repo], check=True,
                             capture_output=True, text=True, env=env).stdout
    except subprocess.CalledProcessError as error:
        raise JobError(f"could not list tags of {repo}: {_last_line(error.stderr) or error}")
    except OSError as error:
        raise JobError(f"could not run git to list tags of {repo}: {error}")

    best, best_key = None, None
    for line in out.splitlines():
        ref = line.split("\t")[-1]
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        match = _RELEASE_TAG.fullmatch(name)
        if not match:
            continue
        key = tuple(int(part) for part in match.groups())
        if best_key is None or key > best_key:
            best, best_key = name, key
    return best


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

_AUTHOR = ("-c", "user.name=ais-max sync", "-c", "user.email=sync-ais-max@users.noreply.github.com",
           "-c", "commit.gpgsign=false")


def _quiet_env():
    return dict(os.environ, GIT_TERMINAL_PROMPT="0")


def _last_line(text):
    lines = (text or "").strip().splitlines()
    return lines[-1] if lines else ""


def _git(cwd, *args):
    """Run git in cwd and return its stdout. Raises JobError naming the git command on failure."""
    try:
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                              text=True, env=_quiet_env()).stdout
    except subprocess.CalledProcessError as error:
        raise JobError(f"git {' '.join(args[:2])} failed: {_last_line(error.stderr) or error}")
    except OSError as error:
        raise JobError(f"could not run git: {error}")


def _gh(gh, cwd, *args):
    """Run the GitHub CLI in cwd and return its stdout. Raises JobError naming the gh command on failure."""
    try:
        return subprocess.run([gh, *args], cwd=cwd, check=True, capture_output=True,
                              text=True, env=_quiet_env()).stdout
    except subprocess.CalledProcessError as error:
        raise JobError(f"gh {' '.join(args[:2])} failed: {_last_line(error.stderr) or error}")
    except OSError as error:
        raise JobError(f"could not run gh: {error}")


def _recorded_tag(root):
    """Return the tag named in root/ais-max's sync record. Raises JobError if it is missing or names none."""
    record = root / "ais-max" / _sync_ais_max.RECORD
    try:
        data = json.loads(record.read_text())
    except (OSError, ValueError):
        raise JobError(f"{record} is missing or not readable JSON")
    tag = data.get("tag") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not tag:
        raise JobError(f"{record} names no tag")
    return tag


def _outside_ais_max(root):
    """Return every path under root that differs from HEAD, untracked files included, outside ais-max/."""
    entries = _git(root, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        status, path = entry[:2], entry[3:]
        if "R" in status or "C" in status:
            i += 1  # a rename or copy is followed by its source path, which is not a separate change
        if path == "ais-max" or path.startswith("ais-max/"):
            continue
        paths.append(path)
    return paths


def _run_checks(checks, root):
    for command in checks:
        try:
            result = subprocess.run(list(command), cwd=root, capture_output=True, text=True)
        except OSError as error:
            raise JobError(f"could not run check {shlex.join(command)}: {error}")
        if result.returncode != 0:
            raise JobError(f"check failed: {shlex.join(command)}")


def _open_prs(gh, root):
    out = _gh(gh, root, "pr", "list", "--state", "open", "--json", "number,headRefName,url", "--limit", "200")
    try:
        return json.loads(out or "[]")
    except ValueError:
        raise JobError("gh pr list did not return JSON")


def _commit_and_push(root, branch, old, new):
    """Commit root/ais-max alone on branch, from the checked-out base, and force-push it to origin."""
    _git(root, "checkout", "-q", "-B", branch)
    _git(root, "add", "-A", "--", "ais-max")
    _git(root, *_AUTHOR, "commit", "-q", "-m", f"Sync ais-max from {old} to {new}", "--", "ais-max")
    _git(root, "push", "-q", "--force", "origin", branch)


def _open_pr(gh, root, base, branch, old, new):
    """Open the sync PR against base and return its URL."""
    body = (f"Rebuilds ais-max from Custom-skills {new}, replacing {old}.\n\n"
            "Opened by scripts/scheduled-sync.py when Custom-skills cuts a new release tag.\n")
    with tempfile.TemporaryDirectory() as scratch:
        body_file = Path(scratch) / "body.md"
        body_file.write_text(body)
        out = _gh(gh, root, "pr", "create", "--base", base, "--head", branch,
                  "--title", f"Sync ais-max from {old} to {new}", "--body-file", str(body_file))
    lines = out.strip().splitlines()
    if not lines:
        raise JobError("gh pr create printed no PR URL")
    return lines[-1].strip()


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
    tag = latest_tag(repo)
    if tag is None:
        raise JobError(f"{repo} has no release tag of the form vX.Y.Z")
    recorded = _recorded_tag(root)
    if recorded == tag:
        return UP_TO_DATE

    try:
        _sync_ais_max.sync(tag, repo=repo, ais=root / "ais", dest=root / "ais-max")
    except _sync_ais_max.SyncError as error:
        raise JobError(str(error))

    stray = _outside_ais_max(root)
    if stray:
        raise JobError("changes outside ais-max/: " + ", ".join(stray))

    _run_checks(checks, root)

    open_prs = _open_prs(gh, root)
    base = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if base == "HEAD":
        raise JobError("root is on a detached HEAD; check out the PR base branch first")

    branch = BRANCH_PREFIX + tag
    _commit_and_push(root, branch, recorded, tag)

    existing = next((pr for pr in open_prs if pr.get("headRefName") == branch), None)
    if existing is not None:
        url, outcome = existing["url"], UPDATED
    else:
        url, outcome = _open_pr(gh, root, base, branch, recorded, tag), OPENED

    for pr in open_prs:
        name = pr.get("headRefName", "")
        if name.startswith(BRANCH_PREFIX) and name != branch:
            _gh(gh, root, "pr", "close", str(pr["number"]), "--comment", f"Superseded by {url}")
            _git(root, "push", "-q", "origin", "--delete", name)

    if auto_merge:
        _gh(gh, root, "pr", "merge", url, "--auto")
    return outcome


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
    parser = argparse.ArgumentParser(description="Sync ais-max to the newest Custom-skills release tag.")
    try:
        parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:
        return stop.code

    try:
        outcome = run()
    except JobError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Sync ais-max: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
