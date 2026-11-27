"""Acceptance tests for #5: rebuild ais-max from a Custom-skills tag.

Every test runs against a fake Custom-skills git repo built in a temp folder,
so none of them touches the network or the real ais-max/, except the
TestCommittedAisMax tests, which read the ais-max/ committed in this repo.
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "sync-ais-max.py"
spec = importlib.util.spec_from_file_location("sync_ais_max", SCRIPT)
sync_ais_max = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_ais_max)

sync = sync_ais_max.sync
SyncError = sync_ais_max.SyncError

AIS_SKILLS = ("new-ticket", "grill-docs", "pr-ticket", "map-epic", "amend-pcr")
AIS_BASE_FILES = {
    "ticket-shapes.md": ("new-ticket", b"ais ticket shapes\n"),
    "RECORD-FORMAT.md": ("grill-docs", b"ais record format\n"),
    "ticket-pr.md": ("pr-ticket", b"ais ticket pr\n"),
}
BASE_LIST = [f"./kanban/{name}" for name in AIS_SKILLS] + [
    "./kanban/architect-ticket",
    "./kanban/helper-skill",
    "./behaviour/unslop",
]
HELPER_MISSING = (
    "helper-skill is missing from the max plugin at v9.2.0, so ticket-shapes.md, "
    "RECORD-FORMAT.md and ticket-pr.md have nowhere to go"
)


def git(repo, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
         "-c", "tag.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, text=True,
    ).stdout.strip()


def marketplace(skills, plugin="max"):
    data = {"name": "custom-skills", "plugins": [
        {"name": "other", "skills": ["./kanban/other"]},
        {"name": plugin, "skills": skills},
    ]}
    return json.dumps(data, indent=2).encode()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def commit_and_tag(repo, tag):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", tag)
    git(repo, "tag", tag)
    return git(repo, "rev-parse", "HEAD")


def build_source(repo):
    """Build the fake Custom-skills repo. Returns {tag: commit sha}."""
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    shas = {}
    for name in AIS_SKILLS + ("architect-ticket", "other"):
        write(repo / "kanban" / name / "SKILL.md", f"upstream {name}\n".encode())
    write(repo / "kanban" / "architect-ticket" / "nested" / "notes.md", b"nested notes\n")
    write(repo / "kanban" / "helper-skill" / "SKILL.md", b"upstream helper-skill\n")
    for file in AIS_BASE_FILES:
        write(repo / "kanban" / "helper-skill" / file, f"upstream copy of {file}\n".encode())
    write(repo / "behaviour" / "unslop" / "SKILL.md", b"upstream unslop\n")
    write(repo / "behaviour" / "unslop" / ".hidden", b"hidden file\n")
    write(repo / "behaviour" / "unslop" / ".hidden-dir" / "inside.md", b"hidden dir\n")
    write(repo / "behaviour" / "unslop" / "deep" / ".also-hidden", b"deep hidden\n")
    write(repo / "developer-tools" / "pro-con" / "SKILL.md", b"upstream pro-con\n")
    write(repo / "archive" / "architect-ticket" / "SKILL.md", b"old architect\n")
    mp = repo / ".claude-plugin" / "marketplace.json"

    write(mp, marketplace(BASE_LIST))
    shas["v1.0.0"] = commit_and_tag(repo, "v1.0.0")

    later = [s for s in BASE_LIST if s != "./behaviour/unslop"] + ["./developer-tools/pro-con"]
    write(mp, marketplace(later))
    shas["v1.1.0"] = commit_and_tag(repo, "v1.1.0")

    write(mp, marketplace(BASE_LIST + ["./archive/architect-ticket"]))
    shas["v9.0.0"] = commit_and_tag(repo, "v9.0.0")

    write(mp, marketplace(BASE_LIST + ["./kanban/ghost"]))
    shas["v9.1.0"] = commit_and_tag(repo, "v9.1.0")

    write(mp, marketplace([s for s in BASE_LIST if s != "./kanban/helper-skill"]))
    shas["v9.2.0"] = commit_and_tag(repo, "v9.2.0")

    write(mp, marketplace(BASE_LIST, plugin="not-max"))
    shas["v9.3.0"] = commit_and_tag(repo, "v9.3.0")

    mp.unlink()
    shas["v9.4.0"] = commit_and_tag(repo, "v9.4.0")
    return shas


def build_ais(ais):
    for name in AIS_SKILLS:
        write(ais / name / "SKILL.md", f"ais {name}\n".encode())
    for file, (skill, data) in AIS_BASE_FILES.items():
        write(ais / skill / file, data)


def snapshot(folder):
    """Every file and folder under folder, hidden ones included, with file bytes."""
    if not folder.exists():
        return None
    return {str(p.relative_to(folder)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(folder.rglob("*"))}


class SyncCase(unittest.TestCase):
    """A fresh work folder per test, holding ais/ and ais-max/, plus a shared source repo."""

    @classmethod
    def setUpClass(cls):
        cls._source_dir = tempfile.mkdtemp()
        cls.source = Path(cls._source_dir) / "custom-skills"
        cls.shas = build_source(cls.source)
        cls.repo = str(cls.source)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._source_dir)

    def setUp(self):
        self._work_dir = tempfile.mkdtemp()
        self.work = Path(self._work_dir)
        self.ais = self.work / "ais"
        self.dest = self.work / "ais-max"
        build_ais(self.ais)
        self.scratch = self.work / "scratch"
        self.scratch.mkdir()
        self._old_tempdir = tempfile.tempdir
        tempfile.tempdir = str(self.scratch)

    def tearDown(self):
        tempfile.tempdir = self._old_tempdir
        shutil.rmtree(self._work_dir)

    def run_sync(self, tag="v1.0.0"):
        return sync(tag, repo=self.repo, ais=self.ais, dest=self.dest)

    def seed_dest(self):
        write(self.dest / "stale-skill" / "SKILL.md", b"from an older sync\n")
        write(self.dest / ".source.json", b'{"commit": "old", "tag": "v0.0.1"}\n')


class TestSyncWrites(SyncCase):

    def test_returns_the_number_of_skills_written(self):
        """sync returns how many skill folders it wrote."""
        self.assertEqual(self.run_sync(), 3)

    def test_writes_each_listed_skill_except_the_ais_ones(self):
        """dest holds one folder per max skill whose name has no folder in ais."""
        self.run_sync()
        folders = {p.name for p in self.dest.iterdir() if p.is_dir()}
        self.assertEqual(folders, {"architect-ticket", "helper-skill", "unslop"})

    def test_skips_skills_not_listed_for_max(self):
        """A skill listed only by another plugin in the marketplace file is not written."""
        self.run_sync()
        self.assertFalse((self.dest / "other").exists())

    def test_skill_sits_flat_under_its_own_name(self):
        """A skill lands at dest/<name>, without its category folder."""
        self.run_sync()
        self.assertTrue((self.dest / "unslop" / "SKILL.md").is_file())

    def test_category_folders_are_not_written(self):
        """No category folder such as kanban or behaviour appears in dest."""
        self.run_sync()
        self.assertFalse((self.dest / "kanban").exists() or (self.dest / "behaviour").exists())

    def test_copies_skill_files_byte_for_byte(self):
        """A copied skill file holds exactly the bytes it has at the tag."""
        self.run_sync()
        self.assertEqual((self.dest / "architect-ticket" / "SKILL.md").read_bytes(),
                         b"upstream architect-ticket\n")

    def test_copies_nested_files(self):
        """Files in subfolders of a skill are copied too."""
        self.run_sync()
        self.assertEqual((self.dest / "architect-ticket" / "nested" / "notes.md").read_bytes(),
                         b"nested notes\n")

    def test_skips_hidden_files(self):
        """A file whose name starts with a dot is not copied."""
        self.run_sync()
        self.assertFalse((self.dest / "unslop" / ".hidden").exists())

    def test_skips_hidden_folders(self):
        """A folder whose name starts with a dot is not copied."""
        self.run_sync()
        self.assertFalse((self.dest / "unslop" / ".hidden-dir").exists())

    def test_skips_hidden_files_in_subfolders(self):
        """A dot file deeper in a skill is not copied either."""
        self.run_sync()
        self.assertFalse((self.dest / "unslop" / "deep" / ".also-hidden").exists())

    def test_helper_skill_base_files_come_from_ais(self):
        """Each base file in dest/helper-skill holds the bytes of its ais original."""
        self.run_sync()
        for file, (_, data) in AIS_BASE_FILES.items():
            with self.subTest(file=file):
                self.assertEqual((self.dest / "helper-skill" / file).read_bytes(), data)

    def test_helper_skill_keeps_its_own_files(self):
        """helper-skill's files that are not base files stay as they are at the tag."""
        self.run_sync()
        self.assertEqual((self.dest / "helper-skill" / "SKILL.md").read_bytes(),
                         b"upstream helper-skill\n")

    def test_record_holds_tag_and_commit(self):
        """The hidden record names the tag and the commit it points at."""
        self.run_sync()
        record = json.loads((self.dest / sync_ais_max.RECORD).read_text())
        self.assertEqual(record, {"commit": self.shas["v1.0.0"], "tag": "v1.0.0"})

    def test_record_is_sorted_indented_json_with_newline(self):
        """The record is written with sorted keys, two-space indent and a final newline."""
        self.run_sync()
        expected = json.dumps({"commit": self.shas["v1.0.0"], "tag": "v1.0.0"},
                              indent=2, sort_keys=True) + "\n"
        self.assertEqual((self.dest / sync_ais_max.RECORD).read_text(), expected)

    def test_record_is_the_only_hidden_entry(self):
        """The record is hidden, and it is the only dot-named entry at the top of dest."""
        self.run_sync()
        hidden = [p.name for p in self.dest.iterdir() if p.name.startswith(".")]
        self.assertEqual(hidden, [sync_ais_max.RECORD])

    def test_creates_dest_when_missing(self):
        """A first run with no dest folder creates it."""
        self.run_sync()
        self.assertTrue((self.dest / "unslop").is_dir())

    def test_removes_what_the_tag_does_not_list(self):
        """A folder left in dest by an older sync is gone after the run."""
        self.seed_dest()
        self.run_sync()
        self.assertFalse((self.dest / "stale-skill").exists())

    def test_never_writes_the_ais_folder(self):
        """ais is byte-identical after a sync."""
        before = snapshot(self.ais)
        self.run_sync()
        self.assertEqual(snapshot(self.ais), before)

    def test_writes_nothing_beside_dest(self):
        """Nothing outside dest changes, temp files included."""
        before = {p.name: snapshot(p) for p in self.work.iterdir() if p != self.dest}
        self.run_sync()
        after = {p.name: snapshot(p) for p in self.work.iterdir() if p != self.dest}
        self.assertEqual(after, before)


class TestSyncAcrossTags(SyncCase):

    def test_skill_added_in_a_later_tag_appears(self):
        """A skill the later tag adds to the max list is in dest after syncing it."""
        self.run_sync("v1.0.0")
        self.run_sync("v1.1.0")
        self.assertTrue((self.dest / "pro-con" / "SKILL.md").is_file())

    def test_skill_removed_in_a_later_tag_disappears(self):
        """A skill the later tag drops from the max list is gone after syncing it."""
        self.run_sync("v1.0.0")
        self.run_sync("v1.1.0")
        self.assertFalse((self.dest / "unslop").exists())

    def test_later_tag_updates_the_record(self):
        """Syncing a later tag rewrites the record to that tag and commit."""
        self.run_sync("v1.0.0")
        self.run_sync("v1.1.0")
        record = json.loads((self.dest / sync_ais_max.RECORD).read_text())
        self.assertEqual(record, {"commit": self.shas["v1.1.0"], "tag": "v1.1.0"})

    def test_same_tag_twice_leaves_no_diff(self):
        """A second run on the same tag leaves dest byte-identical."""
        self.run_sync()
        first = snapshot(self.dest)
        self.run_sync()
        self.assertEqual(snapshot(self.dest), first)

    def test_same_tag_picks_up_an_ais_base_file_edit(self):
        """Rerunning the same tag after an ais base file changes writes the new bytes (ADR-0005)."""
        self.run_sync()
        write(self.ais / "pr-ticket" / "ticket-pr.md", b"edited in ais\n")
        self.run_sync()
        self.assertEqual((self.dest / "helper-skill" / "ticket-pr.md").read_bytes(),
                         b"edited in ais\n")


class TestSyncStops(SyncCase):

    def assert_stops(self, tag, needle):
        with self.assertRaises(SyncError) as caught:
            self.run_sync(tag)
        self.assertIn(needle, str(caught.exception))

    def test_tag_not_in_release_form_stops(self):
        """A tag that is not vX.Y.Z raises SyncError naming the tag."""
        for tag in ("2.1.0", "v2.1", "v2.1.0-rc1", "latest", "", "v2.1.0 ", "main"):
            with self.subTest(tag=tag):
                self.assert_stops(tag, tag or "tag")

    def test_tag_that_does_not_exist_stops(self):
        """A well-formed tag the repo doesn't have raises SyncError naming the tag."""
        self.assert_stops("v7.7.7", "v7.7.7")

    def test_repo_that_cannot_be_cloned_stops(self):
        """A source repo git can't clone raises SyncError."""
        with self.assertRaises(SyncError):
            sync("v1.0.0", repo=str(self.work / "no-such-repo"), ais=self.ais, dest=self.dest)

    def test_duplicate_skill_names_stop(self):
        """Two listed folders with the same name raise SyncError naming it."""
        self.assert_stops("v9.0.0", "architect-ticket")

    def test_missing_listed_folder_stops(self):
        """A listed skill folder absent at the tag raises SyncError naming it."""
        self.assert_stops("v9.1.0", "ghost")

    def test_missing_helper_skill_stops_with_a_plain_message(self):
        """A max list without helper-skill raises SyncError with the fixed message."""
        with self.assertRaises(SyncError) as caught:
            self.run_sync("v9.2.0")
        self.assertEqual(str(caught.exception), HELPER_MISSING)

    def test_no_max_plugin_stops(self):
        """A marketplace file with no plugin named max raises SyncError."""
        self.assert_stops("v9.3.0", "max")

    def test_missing_marketplace_file_stops(self):
        """A tag without .claude-plugin/marketplace.json raises SyncError naming the file."""
        self.assert_stops("v9.4.0", "marketplace.json")

    def test_missing_ais_base_file_stops(self):
        """A missing ais base file raises SyncError naming it."""
        for file, (skill, _) in AIS_BASE_FILES.items():
            with self.subTest(file=file):
                original = self.ais / skill / file
                data = original.read_bytes()
                original.unlink()
                try:
                    self.assert_stops("v1.0.0", file)
                finally:
                    original.write_bytes(data)

    def test_every_stop_leaves_dest_untouched(self):
        """When sync raises SyncError, dest is exactly as it was before the run."""
        self.seed_dest()
        before = snapshot(self.dest)
        for tag in ("bad", "v7.7.7", "v9.0.0", "v9.1.0", "v9.2.0", "v9.3.0", "v9.4.0"):
            with self.subTest(tag=tag):
                with self.assertRaises(SyncError):
                    self.run_sync(tag)
                self.assertEqual(snapshot(self.dest), before)

    def test_missing_ais_base_file_leaves_dest_untouched(self):
        """A missing ais base file stops the run with dest exactly as it was."""
        self.seed_dest()
        before = snapshot(self.dest)
        (self.ais / "grill-docs" / "RECORD-FORMAT.md").unlink()
        with self.assertRaises(SyncError):
            self.run_sync()
        self.assertEqual(snapshot(self.dest), before)

    def test_stop_leaves_no_temp_files(self):
        """A stopped run deletes the temp files it made."""
        with self.assertRaises(SyncError):
            self.run_sync("v9.1.0")
        self.assertEqual(list(self.scratch.iterdir()), [])


class TestMain(SyncCase):
    """main, run as the maintainer runs it, from a copy of the project in a temp folder."""

    def setUp(self):
        super().setUp()
        write(self.work / "scripts" / "sync-ais-max.py", SCRIPT.read_bytes())
        self.env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1",
                        GIT_CONFIG_KEY_0=f"url.{self.source.as_uri()}.insteadOf",
                        GIT_CONFIG_VALUE_0=sync_ais_max.SOURCE_REPO)

    def run_main(self, *args):
        return subprocess.run([sys.executable, str(self.work / "scripts" / "sync-ais-max.py"), *args],
                              cwd=self.work, env=self.env, capture_output=True, text=True)

    def test_success_exits_zero(self):
        """A good tag exits 0."""
        self.assertEqual(self.run_main("v1.0.0").returncode, 0)

    def test_success_prints_the_count(self):
        """A good tag prints how many skills it wrote, in one line."""
        self.assertEqual(self.run_main("v1.0.0").stdout, "Wrote 3 skills to ais-max from v1.0.0\n")

    def test_success_writes_ais_max_beside_ais(self):
        """main writes the ais-max folder at the project root."""
        self.run_main("v1.0.0")
        self.assertTrue((self.work / "ais-max" / "helper-skill").is_dir())

    def test_stop_exits_one(self):
        """A failed check exits 1."""
        self.assertEqual(self.run_main("v9.2.0").returncode, 1)

    def test_stop_prints_one_error_line(self):
        """A failed check prints error: and the message on stderr, with no traceback."""
        self.assertEqual(self.run_main("v9.2.0").stderr, f"error: {HELPER_MISSING}\n")

    def test_stop_leaves_ais_max_untouched(self):
        """A failed check leaves ais-max as it was."""
        self.dest = self.work / "ais-max"
        self.seed_dest()
        before = snapshot(self.dest)
        self.run_main("v9.1.0")
        self.assertEqual(snapshot(self.dest), before)

    def test_no_tag_exits_two(self):
        """Running with no tag is a usage error."""
        self.assertEqual(self.run_main().returncode, 2)

    def test_two_tags_exit_two(self):
        """Running with more than one tag is a usage error."""
        self.assertEqual(self.run_main("v1.0.0", "v1.1.0").returncode, 2)


class TestCommittedAisMax(unittest.TestCase):
    """The ais-max/ committed in this repo, from the first run against v2.1.0 onwards."""

    def read_record(self):
        path = ROOT / "ais-max" / sync_ais_max.RECORD
        if not path.is_file():
            self.fail(f"{path.relative_to(ROOT)} is missing; run the sync and commit it")
        return json.loads(path.read_text())

    def test_record_names_a_release_tag(self):
        """The committed record's tag has the vX.Y.Z form."""
        self.assertRegex(self.read_record().get("tag", ""), r"^v\d+\.\d+\.\d+$")

    def test_record_names_a_full_commit(self):
        """The committed record's commit is a 40-character sha."""
        self.assertRegex(self.read_record().get("commit", ""), r"^[0-9a-f]{40}$")

    def test_holds_no_ais_skill(self):
        """No folder in the committed ais-max shares a name with an ais skill (ADR-0002)."""
        self.read_record()
        ais = {p.name for p in (ROOT / "ais").iterdir() if p.is_dir()}
        ais_max = {p.name for p in (ROOT / "ais-max").iterdir() if p.is_dir()}
        self.assertEqual(ais & ais_max, set())

    def test_helper_skill_matches_ais(self):
        """Each base file in the committed helper-skill matches its ais original (ADR-0003)."""
        self.read_record()
        for file, skill in sync_ais_max.BASE_FILES.items():
            with self.subTest(file=file):
                self.assertEqual((ROOT / "ais-max" / "helper-skill" / file).read_bytes(),
                                 (ROOT / "ais" / skill / file).read_bytes())

    def test_holds_no_hidden_file_but_the_record(self):
        """The only dot-named entry anywhere in the committed ais-max is the record."""
        self.read_record()
        hidden = [str(p.relative_to(ROOT / "ais-max")) for p in (ROOT / "ais-max").rglob(".*")]
        self.assertEqual(hidden, [sync_ais_max.RECORD])


if __name__ == "__main__":
    unittest.main()
