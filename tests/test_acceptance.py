"""Acceptance tests for #10, the release planner in scripts/plan-release.py.

Every test runs against a fake repo built in a temp folder with real git, so
none of them reads this repo's own tags or ais-max/ sync record.
"""

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "plan-release.py"
spec = importlib.util.spec_from_file_location("plan_release", SCRIPT)
plan_release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan_release)

plan = plan_release.plan
main = plan_release.main
PlanError = plan_release.PlanError

SOURCE_TAG = "v2.1.0"


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def write_record(repo, data):
    path = repo / "ais-max" / ".source.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    return path


class RepoCase(unittest.TestCase):
    """A fresh git repo on main with one commit holding a valid sync record."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        write_record(self.repo, json.dumps({"commit": "abc", "tag": SOURCE_TAG}))
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "Initial commit")

    def commit(self, title):
        git(self.repo, "commit", "-q", "--allow-empty", "-m", title)

    def tag(self, name):
        git(self.repo, "tag", name)

    def tagged(self, tag, *titles):
        """Tag HEAD as tag, then commit each title after it."""
        self.tag(tag)
        for title in titles:
            self.commit(title)

    def version(self):
        return plan(self.repo).version


class TestFirstRelease(RepoCase):

    def test_no_release_tag_plans_1_0_0(self):
        """With no release tag yet, the version is 1.0.0."""
        self.commit("fix: a thing")
        self.assertEqual(self.version(), "1.0.0")

    def test_no_release_tag_ignores_breaking_titles(self):
        """With no release tag yet, a breaking title still gives 1.0.0."""
        self.commit("feat!: drop everything")
        self.assertEqual(self.version(), "1.0.0")

    def test_no_release_tag_with_only_the_first_commit_plans_1_0_0(self):
        """A repo whose only commit is untagged still plans 1.0.0."""
        self.assertEqual(self.version(), "1.0.0")

    def test_no_release_tag_reports_no_last_tag(self):
        """With no release tag yet, last_tag is None."""
        self.assertIsNone(plan(self.repo).last_tag)


class TestBump(RepoCase):

    def test_fix_bumps_patch(self):
        """A fix title after v1.2.3 gives 1.2.4."""
        self.tagged("v1.2.3", "fix: a thing")
        self.assertEqual(self.version(), "1.2.4")

    def test_docs_bumps_patch(self):
        """A docs title is anything else, so it bumps patch."""
        self.tagged("v1.2.3", "docs: explain")
        self.assertEqual(self.version(), "1.2.4")

    def test_untyped_title_bumps_patch(self):
        """A title with no type bumps patch."""
        self.tagged("v1.2.3", "Refresh the catalog")
        self.assertEqual(self.version(), "1.2.4")

    def test_patch_counts_past_nine(self):
        """Version parts are integers, so 1.2.9 bumps to 1.2.10."""
        self.tagged("v1.2.9", "fix: a thing")
        self.assertEqual(self.version(), "1.2.10")

    def test_feat_bumps_minor_and_resets_patch(self):
        """A feat title after v1.2.3 gives 1.3.0."""
        self.tagged("v1.2.3", "feat: a thing")
        self.assertEqual(self.version(), "1.3.0")

    def test_scoped_feat_bumps_minor(self):
        """feat(scope): counts as a feat."""
        self.tagged("v1.2.3", "feat(build): a thing")
        self.assertEqual(self.version(), "1.3.0")

    def test_feat_in_this_repos_title_style_bumps_minor(self):
        """A squash-merged title like this repo's, "feat: (1.5) ... (#18)", is a feat."""
        self.tagged("v1.2.3", "feat: (1.5) Build the Codex marketplace tree (#18)")
        self.assertEqual(self.version(), "1.3.0")

    def test_feature_is_not_feat(self):
        """A type that only starts with feat, like feature:, bumps patch."""
        self.tagged("v1.2.3", "feature: a thing")
        self.assertEqual(self.version(), "1.2.4")

    def test_capitalised_feat_is_not_feat(self):
        """Types are lowercase, so Feat: bumps patch."""
        self.tagged("v1.2.3", "Feat: a thing")
        self.assertEqual(self.version(), "1.2.4")

    def test_feat_among_fixes_bumps_minor(self):
        """One feat among fixes bumps minor."""
        self.tagged("v1.2.3", "fix: one", "feat: two", "fix: three")
        self.assertEqual(self.version(), "1.3.0")

    def test_breaking_feat_bumps_major_and_resets_the_rest(self):
        """feat!: after v1.2.3 gives 2.0.0."""
        self.tagged("v1.2.3", "feat!: drop a thing")
        self.assertEqual(self.version(), "2.0.0")

    def test_breaking_scoped_fix_bumps_major(self):
        """fix(build)!: is breaking too, whatever the type."""
        self.tagged("v1.2.3", "fix(build)!: change the layout")
        self.assertEqual(self.version(), "2.0.0")

    def test_breaking_in_this_repos_title_style_bumps_major(self):
        """"feat!: Remove the skills.sh collection (#3) (#15)" is breaking."""
        self.tagged("v1.2.3", "feat!: Remove the skills.sh collection (#3) (#15)")
        self.assertEqual(self.version(), "2.0.0")

    def test_breaking_among_feats_bumps_major(self):
        """One breaking title among feats and fixes bumps major."""
        self.tagged("v1.2.3", "feat: one", "chore!: two", "fix: three")
        self.assertEqual(self.version(), "2.0.0")

    def test_breaking_change_words_without_bang_are_not_breaking(self):
        """BREAKING CHANGE in a title with no "!" isn't breaking."""
        self.tagged("v1.2.3", "fix: BREAKING CHANGE in the layout")
        self.assertEqual(self.version(), "1.2.4")

    def test_breaking_change_in_body_is_not_breaking(self):
        """Only titles count, so BREAKING CHANGE in a commit body bumps nothing extra."""
        self.tag("v1.2.3")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "fix: a thing",
            "-m", "BREAKING CHANGE: the layout moved")
        self.assertEqual(self.version(), "1.2.4")

    def test_bang_after_the_first_colon_is_not_breaking(self):
        """A "!:" later in the title, not before its first colon, isn't breaking."""
        self.tagged("v1.2.3", "fix: wow!: that broke")
        self.assertEqual(self.version(), "1.2.4")

    def test_commits_before_the_last_tag_dont_count(self):
        """A breaking title before the last tag doesn't bump this release."""
        self.commit("feat!: old break")
        self.tagged("v1.2.3", "fix: a thing")
        self.assertEqual(self.version(), "1.2.4")

    def test_commits_on_a_merged_branch_count(self):
        """A feat on a branch merged without squashing bumps minor."""
        self.tag("v1.2.3")
        git(self.repo, "checkout", "-q", "-b", "side")
        self.commit("feat: from the side")
        git(self.repo, "checkout", "-q", "main")
        self.commit("fix: on main")
        git(self.repo, "merge", "-q", "--no-ff", "-m", "Merge branch side", "side")
        self.assertEqual(self.version(), "1.3.0")


class TestLastTag(RepoCase):

    def test_last_tag_is_reported(self):
        """last_tag names the release tag the version counts from."""
        self.tagged("v1.2.3", "fix: a thing")
        self.assertEqual(plan(self.repo).last_tag, "v1.2.3")

    def test_highest_version_wins_over_newest_tag(self):
        """v1.10.0 on an older commit beats v1.9.0 on a newer one."""
        self.tag("v1.10.0")
        self.tagged("v1.9.0", "fix: a thing")
        self.assertEqual(plan(self.repo).last_tag, "v1.10.0")

    def test_version_counts_from_the_highest_tag(self):
        """With v1.10.0 the highest, a fix gives 1.10.1."""
        self.tag("v1.10.0")
        self.tagged("v1.9.0", "fix: a thing")
        self.assertEqual(self.version(), "1.10.1")

    def test_tags_of_other_shapes_are_ignored(self):
        """Tags that aren't vX.Y.Z don't count as releases."""
        self.tagged("v1.2.3", "fix: one")
        for name in ("v9.0", "v9.0.0-rc1", "9.0.0", "release-9", "vX.Y.Z"):
            self.tag(name)
        self.commit("fix: two")
        self.assertEqual(plan(self.repo).last_tag, "v1.2.3")

    def test_only_other_shaped_tags_means_first_release(self):
        """A repo with only non-release tags plans 1.0.0."""
        self.tagged("v9.0-beta", "fix: a thing")
        self.assertEqual(self.version(), "1.0.0")

    def test_tag_not_reachable_from_head_is_ignored(self):
        """A higher release tag on a branch HEAD doesn't contain doesn't count."""
        self.tag("v1.2.3")
        git(self.repo, "checkout", "-q", "-b", "stray")
        self.commit("fix: stray")
        self.tag("v9.0.0")
        git(self.repo, "checkout", "-q", "main")
        self.commit("fix: on main")
        self.assertEqual(plan(self.repo).last_tag, "v1.2.3")


class TestNothingToRelease(RepoCase):

    def test_no_commit_since_last_tag_raises(self):
        """HEAD on the last release tag raises PlanError."""
        self.tagged("v1.2.0")
        with self.assertRaises(PlanError):
            plan(self.repo)

    def test_no_commit_since_last_tag_says_so(self):
        """The message is exactly "nothing to release since v1.2.0"."""
        self.tagged("v1.2.0")
        with self.assertRaises(PlanError) as caught:
            plan(self.repo)
        self.assertEqual(str(caught.exception), "nothing to release since v1.2.0")

    def test_nothing_to_release_comes_before_a_bad_record(self):
        """With nothing to release and a broken record, the message is about the release."""
        self.tagged("v1.2.0")
        (self.repo / "ais-max" / ".source.json").unlink()
        with self.assertRaises(PlanError) as caught:
            plan(self.repo)
        self.assertEqual(str(caught.exception), "nothing to release since v1.2.0")


class TestSourceTag(RepoCase):

    def test_source_tag_comes_from_the_sync_record(self):
        """source_tag is the tag in ais-max/.source.json."""
        self.assertEqual(plan(self.repo).source_tag, SOURCE_TAG)

    def test_record_can_be_named(self):
        """A record passed in is read instead of the repo's own."""
        other = Path(self._tmp.name) / "other.json"
        other.write_text(json.dumps({"tag": "v7.0.0"}))
        self.assertEqual(plan(self.repo, record=other).source_tag, "v7.0.0")

    def assert_record_error(self, data):
        """Write data as the record, and assert plan() raises a PlanError naming its path."""
        path = self.repo / "ais-max" / ".source.json"
        if data is None:
            path.unlink()
        else:
            path.write_text(data)
        with self.assertRaises(PlanError) as caught:
            plan(self.repo)
        self.assertIn(str(Path("ais-max") / ".source.json"), str(caught.exception))

    def test_missing_record_raises_naming_it(self):
        """A missing record raises PlanError naming its path."""
        self.assert_record_error(None)

    def test_record_that_isnt_json_raises_naming_it(self):
        """A record that isn't JSON raises PlanError naming its path."""
        self.assert_record_error("{not json")

    def test_record_that_isnt_an_object_raises_naming_it(self):
        """A record holding a JSON list raises PlanError naming its path."""
        self.assert_record_error(json.dumps(["v2.1.0"]))

    def test_record_without_tag_raises_naming_it(self):
        """A record with no tag raises PlanError naming its path."""
        self.assert_record_error(json.dumps({"commit": "abc"}))

    def test_record_with_non_string_tag_raises_naming_it(self):
        """A record whose tag isn't a string raises PlanError naming its path."""
        self.assert_record_error(json.dumps({"tag": 2}))


class TestNotARepo(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        write_record(self.folder, json.dumps({"tag": SOURCE_TAG}))

    def test_folder_that_isnt_a_repo_raises(self):
        """A folder that isn't a git work tree raises PlanError."""
        with self.assertRaises(PlanError):
            plan(self.folder)

    def test_repo_without_commits_raises(self):
        """A git repo whose HEAD has no commit raises PlanError."""
        git(self.folder, "init", "-q", "-b", "main")
        with self.assertRaises(PlanError):
            plan(self.folder)


class TestReadsOnly(RepoCase):

    def test_plan_creates_no_tag(self):
        """Planning leaves the repo's tags as they were."""
        self.tagged("v1.2.3", "feat: a thing")
        before = git(self.repo, "tag", "--list")
        plan(self.repo)
        self.assertEqual(git(self.repo, "tag", "--list"), before)

    def test_plan_leaves_the_work_tree_clean(self):
        """Planning writes no file into the repo."""
        self.tagged("v1.2.3", "feat: a thing")
        plan(self.repo)
        self.assertEqual(git(self.repo, "status", "--porcelain", "--ignored"), "")

    def test_plan_moves_no_commit(self):
        """Planning leaves HEAD on the commit it started on."""
        self.tagged("v1.2.3", "feat: a thing")
        before = git(self.repo, "rev-parse", "HEAD")
        plan(self.repo)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), before)


class TestMain(RepoCase):

    def setUp(self):
        super().setUp()
        original = plan_release.ROOT
        plan_release.ROOT = self.repo
        self.addCleanup(setattr, plan_release, "ROOT", original)

    def run_main(self, argv=()):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_success_exits_0(self):
        """A plan exits 0."""
        self.tagged("v1.2.3", "feat: a thing")
        self.assertEqual(self.run_main()[0], 0)

    def test_success_prints_three_output_lines(self):
        """stdout is version, last_tag and source_tag as KEY=VALUE lines, in order."""
        self.tagged("v1.2.3", "feat: a thing")
        self.assertEqual(self.run_main()[1],
                         f"version=1.3.0\nlast_tag=v1.2.3\nsource_tag={SOURCE_TAG}\n")

    def test_first_release_prints_empty_last_tag(self):
        """With no release tag, the last_tag line has nothing after the =."""
        self.commit("fix: a thing")
        self.assertEqual(self.run_main()[1],
                         f"version=1.0.0\nlast_tag=\nsource_tag={SOURCE_TAG}\n")

    def test_success_prints_nothing_to_stderr(self):
        """A plan prints nothing to stderr."""
        self.tagged("v1.2.3", "feat: a thing")
        self.assertEqual(self.run_main()[2], "")

    def test_nothing_to_release_exits_1(self):
        """Nothing to release exits 1."""
        self.tagged("v1.2.0")
        self.assertEqual(self.run_main()[0], 1)

    def test_nothing_to_release_prints_the_error(self):
        """Nothing to release prints "error: nothing to release since v1.2.0" to stderr."""
        self.tagged("v1.2.0")
        self.assertEqual(self.run_main()[2], "error: nothing to release since v1.2.0\n")

    def test_error_prints_nothing_to_stdout(self):
        """A failed plan prints nothing to stdout, so no half plan reaches $GITHUB_OUTPUT."""
        self.tagged("v1.2.0")
        self.assertEqual(self.run_main()[1], "")

    def test_record_error_exits_1(self):
        """A broken sync record exits 1."""
        self.commit("fix: a thing")
        (self.repo / "ais-max" / ".source.json").unlink()
        self.assertEqual(self.run_main()[0], 1)

    def test_an_argument_exits_2(self):
        """Any argument is a usage error, exit 2."""
        self.commit("fix: a thing")
        self.assertEqual(self.run_main(["1.0.0"])[0], 2)


if __name__ == "__main__":
    unittest.main()
