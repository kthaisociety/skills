"""Tests for install.sh, which copies the ais and ais-max skills from a clone into an agent's skills folder.

The tests copy install.sh and scripts/build-codex.py into a fake clone in a
temp folder, beside fake ais/ and ais-max/ folders, and run it with HOME
pointed at a temp home. Terminal runs go through a pseudo-terminal.
"""

import os
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL = ROOT / "install.sh"
BUILD_CODEX = ROOT / "scripts" / "build-codex.py"

POLICY = b"policy:\n  allow_implicit_invocation: false\n"
MARKER = ".ais-install"
TIMEOUT = 60


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def skill_md(name, extra="", body=""):
    return f"---\nname: {name}\ndescription: The {name} skill.\n{extra}---\n\n{body}"


def build_sources(work):
    """Write fake ais/ and ais-max/ under work. Returns (ais, ais_max)."""
    ais = work / "ais"
    ais_max = work / "ais-max"
    write(ais / "new-ticket" / "SKILL.md", skill_md(
        "new-ticket", extra="disable-model-invocation: true\n",
        body="Run /grill-docs first. Read ../grill-docs/FORMAT.md.\n"))
    write(ais / "grill-docs" / "SKILL.md", skill_md("grill-docs", body="Grill the user.\n"))
    write(ais / "grill-docs" / "FORMAT.md", "Then hand back to /new-ticket.\n")
    write(ais / "grill-docs" / "LICENSE", b"\x00\x01binary licence\xff")
    write(ais_max / "architect-ticket" / "SKILL.md", skill_md(
        "architect-ticket", extra="model: opus\n",
        body="Point at /new-ticket. Leave /not-a-skill alone. Read ../helper-skill/shapes.md.\n"))
    write(ais_max / "helper-skill" / "SKILL.md", skill_md("helper-skill"))
    write(ais_max / "helper-skill" / "shapes.md", "Shapes for /architect-ticket.\n")
    write(ais_max / "helper-skill" / ".hidden", "hidden file\n")
    write(ais_max / "helper-skill" / ".hidden-dir" / "inside.md", "hidden folder\n")
    write(ais_max / ".source.json", '{"commit": "abc", "tag": "v2.1.0"}\n')
    write(ais_max / ".hidden-skill" / "SKILL.md", skill_md(".hidden-skill"))
    return ais, ais_max


def snapshot(folder):
    """Every file and folder under folder, hidden ones included, with file bytes."""
    if not folder.exists():
        return None
    return {str(p.relative_to(folder)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(folder.rglob("*"))}


def visible_files(folder):
    """Every non-hidden file under folder, relative, with its bytes."""
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*"))
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(folder).parts)}


class InstallCase(unittest.TestCase):
    """A fake clone holding install.sh, the Codex build and fake plugins, plus a fake home."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp()).resolve()
        self.clone = self.work / "clone"
        self.home = self.work / "home"
        self.home.mkdir()
        write(self.clone / "install.sh", INSTALL.read_bytes())
        (self.clone / "install.sh").chmod(0o755)
        write(self.clone / "scripts" / "build-codex.py", BUILD_CODEX.read_bytes())
        self.ais, self.ais_max = build_sources(self.clone)
        self.claude = self.home / ".claude" / "skills"
        self.agy = self.home / ".gemini" / "config" / "skills"
        self.codex = self.home / ".agents" / "skills"
        self.path = os.environ.get("PATH", "")

    def tearDown(self):
        shutil.rmtree(self.work)

    def env(self):
        env = {k: v for k, v in os.environ.items() if k not in ("HOME", "PATH")}
        env["HOME"] = str(self.home)
        env["PATH"] = self.path
        return env

    def run_install(self, *args):
        """Run install.sh without a terminal. Returns the CompletedProcess."""
        return subprocess.run(
            [str(self.clone / "install.sh"), *args], cwd=self.work, env=self.env(),
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT)

    def run_tty(self, *args, answers=""):
        """Run install.sh on a pseudo-terminal, typing answers. Returns (exit code, output)."""
        master, slave = pty.openpty()
        proc = subprocess.Popen(
            [str(self.clone / "install.sh"), *args], cwd=self.work, env=self.env(),
            stdin=slave, stdout=slave, stderr=slave, close_fds=True)
        os.close(slave)
        if answers:
            os.write(master, answers.encode())
        out = b""
        deadline = time.monotonic() + TIMEOUT
        while True:
            if time.monotonic() > deadline:
                proc.kill()
                proc.wait()
                os.close(master)
                self.fail(f"install.sh did not finish on a terminal; output so far:\n{out.decode(errors='replace')}")
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
            elif proc.poll() is not None:
                break
        proc.wait()
        os.close(master)
        return proc.returncode, out.decode(errors="replace").replace("\r\n", "\n")

    def install(self, agent="claude", plugin="ais"):
        """Install with --yes and assert it succeeded. Returns the CompletedProcess."""
        result = self.run_install("--yes", agent, plugin)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def skills_in(self, folder):
        return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []

    def no_python_path(self):
        """A PATH holding every command on the real PATH except python."""
        farm = self.work / "no-python-bin"
        farm.mkdir()
        for entry in self.path.split(os.pathsep):
            folder = Path(entry)
            if not folder.is_dir():
                continue
            for tool in folder.iterdir():
                if tool.name.startswith("python") or (farm / tool.name).exists():
                    continue
                if tool.is_file() and os.access(tool, os.X_OK):
                    (farm / tool.name).symlink_to(tool)
        return str(farm)

    def failing_python_path(self):
        """The real PATH with a python3 in front that always fails."""
        fake = self.work / "fake-python-bin"
        write(fake / "python3", "#!/bin/sh\necho 'fake python3 failed' >&2\nexit 1\n")
        (fake / "python3").chmod(0o755)
        return f"{fake}{os.pathsep}{self.path}"


class TestInstallCopies(InstallCase):

    def test_copies_every_ais_skill_into_the_claude_folder(self):
        """Choosing ais copies every ais skill into ~/.claude/skills."""
        self.install("claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-docs", "new-ticket"])

    def test_copies_every_ais_skill_into_the_antigravity_folder(self):
        """The agy agent's skills folder is ~/.gemini/config/skills."""
        self.install("agy", "ais")
        self.assertEqual(self.skills_in(self.agy), ["grill-docs", "new-ticket"])

    def test_a_copy_holds_the_source_skill_files(self):
        """A copy holds every visible file of its source skill, byte for byte."""
        self.install("claude", "ais")
        self.assertEqual(visible_files(self.claude / "grill-docs"), visible_files(self.ais / "grill-docs"))

    def test_a_copy_is_not_a_symlink(self):
        """The skill folder is a real copy, never a symlink into the clone."""
        self.install("claude", "ais")
        self.assertFalse((self.claude / "new-ticket").is_symlink())

    def test_a_copy_has_no_symlinked_files(self):
        """No file in a copy links back into the clone."""
        self.install("claude", "ais")
        self.assertEqual([p for p in (self.claude / "grill-docs").rglob("*") if p.is_symlink()], [])

    def test_ais_leaves_out_ais_max_skills(self):
        """Choosing ais copies no ais-max skill."""
        self.install("claude", "ais")
        self.assertFalse((self.claude / "architect-ticket").exists())

    def test_ais_max_copies_its_own_skills(self):
        """Choosing ais-max copies every ais-max skill."""
        self.install("claude", "ais-max")
        self.assertTrue({"architect-ticket", "helper-skill"} <= set(self.skills_in(self.claude)))

    def test_ais_max_copies_ais_as_well(self):
        """Choosing ais-max copies every ais skill too."""
        self.install("claude", "ais-max")
        self.assertEqual(self.skills_in(self.claude),
                         ["architect-ticket", "grill-docs", "helper-skill", "new-ticket"])

    def test_yes_may_come_after_the_arguments(self):
        """--yes works after AGENT and PLUGIN."""
        result = self.run_install("claude", "ais", "--yes")
        self.assertEqual((result.returncode, self.skills_in(self.claude)), (0, ["grill-docs", "new-ticket"]))

    def test_writes_nothing_outside_the_agent_folder(self):
        """A claude install leaves the other agents' folders alone."""
        self.install("claude", "ais")
        self.assertEqual(self.skills_in(self.home), [".claude"])

    def test_leaves_the_clone_untouched(self):
        """Installing reads the plugin folders and never writes them."""
        before = (snapshot(self.ais), snapshot(self.ais_max))
        self.install("claude", "ais-max")
        self.assertEqual((snapshot(self.ais), snapshot(self.ais_max)), before)


class TestInstallHiddenFiles(InstallCase):

    def test_skips_hidden_files_in_a_skill(self):
        """Hidden files in a skill folder are never copied."""
        self.install("claude", "ais-max")
        self.assertFalse((self.claude / "helper-skill" / ".hidden").exists())

    def test_skips_hidden_folders_in_a_skill(self):
        """Hidden folders in a skill folder are never copied."""
        self.install("claude", "ais-max")
        self.assertFalse((self.claude / "helper-skill" / ".hidden-dir").exists())

    def test_skips_hidden_skill_folders(self):
        """A plugin folder whose name starts with "." is not a skill."""
        self.install("claude", "ais-max")
        self.assertFalse((self.claude / ".hidden-skill").exists())

    def test_sync_record_is_never_copied(self):
        """Ais-max/.source.json never reaches the agent folder."""
        self.install("claude", "ais-max")
        self.assertEqual(list(self.claude.rglob(".source.json")), [])


class TestInstallRefresh(InstallCase):

    def test_rerun_copies_a_source_edit(self):
        """A rerun replaces an earlier copy with the current source."""
        self.install("claude", "ais")
        write(self.ais / "grill-docs" / "FORMAT.md", "Edited in the clone.\n")
        self.install("claude", "ais")
        self.assertEqual((self.claude / "grill-docs" / "FORMAT.md").read_text(), "Edited in the clone.\n")

    def test_replaced_copy_keeps_nothing_from_the_earlier_one(self):
        """A file deleted from the source is gone from the copy after a rerun."""
        self.install("claude", "ais")
        (self.ais / "grill-docs" / "FORMAT.md").unlink()
        self.install("claude", "ais")
        self.assertFalse((self.claude / "grill-docs" / "FORMAT.md").exists())

    def test_rerun_overwrites_an_edit_made_in_the_copy(self):
        """Editing an installed copy in place does not survive a rerun."""
        self.install("claude", "ais")
        write(self.claude / "grill-docs" / "SKILL.md", "edited in place\n")
        self.install("claude", "ais")
        self.assertEqual((self.claude / "grill-docs" / "SKILL.md").read_bytes(),
                         (self.ais / "grill-docs" / "SKILL.md").read_bytes())

    def test_replaces_a_copy_another_clone_wrote(self):
        """Any folder holding .ais-install is ours, whichever clone wrote it."""
        write(self.claude / "grill-docs" / MARKER, "")
        write(self.claude / "grill-docs" / "SKILL.md", "from another clone\n")
        self.install("claude", "ais")
        self.assertEqual((self.claude / "grill-docs" / "SKILL.md").read_bytes(),
                         (self.ais / "grill-docs" / "SKILL.md").read_bytes())

    def test_removes_the_copy_of_a_deleted_skill(self):
        """A copy whose skill left the clone is removed on the next run."""
        self.install("claude", "ais")
        shutil.rmtree(self.ais / "grill-docs")
        self.install("claude", "ais")
        self.assertFalse((self.claude / "grill-docs").exists())

    def test_removes_the_copy_of_a_renamed_skill(self):
        """A rename leaves only the new name's copy."""
        self.install("claude", "ais")
        (self.ais / "grill-docs").rename(self.ais / "grill-plan")
        write(self.ais / "grill-plan" / "SKILL.md", skill_md("grill-plan"))
        self.install("claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-plan", "new-ticket"])

    def test_prunes_a_dead_copy_from_the_plugin_not_chosen(self):
        """An ais run removes a dead ais-max copy too."""
        self.install("claude", "ais-max")
        shutil.rmtree(self.ais_max / "helper-skill")
        self.install("claude", "ais")
        self.assertFalse((self.claude / "helper-skill").exists())

    def test_keeps_copies_from_the_plugin_not_chosen(self):
        """An ais run keeps ais-max copies whose skills still exist."""
        self.install("claude", "ais-max")
        self.install("claude", "ais")
        self.assertTrue((self.claude / "architect-ticket" / "SKILL.md").is_file())

    def test_keeps_a_folder_it_did_not_write(self):
        """A folder without .ais-install is never removed, even under a dead name."""
        write(self.claude / "my-own-skill" / "SKILL.md", skill_md("my-own-skill"))
        self.install("claude", "ais")
        self.assertTrue((self.claude / "my-own-skill" / "SKILL.md").is_file())


class TestInstallForeignFolders(InstallCase):

    def seed_foreign(self):
        write(self.claude / "grill-docs" / "SKILL.md", "my own grill-docs\n")

    def test_leaves_a_foreign_folder_in_the_way_untouched(self):
        """A folder it didn't write, under a skill's name, keeps its contents."""
        self.seed_foreign()
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(((self.claude / "grill-docs" / "SKILL.md").read_text(), (self.claude / "new-ticket").is_dir()),
                         ("my own grill-docs\n", True))

    def test_warns_about_a_foreign_folder_in_the_way(self):
        """The skipped folder is named in a warning on stderr."""
        self.seed_foreign()
        result = self.run_install("--yes", "claude", "ais")
        self.assertIn(f"warning: {self.claude / 'grill-docs'} is not from install.sh, skipping", result.stderr)

    def test_still_copies_the_other_skills(self):
        """One foreign folder doesn't stop the other skills."""
        self.seed_foreign()
        self.run_install("--yes", "claude", "ais")
        self.assertTrue((self.claude / "new-ticket" / "SKILL.md").is_file())

    def test_exits_1_after_skipping_a_foreign_folder(self):
        """Skipping a folder fails the run, after copying the rest."""
        self.seed_foreign()
        result = self.run_install("--yes", "claude", "ais")
        self.assertEqual((result.returncode, (self.claude / "new-ticket").is_dir()), (1, True))

    def test_a_foreign_file_in_the_way_is_left_alone(self):
        """A plain file under a skill's name is skipped, not replaced."""
        write(self.claude / "grill-docs", "a file, not a folder\n")
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(((self.claude / "grill-docs").read_text(), (self.claude / "new-ticket").is_dir()),
                         ("a file, not a folder\n", True))

    def test_a_foreign_symlink_in_the_way_is_left_alone(self):
        """A symlink under a skill's name, such as one the Custom-skills installer left, stays."""
        elsewhere = self.work / "elsewhere"
        write(elsewhere / "SKILL.md", "elsewhere\n")
        self.claude.mkdir(parents=True)
        (self.claude / "grill-docs").symlink_to(elsewhere)
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(((self.claude / "grill-docs").is_symlink(), (elsewhere / "SKILL.md").read_text(),
                          (self.claude / "new-ticket").is_dir()), (True, "elsewhere\n", True))


class TestInstallInvalidSkills(InstallCase):

    def test_skips_a_skill_with_no_skill_md(self):
        """A skill folder without SKILL.md is not copied."""
        write(self.ais / "broken" / "notes.md", "no SKILL.md here\n")
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-docs", "new-ticket"])

    def test_skips_a_skill_with_no_name(self):
        """A skill whose frontmatter lacks a name is not copied."""
        write(self.ais / "broken" / "SKILL.md", "---\ndescription: No name.\n---\n")
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-docs", "new-ticket"])

    def test_skips_a_skill_with_no_description(self):
        """A skill whose frontmatter lacks a description is not copied."""
        write(self.ais / "broken" / "SKILL.md", "---\nname: broken\n---\n")
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-docs", "new-ticket"])

    def test_skips_a_skill_whose_name_differs_from_its_folder(self):
        """A frontmatter name that isn't the folder name keeps the skill out."""
        write(self.ais / "broken" / "SKILL.md", skill_md("other-name"))
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-docs", "new-ticket"])

    def test_reports_an_invalid_skill(self):
        """The invalid skill is reported on stderr as error: <plugin>/<skill>."""
        write(self.ais / "broken" / "SKILL.md", skill_md("other-name"))
        result = self.run_install("--yes", "claude", "ais")
        self.assertIn("error: ais/broken:", result.stderr)

    def test_still_copies_the_valid_skills(self):
        """An invalid skill doesn't stop the valid ones."""
        write(self.ais / "broken" / "SKILL.md", skill_md("other-name"))
        self.run_install("--yes", "claude", "ais")
        self.assertEqual(self.skills_in(self.claude), ["grill-docs", "new-ticket"])

    def test_exits_1_after_an_invalid_skill(self):
        """An invalid skill fails the run, after copying the valid ones."""
        write(self.ais / "broken" / "SKILL.md", skill_md("other-name"))
        result = self.run_install("--yes", "claude", "ais")
        self.assertEqual((result.returncode, (self.claude / "new-ticket").is_dir()), (1, True))

    def test_keeps_an_earlier_copy_of_a_skill_now_invalid(self):
        """A skill still in the clone isn't pruned just because it is now invalid."""
        self.install("claude", "ais")
        write(self.ais / "grill-docs" / "SKILL.md", "---\nname: grill-docs\n---\n")
        self.run_install("--yes", "claude", "ais")
        self.assertTrue((self.claude / "grill-docs").is_dir())


class TestInstallPlan(InstallCase):

    def test_plan_marks_a_new_skill_with_plus(self):
        """A skill with no folder yet is planned as "  + <skill>"."""
        result = self.install("claude", "ais")
        self.assertIn("  + grill-docs\n", result.stdout)

    def test_plan_marks_an_earlier_copy_with_tilde(self):
        """A copy that will be replaced is planned as "  ~ <skill>"."""
        self.install("claude", "ais")
        result = self.install("claude", "ais")
        self.assertIn("  ~ grill-docs\n", result.stdout)

    def test_plan_marks_a_dead_copy_with_minus(self):
        """A copy that will be removed is planned as "  - <skill>"."""
        self.install("claude", "ais")
        shutil.rmtree(self.ais / "grill-docs")
        result = self.install("claude", "ais")
        self.assertIn("  - grill-docs\n", result.stdout)

    def test_plan_lists_adds_then_updates_then_removals(self):
        """The plan groups adds, then updates, then removals."""
        self.install("claude", "ais")
        shutil.rmtree(self.ais / "grill-docs")
        write(self.ais / "a-new-skill" / "SKILL.md", skill_md("a-new-skill"))
        lines = [l for l in self.install("claude", "ais").stdout.splitlines() if l[:4] in ("  + ", "  ~ ", "  - ")]
        self.assertEqual(lines, ["  + a-new-skill", "  ~ new-ticket", "  - grill-docs"])

    def test_plan_sorts_each_group_by_name(self):
        """Skills within one group come in name order."""
        lines = [l for l in self.install("claude", "ais-max").stdout.splitlines() if l.startswith("  + ")]
        self.assertEqual(lines, ["  + architect-ticket", "  + grill-docs", "  + helper-skill", "  + new-ticket"])

    def test_empty_plan_says_nothing_to_change(self):
        """With nothing to add, update or remove it says so."""
        self.claude.mkdir(parents=True)
        shutil.rmtree(self.ais)
        self.ais.mkdir()
        result = self.run_install("claude", "ais")
        self.assertEqual((result.returncode, "Nothing to change" in result.stdout), (0, True))

    def test_prints_added_with_the_full_path(self):
        """Each new folder is reported as "added <path>"."""
        result = self.install("claude", "ais")
        self.assertIn(f"added {self.claude / 'grill-docs'}\n", result.stdout)

    def test_prints_updated_with_the_full_path(self):
        """Each replaced folder is reported as "updated <path>"."""
        self.install("claude", "ais")
        result = self.install("claude", "ais")
        self.assertIn(f"updated {self.claude / 'grill-docs'}\n", result.stdout)

    def test_prints_removed_with_the_full_path(self):
        """Each removed folder is reported as "removed <path>"."""
        self.install("claude", "ais")
        shutil.rmtree(self.ais / "grill-docs")
        result = self.install("claude", "ais")
        self.assertIn(f"removed {self.claude / 'grill-docs'}\n", result.stdout)


class TestInstallWithoutTerminal(InstallCase):

    def test_without_yes_prints_the_plan(self):
        """Without a terminal or --yes it still prints the plan."""
        result = self.run_install("claude", "ais")
        self.assertIn("  + new-ticket\n", result.stdout)

    def test_without_yes_writes_nothing(self):
        """Without a terminal or --yes it writes nothing, after printing the plan."""
        result = self.run_install("claude", "ais")
        self.assertEqual(("  + new-ticket" in result.stdout, self.claude.exists()), (True, False))

    def test_without_yes_exits_1(self):
        """Without a terminal or --yes it exits 1, after printing the plan."""
        result = self.run_install("claude", "ais")
        self.assertEqual(("  + new-ticket" in result.stdout, result.returncode), (True, 1))

    def test_missing_both_arguments_prints_usage(self):
        """Without a terminal and with no arguments it prints its usage on stderr."""
        result = self.run_install()
        self.assertIn("Usage: ./install.sh", result.stderr)

    def test_missing_the_plugin_prints_usage(self):
        """Without a terminal and with no PLUGIN it prints its usage on stderr."""
        result = self.run_install("--yes", "claude")
        self.assertIn("Usage: ./install.sh", result.stderr)

    def test_missing_arguments_exits_1_and_writes_nothing(self):
        """A usage stop writes nothing and exits 1."""
        result = self.run_install("--yes", "claude")
        self.assertEqual(("Usage" in result.stderr, result.returncode, self.claude.exists()), (True, 1, False))


class TestInstallArguments(InstallCase):

    def test_help_prints_usage_and_exits_0(self):
        """--help prints the usage to stdout and exits 0."""
        result = self.run_install("--help")
        self.assertEqual((result.returncode, "Usage: ./install.sh" in result.stdout), (0, True))

    def test_rejects_an_unknown_agent(self):
        """An unknown AGENT is named in an error and exits 1."""
        result = self.run_install("--yes", "cursor", "ais")
        self.assertEqual((result.returncode, "error:" in result.stderr and "cursor" in result.stderr), (1, True))

    def test_rejects_an_unknown_plugin(self):
        """An unknown PLUGIN is named in an error and exits 1."""
        result = self.run_install("--yes", "claude", "max")
        self.assertEqual((result.returncode, "error:" in result.stderr and "max" in result.stderr), (1, True))

    def test_rejects_an_unknown_flag(self):
        """An unknown flag is named in an error and exits 1."""
        result = self.run_install("--yes", "--force", "claude", "ais")
        self.assertEqual((result.returncode, "error:" in result.stderr and "--force" in result.stderr), (1, True))

    def test_an_unknown_argument_writes_nothing(self):
        """An unknown argument stops the run before any write."""
        result = self.run_install("--yes", "claude", "max")
        self.assertEqual(("error:" in result.stderr, self.home.exists() and self.skills_in(self.home)), (True, []))


class TestInstallOnTerminal(InstallCase):

    def test_asks_for_the_agent_then_the_plugin(self):
        """With no arguments on a terminal it asks for both, then copies."""
        code, out = self.run_tty(answers="claude\nais\ny\n")
        self.assertEqual((code, self.skills_in(self.claude)), (0, ["grill-docs", "new-ticket"]), out)

    def test_accepts_numbers_from_the_lists(self):
        """Each prompt takes the number of a listed choice."""
        code, out = self.run_tty(answers="3\n1\ny\n")
        self.assertEqual((code, self.skills_in(self.codex)), (0, ["grill-docs", "new-ticket"]), out)

    def test_asks_again_after_an_unknown_answer(self):
        """An answer that names no agent gets the question again."""
        code, out = self.run_tty(answers="cursor\nagy\nais\ny\n")
        self.assertEqual((code, self.skills_in(self.agy)), (0, ["grill-docs", "new-ticket"]), out)

    def test_asks_only_for_the_missing_plugin(self):
        """Given the agent, it asks only for the plugin."""
        code, out = self.run_tty("claude", answers="ais-max\ny\n")
        self.assertEqual((code, len(self.skills_in(self.claude))), (0, 4), out)

    def test_asks_to_apply(self):
        """On a terminal it asks "Apply? [y/N] " before writing."""
        code, out = self.run_tty("claude", "ais", answers="n\n")
        self.assertIn("Apply? [y/N]", out)

    def test_declining_writes_nothing(self):
        """Answering no leaves the agent folder as it was."""
        code, out = self.run_tty("claude", "ais", answers="n\n")
        self.assertEqual(("Nothing written" in out, self.claude.exists()), (True, False), out)

    def test_declining_exits_0(self):
        """A declined plan is not a failure."""
        code, out = self.run_tty("claude", "ais", answers="n\n")
        self.assertEqual((code, "Nothing written" in out), (0, True), out)

    def test_an_empty_answer_declines(self):
        """Enter alone takes the N default."""
        code, out = self.run_tty("claude", "ais", answers="\n")
        self.assertEqual(("Nothing written" in out, self.claude.exists()), (True, False), out)

    def test_yes_skips_the_question(self):
        """--yes applies on a terminal without asking."""
        code, out = self.run_tty("--yes", "claude", "ais")
        self.assertEqual((code, "Apply?" in out, self.skills_in(self.claude)),
                         (0, False, ["grill-docs", "new-ticket"]), out)


class TestInstallCodex(InstallCase):

    def test_copies_every_skill_into_the_codex_folder(self):
        """The codex agent's skills folder is ~/.agents/skills."""
        self.install("codex", "ais-max")
        self.assertEqual(self.skills_in(self.codex),
                         ["architect-ticket", "grill-docs", "helper-skill", "new-ticket"])

    def test_copies_converted_mentions(self):
        """Codex copies carry bare $<skill> mentions from the local build."""
        self.install("codex", "ais-max")
        self.assertIn("Point at $new-ticket.", (self.codex / "architect-ticket" / "SKILL.md").read_text())

    def test_copies_converted_frontmatter(self):
        """Codex copies keep only name and description in the frontmatter."""
        self.install("codex", "ais-max")
        self.assertNotIn("model: opus", (self.codex / "architect-ticket" / "SKILL.md").read_text())

    def test_copies_the_invocation_policy(self):
        """A skill that disables model invocation gets agents/openai.yaml."""
        self.install("codex", "ais")
        self.assertEqual((self.codex / "new-ticket" / "agents" / "openai.yaml").read_bytes(), POLICY)

    def test_claude_copies_stay_unconverted(self):
        """Only Codex copies are converted; Claude gets the source as written."""
        self.install("claude", "ais-max")
        self.assertIn("Point at /new-ticket.", (self.claude / "architect-ticket" / "SKILL.md").read_text())

    def test_a_failed_build_writes_nothing(self):
        """When the local build fails, nothing reaches the Codex folder."""
        self.install("claude", "ais")
        self.path = self.failing_python_path()
        result = self.run_install("--yes", "codex", "ais")
        self.assertEqual((result.returncode, self.codex.exists()), (1, False))

    def test_missing_python3_writes_nothing(self):
        """Without python3 it says why on stderr and writes nothing."""
        self.path = self.no_python_path()
        result = self.run_install("--yes", "codex", "ais")
        self.assertEqual((result.returncode, self.codex.exists(), "python3" in result.stderr), (1, False, True))

    def test_claude_needs_no_python3(self):
        """Only codex runs the build, so claude installs without python3."""
        self.path = self.no_python_path()
        result = self.run_install("--yes", "claude", "ais")
        self.assertEqual((result.returncode, self.skills_in(self.claude)), (0, ["grill-docs", "new-ticket"]))


if __name__ == "__main__":
    unittest.main()
