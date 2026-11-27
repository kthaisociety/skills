"""Tests for scripts/scheduled-sync.py, the scheduled ais-max sync.

Every run() test works in a temp folder: a fake Custom-skills git repo, a
fake checkout of this repo with ais/ and an ais-max/ synced at v2.1.0, a
bare repo as its origin, and a fake gh that logs each call. Git's global
and system config are switched off while run() works, so the job has to
set its own commit author, as it will on a CI runner.

The TestMain tests run the script itself against this repo, with git
redirected from the real Custom-skills URL to a fake repo tagged so that
nothing is due, so they never write to this checkout.
"""

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "scheduled-sync.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


job = _load("scheduled_sync", SCRIPT)
sync_ais_max = _load("sync_ais_max_for_job", ROOT / "scripts" / "sync-ais-max.py")

JobError = job.JobError
NEW_PR_URL = "https://github.com/kthaisociety/skills/pull/99"
NEW_BRANCH = "sync/ais-max-v2.2.0"
TITLE = "Sync ais-max from v2.1.0 to v2.2.0"
MAX_LIST = ["./kanban/new-ticket", "./kanban/helper-skill", "./kanban/architect-ticket"]
AIS_BASE_FILES = {
    "new-ticket": "ticket-shapes.md",
    "grill-docs": "RECORD-FORMAT.md",
    "pr-ticket": "ticket-pr.md",
}

FAKE_GH = """#!{python}
import json, pathlib, sys
here = pathlib.Path(__file__).parent
args = sys.argv[1:]
entry = {{"args": args}}
if "--body-file" in args:
    path = args[args.index("--body-file") + 1]
    entry["body"] = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text()
elif "--body" in args:
    entry["body"] = args[args.index("--body") + 1]
with open(here / "calls.jsonl", "a") as log:
    log.write(json.dumps(entry) + "\\n")
fail = here / "fail"
if fail.exists() and args[:2] == fail.read_text().split():
    print("gh: refused", file=sys.stderr)
    sys.exit(1)
if args[:2] == ["pr", "list"]:
    print((here / "open.json").read_text())
elif args[:2] == ["pr", "create"]:
    print("{url}")
"""


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false", *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def marketplace(plugin="max"):
    return json.dumps({"name": "custom-skills",
                       "plugins": [{"name": plugin, "skills": MAX_LIST}]}, indent=2)


def new_source(path):
    """Create an empty fake Custom-skills repo at path."""
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    for entry in MAX_LIST:
        write(path / entry / "SKILL.md", f"{Path(entry).name}\n")
    write(path / ".claude-plugin" / "marketplace.json", marketplace())
    return path


def add_tag(source, tag, plugin="max"):
    """Commit a change to source and tag it."""
    write(source / "kanban" / "architect-ticket" / "SKILL.md", f"architect at {tag}\n")
    write(source / ".claude-plugin" / "marketplace.json", marketplace(plugin))
    git(source, "add", "-A")
    git(source, "commit", "-q", "-m", tag)
    git(source, "tag", tag)


def make_source(path, tags):
    new_source(path)
    for tag in tags:
        add_tag(path, tag)
    return path


def make_root(tmp, source):
    """A fake checkout of this repo, on main, with ais-max synced at v2.1.0 and pushed to origin."""
    root = tmp / "root"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for skill, file in AIS_BASE_FILES.items():
        write(root / "ais" / skill / "SKILL.md", f"ais {skill}\n")
        write(root / "ais" / skill / file, f"ais {file}\n")
    write(root / "README.md", "fake repo\n")
    sync_ais_max.sync("v2.1.0", repo=str(source), ais=root / "ais", dest=root / "ais-max")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    origin = tmp / "origin.git"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(origin))
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "-u", "origin", "main")
    return root


def make_gh(folder, open_prs=(), fail=None):
    """A fake gh in folder. Returns its path."""
    folder.mkdir()
    gh = folder / "gh"
    gh.write_text(FAKE_GH.format(python=sys.executable, url=NEW_PR_URL))
    gh.chmod(0o755)
    (folder / "open.json").write_text(json.dumps(list(open_prs)))
    (folder / "calls.jsonl").write_text("")
    if fail:
        (folder / "fail").write_text(fail)
    return gh


def gh_calls(gh):
    lines = (gh.parent / "calls.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines if line]


def calls_of(gh, *command):
    return [call for call in gh_calls(gh) if call["args"][:len(command)] == list(command)]


def flag(call, name):
    args = call["args"]
    return args[args.index(name) + 1] if name in args else None


def origin_refs(root):
    out = git(root, "ls-remote", "origin")
    return dict(reversed(line.split("\t")) for line in out.splitlines())


def recorded_tag_on(root, ref):
    git(root, "fetch", "-q", "origin")
    return json.loads(git(root, "show", f"{ref}:ais-max/.source.json"))["tag"]


def pr(number, branch):
    return {"number": number, "headRefName": branch,
            "url": f"https://github.com/kthaisociety/skills/pull/{number}", "title": branch}


def failing_check(code=3):
    return (sys.executable, "-c", f"import sys; sys.exit({code})")


def tag_check(tag):
    """A check that passes only when run from a root whose ais-max records tag."""
    return (sys.executable, "-c",
            "import json, sys; "
            f"sys.exit(0 if json.load(open('ais-max/.source.json'))['tag'] == {tag!r} else 1)")


class JobCase(unittest.TestCase):
    """A fresh temp world per test. Subclasses set TAGS and OPEN_PRS."""

    TAGS = ("v2.1.0", "v2.2.0")
    OPEN_PRS = ()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.source = make_source(self.tmp / "source", self.TAGS)
        self.root = make_root(self.tmp, self.source)
        self.gh = make_gh(self.tmp / "bin", self.OPEN_PRS)
        empty = self.tmp / "empty.gitconfig"
        empty.write_text("")
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": str(empty),
                                           "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)

    def run_job(self, checks=(), auto_merge=False, gh=None):
        return job.run(repo=str(self.source), root=self.root, gh=str(gh or self.gh),
                       checks=checks, auto_merge=auto_merge)

    def run_failing(self, **kwargs):
        with self.assertRaises(JobError) as caught:
            self.run_job(**kwargs)
        return caught.exception


class TestLatestTag(unittest.TestCase):
    """latest_tag(repo) picks the newest vX.Y.Z tag by version number."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.source = new_source(Path(self._tmp.name) / "source")

    def test_returns_the_highest_tag(self):
        """Of two release tags, the higher version wins."""
        for tag in ("v2.1.0", "v2.2.0"):
            add_tag(self.source, tag)
        self.assertEqual(job.latest_tag(str(self.source)), "v2.2.0")

    def test_compares_parts_as_numbers(self):
        """v2.10.0 is newer than v2.9.0, even though it sorts lower as text."""
        for tag in ("v2.10.0", "v2.9.0"):
            add_tag(self.source, tag)
        self.assertEqual(job.latest_tag(str(self.source)), "v2.10.0")

    def test_ignores_tag_dates(self):
        """A lower version tagged later does not count as newer."""
        for tag in ("v2.0.0", "v1.0.0"):
            add_tag(self.source, tag)
        self.assertEqual(job.latest_tag(str(self.source)), "v2.0.0")

    def test_ignores_tags_that_are_not_release_tags(self):
        """Tags not exactly of the form vX.Y.Z are never picked, however high."""
        add_tag(self.source, "v1.0.0")
        for bad in ("v9.9", "v9.9.9-rc1", "9.9.9", "v9.9.9.9", "release-v9.9.9", "V9.9.9"):
            add_tag(self.source, bad)
        self.assertEqual(job.latest_tag(str(self.source)), "v1.0.0")

    def test_returns_none_when_only_other_tags_exist(self):
        """A repo whose tags are all non-release tags has no newest release tag."""
        for bad in ("v1.0", "latest"):
            add_tag(self.source, bad)
        self.assertIsNone(job.latest_tag(str(self.source)))

    def test_returns_none_for_a_repo_with_no_tags(self):
        """A repo with no tags at all has no newest release tag."""
        write(self.source / "x", "x\n")
        git(self.source, "add", "-A")
        git(self.source, "commit", "-q", "-m", "x")
        self.assertIsNone(job.latest_tag(str(self.source)))

    def test_raises_when_repo_cannot_be_listed(self):
        """A path that is not a git repo raises JobError."""
        missing = Path(self._tmp.name) / "not-a-repo"
        missing.mkdir()
        with self.assertRaises(JobError):
            job.latest_tag(str(missing))

    def test_error_names_the_repo(self):
        """The JobError for an unlistable repo names that repo."""
        missing = str(Path(self._tmp.name) / "not-a-repo")
        with self.assertRaises(JobError) as caught:
            job.latest_tag(missing)
        self.assertIn(missing, str(caught.exception))


class TestUpToDate(JobCase):
    """The newest tag matches the record: the job ends and opens nothing."""

    TAGS = ("v2.1.0",)

    def test_returns_up_to_date(self):
        """A matching tag returns UP_TO_DATE."""
        self.assertEqual(self.run_job(), job.UP_TO_DATE)

    def test_calls_no_gh(self):
        """A matching tag makes no gh call at all."""
        self.run_job()
        self.assertEqual(gh_calls(self.gh), [])

    def test_pushes_nothing(self):
        """A matching tag leaves origin as it was."""
        before = origin_refs(self.root)
        self.run_job()
        self.assertEqual(origin_refs(self.root), before)

    def test_leaves_the_working_tree_clean(self):
        """A matching tag writes nothing to the checkout."""
        self.run_job()
        self.assertEqual(git(self.root, "status", "--porcelain"), "")

    def test_runs_no_checks(self):
        """A matching tag skips the checks, so a failing check can't fail the job."""
        self.assertEqual(self.run_job(checks=[failing_check()]), job.UP_TO_DATE)


class TestOpensPr(JobCase):
    """A new tag with no sync PR open: sync, check, push, open one."""

    def test_returns_opened(self):
        """A new tag with no open sync PR returns OPENED."""
        self.assertEqual(self.run_job(), job.OPENED)

    def test_opens_one_pr(self):
        """Exactly one PR is opened."""
        self.run_job()
        self.assertEqual(len(calls_of(self.gh, "pr", "create")), 1)

    def test_pushes_a_branch_named_after_the_tag(self):
        """The sync lands on origin as branch sync/ais-max-<new tag>."""
        self.run_job()
        self.assertIn(f"refs/heads/{NEW_BRANCH}", origin_refs(self.root))

    def test_pushed_branch_records_the_new_tag(self):
        """The pushed branch's sync record names the new tag."""
        self.run_job()
        self.assertEqual(recorded_tag_on(self.root, f"origin/{NEW_BRANCH}"), "v2.2.0")

    def test_pushed_branch_changes_only_ais_max(self):
        """The pushed branch differs from main only under ais-max/."""
        self.run_job()
        git(self.root, "fetch", "-q", "origin")
        changed = git(self.root, "diff", "--name-only", "origin/main", f"origin/{NEW_BRANCH}")
        self.assertEqual([p for p in changed.splitlines() if not p.startswith("ais-max/")], [])

    def test_leaves_main_on_origin_alone(self):
        """origin's main is not moved by the job."""
        before = origin_refs(self.root)["refs/heads/main"]
        self.run_job()
        self.assertEqual(origin_refs(self.root)["refs/heads/main"], before)

    def test_pr_title_names_both_tags(self):
        """The PR title reads "Sync ais-max from <old> to <new>"."""
        self.run_job()
        self.assertEqual(flag(calls_of(self.gh, "pr", "create")[0], "--title"), TITLE)

    def test_pr_body_names_the_old_tag(self):
        """The PR body names the tag ais-max moves from."""
        self.run_job()
        self.assertIn("v2.1.0", calls_of(self.gh, "pr", "create")[0]["body"])

    def test_pr_body_names_the_new_tag(self):
        """The PR body names the tag ais-max moves to."""
        self.run_job()
        self.assertIn("v2.2.0", calls_of(self.gh, "pr", "create")[0]["body"])

    def test_pr_targets_the_checked_out_branch(self):
        """The PR's base is the branch root had checked out."""
        self.run_job()
        self.assertEqual(flag(calls_of(self.gh, "pr", "create")[0], "--base"), "main")

    def test_pr_comes_from_the_sync_branch(self):
        """The PR's head is the pushed sync branch."""
        self.run_job()
        self.assertEqual(flag(calls_of(self.gh, "pr", "create")[0], "--head"), NEW_BRANCH)

    def test_checks_run_on_the_synced_tree(self):
        """Checks run from root after the sync, so they see the new tag."""
        self.assertEqual(self.run_job(checks=[tag_check("v2.2.0")]), job.OPENED)

    def test_auto_merge_off_never_asks_to_merge(self):
        """With auto_merge false, gh is never asked to merge."""
        self.run_job(auto_merge=False)
        self.assertEqual(calls_of(self.gh, "pr", "merge"), [])

    def test_auto_merge_on_asks_for_auto_merge(self):
        """With auto_merge true, the PR is set to merge once its checks pass."""
        self.run_job(auto_merge=True)
        self.assertIn("--auto", calls_of(self.gh, "pr", "merge")[0]["args"])


class TestFailedCheck(JobCase):
    """A failing check fails the job and opens no PR."""

    def test_raises(self):
        """A check exiting non-zero raises JobError."""
        self.run_failing(checks=[failing_check()])

    def test_error_names_the_check(self):
        """The JobError names the command that failed."""
        error = self.run_failing(checks=[tag_check("v2.2.0"), failing_check(7)])
        self.assertIn("sys.exit(7)", str(error))

    def test_pushes_nothing(self):
        """A failed check leaves origin as it was."""
        before = origin_refs(self.root)
        self.run_failing(checks=[failing_check()])
        self.assertEqual(origin_refs(self.root), before)

    def test_opens_no_pr(self):
        """A failed check opens no PR."""
        self.run_failing(checks=[failing_check()])
        self.assertEqual(calls_of(self.gh, "pr", "create"), [])


class TestDiffOutsideAisMax(JobCase):
    """A change outside ais-max fails the job and opens no PR."""

    def setUp(self):
        super().setUp()
        write(self.root / "stray.txt", "not ais-max\n")

    def test_raises(self):
        """An untracked file outside ais-max raises JobError."""
        self.run_failing()

    def test_error_names_the_path(self):
        """The JobError names the path outside ais-max."""
        self.assertIn("stray.txt", str(self.run_failing()))

    def test_pushes_nothing(self):
        """A change outside ais-max leaves origin as it was."""
        before = origin_refs(self.root)
        self.run_failing()
        self.assertEqual(origin_refs(self.root), before)

    def test_opens_no_pr(self):
        """A change outside ais-max opens no PR."""
        self.run_failing()
        self.assertEqual(calls_of(self.gh, "pr", "create"), [])

    def test_modified_tracked_file_also_fails(self):
        """An edit to a tracked file outside ais-max fails the job too."""
        (self.root / "stray.txt").unlink()
        write(self.root / "README.md", "edited\n")
        self.assertIn("README.md", str(self.run_failing()))


class TestSameTagPrOpen(JobCase):
    """A sync PR for the same tag is open: update it, open no second one."""

    OPEN_PRS = (pr(5, NEW_BRANCH),)

    def setUp(self):
        super().setUp()
        git(self.root, "checkout", "-q", "-b", NEW_BRANCH)
        write(self.root / "ais-max" / "stale.md", "stale\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "stale sync")
        git(self.root, "push", "-q", "origin", NEW_BRANCH)
        git(self.root, "checkout", "-q", "main")
        git(self.root, "branch", "-q", "-D", NEW_BRANCH)

    def test_returns_updated(self):
        """An open PR on the same branch returns UPDATED."""
        self.assertEqual(self.run_job(), job.UPDATED)

    def test_opens_no_second_pr(self):
        """No new PR is opened beside the existing one."""
        self.run_job()
        self.assertEqual(calls_of(self.gh, "pr", "create"), [])

    def test_replaces_the_branch_on_origin(self):
        """The branch on origin is replaced by a fresh sync, dropping the stale commit."""
        self.run_job()
        git(self.root, "fetch", "-q", "origin")
        files = git(self.root, "ls-tree", "-r", "--name-only", f"origin/{NEW_BRANCH}")
        self.assertNotIn("ais-max/stale.md", files.splitlines())

    def test_replaced_branch_records_the_new_tag(self):
        """The replaced branch's sync record names the new tag."""
        self.run_job()
        self.assertEqual(recorded_tag_on(self.root, f"origin/{NEW_BRANCH}"), "v2.2.0")

    def test_keeps_the_pr_open(self):
        """The same-tag PR is not closed."""
        self.run_job()
        self.assertEqual(calls_of(self.gh, "pr", "close"), [])


class TestOlderTagPrOpen(JobCase):
    """A sync PR for another tag is open: open the new one, close the old one."""

    OLD_BRANCH = "sync/ais-max-v2.1.5"
    OPEN_PRS = (pr(4, OLD_BRANCH), pr(7, "feature-x"))

    def setUp(self):
        super().setUp()
        git(self.root, "push", "-q", "origin", f"main:refs/heads/{self.OLD_BRANCH}")
        git(self.root, "push", "-q", "origin", "main:refs/heads/feature-x")

    def test_returns_opened(self):
        """A new tag beside an older sync PR returns OPENED."""
        self.assertEqual(self.run_job(), job.OPENED)

    def test_opens_the_new_pr(self):
        """The new tag gets its own PR."""
        self.run_job()
        self.assertEqual(len(calls_of(self.gh, "pr", "create")), 1)

    def test_closes_the_old_pr(self):
        """The older sync PR is closed."""
        self.run_job()
        closed = [call["args"][2] for call in calls_of(self.gh, "pr", "close")]
        self.assertIn("4", closed)

    def test_close_comment_links_the_new_pr(self):
        """The older PR is closed with a comment linking the new one."""
        self.run_job()
        close = next(c for c in calls_of(self.gh, "pr", "close") if c["args"][2] == "4")
        self.assertIn(NEW_PR_URL, flag(close, "--comment"))

    def test_deletes_the_old_branch(self):
        """The older sync PR's branch is deleted from origin."""
        self.run_job()
        self.assertNotIn(f"refs/heads/{self.OLD_BRANCH}", origin_refs(self.root))

    def test_leaves_other_prs_open(self):
        """A PR whose branch is not a sync branch is not closed."""
        self.run_job()
        closed = [call["args"][2] for call in calls_of(self.gh, "pr", "close")]
        self.assertNotIn("7", closed)

    def test_leaves_other_branches_alone(self):
        """A branch that is not a sync branch stays on origin."""
        self.run_job()
        self.assertIn("refs/heads/feature-x", origin_refs(self.root))


class TestRunFailures(JobCase):
    """Each documented failure raises JobError and touches nothing on GitHub."""

    def test_no_release_tag_raises(self):
        """A Custom-skills repo with no release tag raises JobError."""
        for tag in ("v2.1.0", "v2.2.0"):
            git(self.source, "tag", "-d", tag)
        self.run_failing()

    def test_missing_record_raises(self):
        """An ais-max with no sync record raises JobError."""
        (self.root / "ais-max" / ".source.json").unlink()
        git(self.root, "commit", "-q", "-am", "drop record")
        self.run_failing()

    def test_record_without_tag_raises(self):
        """A sync record that names no tag raises JobError."""
        write(self.root / "ais-max" / ".source.json", "{}\n")
        git(self.root, "commit", "-q", "-am", "empty record")
        self.run_failing()

    def test_failed_sync_raises(self):
        """A new tag the sync rejects raises JobError."""
        add_tag(self.source, "v2.3.0", plugin="not-max")
        self.run_failing()

    def test_failed_sync_carries_the_sync_message(self):
        """The JobError for a failed sync carries the sync's own message."""
        add_tag(self.source, "v2.3.0", plugin="not-max")
        self.assertIn('lists no plugin named "max"', str(self.run_failing()))

    def test_failed_sync_pushes_nothing(self):
        """A failed sync leaves origin as it was."""
        add_tag(self.source, "v2.3.0", plugin="not-max")
        before = origin_refs(self.root)
        self.run_failing()
        self.assertEqual(origin_refs(self.root), before)

    def test_failed_sync_calls_no_gh(self):
        """A failed sync makes no gh call."""
        add_tag(self.source, "v2.3.0", plugin="not-max")
        self.run_failing()
        self.assertEqual(gh_calls(self.gh), [])

    def test_unreadable_record_raises(self):
        """A sync record that is not JSON raises JobError."""
        write(self.root / "ais-max" / ".source.json", "not json\n")
        git(self.root, "commit", "-q", "-am", "broken record")
        self.run_failing()

    def test_detached_head_raises(self):
        """A root on a detached HEAD, with no base branch to open a PR against, raises JobError."""
        git(self.root, "checkout", "-q", "--detach")
        self.run_failing()

    def test_detached_head_pushes_nothing(self):
        """A detached HEAD leaves origin as it was."""
        git(self.root, "checkout", "-q", "--detach")
        before = origin_refs(self.root)
        self.run_failing()
        self.assertEqual(origin_refs(self.root), before)

    def test_failed_gh_raises(self):
        """A gh pr create that fails raises JobError."""
        gh = make_gh(self.tmp / "bin-fail", fail="pr create")
        self.run_failing(gh=gh)


class TestMain(unittest.TestCase):
    """The script run from the command line, against this repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.source = new_source(self.tmp / "source")
        config = self.tmp / "redirect.gitconfig"
        config.write_text(f'[url "{self.source}"]\n\tinsteadOf = {job.SOURCE_REPO}\n')
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM="1")

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=self.env,
                              capture_output=True, text=True)

    def recorded_tag(self):
        return json.loads((ROOT / "ais-max" / ".source.json").read_text())["tag"]

    def test_rejects_arguments(self):
        """Any argument exits 2."""
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(job.main(["v2.2.0"]), 2)

    def test_up_to_date_exits_zero(self):
        """When nothing is due, the script exits 0."""
        add_tag(self.source, self.recorded_tag())
        self.assertEqual(self.run_script().returncode, 0)

    def test_up_to_date_prints_the_outcome(self):
        """When nothing is due, the last stdout line is "Sync ais-max: up to date"."""
        add_tag(self.source, self.recorded_tag())
        self.assertEqual(self.run_script().stdout.strip().splitlines()[-1],
                         "Sync ais-max: up to date")

    def test_job_error_exits_one(self):
        """A JobError exits 1."""
        add_tag(self.source, "latest")
        self.assertEqual(self.run_script().returncode, 1)

    def test_job_error_prints_to_stderr(self):
        """A JobError prints "error: <message>" to stderr."""
        add_tag(self.source, "latest")
        self.assertTrue(self.run_script().stderr.startswith("error: "))


if __name__ == "__main__":
    unittest.main()
