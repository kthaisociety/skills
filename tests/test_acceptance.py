"""Acceptance tests for #8: scripts/build-agy.py builds and checks the ais-agy tree.

Every test runs in a temp folder against fake ais and ais-max folders and a
fake `agy` command, except TestRealTree, which builds from this repo's own
ais/ and ais-max/ and runs the real agy.
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
SCRIPT = ROOT / "scripts" / "build-agy.py"
spec = importlib.util.spec_from_file_location("build_agy", SCRIPT)
build_agy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_agy)

build_tree = build_agy.build_tree
check_tree = build_agy.check_tree
BuildError = build_agy.BuildError

VERSION = "1.6.0"
PLUGINS = ("ais", "ais-max")
AIS_SKILLS = ("grill-docs", "new-ticket")
MAX_SKILLS = ("architect-ticket", "unslop")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def skill_md(name, description="Does a thing."):
    lines = ["---"]
    if name is not None:
        lines.append(f"name: {name}")
    if description is not None:
        lines.append(f"description: {description}")
    lines += ["---", "", f"# {name}", ""]
    return "\n".join(lines).encode()


def dump(obj):
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode()


def snapshot(folder):
    """Every file and folder under folder, hidden ones included, with file bytes."""
    if not folder.exists():
        return None
    return {str(p.relative_to(folder)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(folder.rglob("*"))}


def build_sources(ais, ais_max):
    """Fake ais and ais-max folders, with nested, hidden and loose files to test copying."""
    for name in AIS_SKILLS:
        write(ais / name / "SKILL.md", skill_md(name))
    write(ais / "grill-docs" / "RECORD-FORMAT.md", b"record format\n")
    write(ais / "grill-docs" / "deep" / "nested.md", b"nested\n")
    write(ais / "grill-docs" / ".hidden", b"hidden file\n")
    write(ais / "grill-docs" / ".hidden-dir" / "inside.md", b"hidden dir\n")
    write(ais / "grill-docs" / "deep" / ".also-hidden", b"deep hidden\n")
    write(ais / "loose.md", b"not a skill\n")
    for name in MAX_SKILLS:
        write(ais_max / name / "SKILL.md", skill_md(name))
    write(ais_max / "unslop" / "LICENSE", b"license \xc3\xa5\n")
    write(ais_max / ".source.json", b'{"tag": "v2.1.0"}\n')


def write_tree(tree, version=VERSION, ais_skills=AIS_SKILLS, max_skills=MAX_SKILLS):
    """A tree laid out as build_tree promises, written by hand so check tests don't lean on build."""
    for plugin, skills in (("ais", ais_skills), ("ais-max", max_skills)):
        write(tree / plugin / "plugin.json", dump({
            "name": plugin, "version": version,
            "displayName": f"Display {plugin}", "description": "A plugin.",
        }))
        for name in skills:
            write(tree / plugin / "skills" / name / "SKILL.md", skill_md(name))


def edit_json(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_bytes(dump(data))


def fake_agy(folder, results=None):
    """An executable `agy` in folder that logs its arguments and answers per plugin folder.

    results maps a plugin folder name, the last part of the path it is
    given, to (exit code, stdout, stderr). A folder not in results gets
    (0, a passing report, "").
    """
    calls = folder / "agy-calls.jsonl"
    answers = folder / "agy-answers.json"
    answers.write_text(json.dumps(results or {}))
    script = folder / "agy"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        f"with open({str(calls)!r}, 'a') as log:\n"
        "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"answers = json.load(open({str(answers)!r}))\n"
        "name = os.path.basename(sys.argv[-1].rstrip('/'))\n"
        "default = [0, json.dumps({'name': name, 'findings': []}), '']\n"
        "code, out, err = answers.get(name, default)\n"
        "sys.stdout.write(out)\n"
        "sys.stderr.write(err)\n"
        "sys.exit(code)\n")
    script.chmod(0o755)
    return script, calls


def starts(messages, prefixes):
    """True when there is one message per prefix, each starting with its prefix, in order."""
    return len(messages) == len(prefixes) and all(m.startswith(p) for m, p in zip(messages, prefixes))


def calls_made(calls):
    if not calls.exists():
        return []
    return [json.loads(line) for line in calls.read_text().splitlines()]


def report(name, findings):
    """A JSON report shaped like `agy plugin validate --json` prints.

    findings is a list of (severity, file, message).
    """
    return json.dumps({
        "dir": f"/somewhere/{name}", "manifest": "plugin.json", "name": name,
        "components": {"skills": 2},
        "findings": [{"severity": s, "file": f, "message": m} for s, f, m in findings],
    }, indent=2)


class Case(unittest.TestCase):

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.ais = self.work / "ais"
        self.ais_max = self.work / "ais-max"
        self.dest = self.work / ".agy-build"
        self.bin = self.work / "bin"
        self.bin.mkdir()
        build_sources(self.ais, self.ais_max)

    def build(self, version=VERSION):
        return build_tree(version, ais=self.ais, ais_max=self.ais_max, dest=self.dest)

    def seed_dest(self):
        write(self.dest / "stale" / "old.md", b"from an earlier build\n")


# Build


class TestBuildWrites(Case):

    def test_returns_skill_names_per_plugin(self):
        """build_tree returns each plugin's skill folder names, sorted."""
        self.assertEqual(self.build(), {"ais": sorted(AIS_SKILLS), "ais-max": sorted(MAX_SKILLS)})

    def test_writes_each_plugin_manifest(self):
        """Each plugin.json holds name, version, displayName and description, in order, and nothing else."""
        self.build()
        for name in PLUGINS:
            with self.subTest(plugin=name):
                expected = dump({"name": name, "version": VERSION,
                                 "displayName": build_agy.DISPLAY_NAMES[name],
                                 "description": build_agy.DESCRIPTIONS[name]})
                self.assertEqual((self.dest / name / "plugin.json").read_bytes(), expected)

    def test_both_manifests_carry_the_given_version(self):
        """Both plugin.json files carry the version build_tree was given."""
        self.build("3.10.27")
        versions = [json.loads((self.dest / n / "plugin.json").read_text())["version"] for n in PLUGINS]
        self.assertEqual(versions, ["3.10.27", "3.10.27"])

    def test_ais_max_description_says_to_install_ais_first(self):
        """The ais-max manifest tells the reader to install ais first."""
        self.build()
        manifest = json.loads((self.dest / "ais-max" / "plugin.json").read_text())
        self.assertIn("install ais first", manifest["description"].lower())

    def test_tree_root_holds_only_the_plugin_folders(self):
        """The tree root holds the ais and ais-max folders and nothing else, so no root plugin.json."""
        self.build()
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), sorted(PLUGINS))

    def test_ais_skills_go_to_the_ais_plugin(self):
        """Each ais skill lands at ais/skills/<name>/ with its SKILL.md byte for byte."""
        self.build()
        for name in AIS_SKILLS:
            with self.subTest(skill=name):
                self.assertEqual((self.dest / "ais" / "skills" / name / "SKILL.md").read_bytes(),
                                 (self.ais / name / "SKILL.md").read_bytes())

    def test_ais_max_skills_go_to_the_ais_max_plugin(self):
        """Each ais-max skill lands at ais-max/skills/<name>/ with its SKILL.md byte for byte."""
        self.build()
        for name in MAX_SKILLS:
            with self.subTest(skill=name):
                self.assertEqual((self.dest / "ais-max" / "skills" / name / "SKILL.md").read_bytes(),
                                 (self.ais_max / name / "SKILL.md").read_bytes())

    def test_skills_folder_holds_only_skills(self):
        """Each plugin's skills folder holds exactly its skill folders."""
        self.build()
        for name, skills in (("ais", AIS_SKILLS), ("ais-max", MAX_SKILLS)):
            with self.subTest(plugin=name):
                self.assertEqual(sorted(p.name for p in (self.dest / name / "skills").iterdir()),
                                 sorted(skills))

    def test_nested_files_are_copied(self):
        """Files in folders below a skill are copied byte for byte."""
        self.build()
        self.assertEqual((self.dest / "ais" / "skills" / "grill-docs" / "deep" / "nested.md").read_bytes(),
                         b"nested\n")

    def test_supporting_files_are_copied(self):
        """Files beside SKILL.md are copied byte for byte."""
        self.build()
        self.assertEqual(
            (self.dest / "ais" / "skills" / "grill-docs" / "RECORD-FORMAT.md").read_bytes(),
            b"record format\n")

    def test_non_ascii_bytes_are_kept(self):
        """A file holding non-ASCII bytes is copied unchanged."""
        self.build()
        self.assertEqual((self.dest / "ais-max" / "skills" / "unslop" / "LICENSE").read_bytes(),
                         b"license \xc3\xa5\n")

    def test_hidden_files_are_left_out(self):
        """No file or folder whose name starts with "." reaches the tree, at any depth."""
        self.build()
        hidden = [p for p in self.dest.rglob("*") if p.name.startswith(".")]
        self.assertEqual(hidden, [])

    def test_sync_record_is_left_out(self):
        """ais-max/.source.json never reaches the tree, under any name."""
        self.build()
        self.assertEqual(list(self.dest.rglob(".source.json")), [])

    def test_loose_files_are_left_out(self):
        """A file lying loose in a plugin source folder, outside any skill, is not copied."""
        self.build()
        self.assertEqual(list(self.dest.rglob("loose.md")), [])

    def test_manifest_keeps_non_ascii_as_written(self):
        """plugin.json keeps non-ASCII characters as written, not as \\u escapes."""
        original = dict(build_agy.DESCRIPTIONS)
        self.addCleanup(build_agy.DESCRIPTIONS.update, original)
        build_agy.DESCRIPTIONS["ais"] = "Åstrand's skills."
        self.build()
        self.assertIn("Åstrand", (self.dest / "ais" / "plugin.json").read_text(encoding="utf-8"))

    def test_skill_in_both_plugins_is_copied_as_is(self):
        """A skill name in both plugins is copied into both, for the check to report."""
        write(self.ais_max / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        written = self.build()
        self.assertIn("grill-docs", written["ais-max"])


class TestBuildReplaces(Case):

    def test_removes_an_earlier_tree(self):
        """A file from an earlier build is gone after a new build."""
        self.seed_dest()
        self.build()
        self.assertFalse((self.dest / "stale").exists())

    def test_running_twice_is_byte_identical(self):
        """Two builds with the same version and inputs leave the same files and bytes."""
        self.build()
        first = snapshot(self.dest)
        self.build()
        self.assertEqual(snapshot(self.dest), first)

    def test_writes_nothing_outside_dest(self):
        """build_tree changes nothing in the work folder apart from dest."""
        before = {k: v for k, v in snapshot(self.work).items() if not k.startswith(".agy-build")}
        self.build()
        after = {k: v for k, v in snapshot(self.work).items() if not k.startswith(".agy-build")}
        self.assertEqual(after, before)

    def test_leaves_sources_untouched(self):
        """build_tree never writes to the ais or ais-max source folders."""
        before = (snapshot(self.ais), snapshot(self.ais_max))
        self.build()
        self.assertEqual((snapshot(self.ais), snapshot(self.ais_max)), before)


class TestBuildRefuses(Case):

    BAD_VERSIONS = ("1.0", "v1.0.0", "1.0.0-rc1", "", "1.a.0", "1.0.0.0", " 1.0.0", "1.0.0\n")

    def test_bad_version_raises(self):
        """A version that isn't X.Y.Z with digit-only parts raises BuildError."""
        for version in self.BAD_VERSIONS:
            with self.subTest(version=version):
                with self.assertRaises(BuildError):
                    self.build(version)

    def test_bad_version_leaves_dest_untouched(self):
        """A bad version leaves an earlier tree exactly as it was."""
        self.seed_dest()
        before = snapshot(self.dest)
        with self.assertRaises(BuildError):
            self.build("1.0")
        self.assertEqual(snapshot(self.dest), before)

    def test_bad_version_writes_no_tree(self):
        """A bad version with no earlier tree leaves no dest folder behind."""
        with self.assertRaises(BuildError):
            self.build("1.0")
        self.assertFalse(self.dest.exists())

    def test_bad_version_message_names_the_version(self):
        """The bad-version message is one line naming the version."""
        with self.assertRaises(BuildError) as caught:
            self.build("9.9")
        self.assertRegex(str(caught.exception), r"^[^\n]*9\.9[^\n]*$")

    def test_bad_version_is_checked_before_the_sources(self):
        """With a bad version and no source folders, the message is about the version."""
        shutil.rmtree(self.ais)
        with self.assertRaises(BuildError) as caught:
            self.build("9.9")
        self.assertIn("9.9", str(caught.exception))

    def test_missing_ais_raises(self):
        """A missing ais folder raises BuildError naming its path."""
        shutil.rmtree(self.ais)
        with self.assertRaises(BuildError) as caught:
            self.build()
        self.assertIn(str(self.ais), str(caught.exception))

    def test_missing_ais_max_raises(self):
        """A missing ais-max folder raises BuildError naming its path."""
        shutil.rmtree(self.ais_max)
        with self.assertRaises(BuildError) as caught:
            self.build()
        self.assertIn(str(self.ais_max), str(caught.exception))

    def test_ais_as_a_file_raises(self):
        """An ais path that is a file, not a folder, raises BuildError."""
        shutil.rmtree(self.ais)
        self.ais.write_text("not a folder\n")
        with self.assertRaises(BuildError):
            self.build()

    def test_missing_source_leaves_dest_untouched(self):
        """A missing source folder leaves an earlier tree exactly as it was."""
        self.seed_dest()
        before = snapshot(self.dest)
        shutil.rmtree(self.ais_max)
        with self.assertRaises(BuildError):
            self.build()
        self.assertEqual(snapshot(self.dest), before)


# Check


class CheckCase(Case):

    def setUp(self):
        super().setUp()
        self.tree = self.work / "tree"
        write_tree(self.tree)
        self.agy, self.calls = fake_agy(self.bin)

    def check(self, tree=None, agy=None):
        return check_tree(self.tree if tree is None else tree, agy=str(agy or self.agy))

    def assert_one_message(self, starts_with, contains=None):
        messages = self.check()
        self.assertEqual(len(messages), 1, messages)
        self.assertTrue(messages[0].startswith(starts_with), messages)
        if contains is not None:
            self.assertIn(contains, messages[0].lower())


class TestCheckPasses(CheckCase):

    def test_good_tree_passes(self):
        """A tree laid out as promised, which agy accepts, yields no messages."""
        self.assertEqual(self.check(), [])

    def test_built_tree_passes(self):
        """A tree build_tree wrote from good sources passes the check."""
        self.build()
        self.assertEqual(self.check(self.dest), [])

    def test_unknown_manifest_key_is_left_to_agy(self):
        """A manifest key outside the schema adds no message of the check's own (ADR-0010)."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.update(bogus=1))
        self.assertEqual(self.check(), [])

    def test_folded_description_counts(self):
        """A ">" description with an indented line of text counts as a description."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md",
              b"---\nname: grill-docs\ndescription: >\n  Folded text.\n---\n")
        self.assertEqual(self.check(), [])

    def test_literal_strip_description_counts(self):
        """A "|-" description with an indented line of text counts as a description."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md",
              b"---\nname: grill-docs\ndescription: |-\n  Literal text.\n---\n")
        self.assertEqual(self.check(), [])

    def test_check_leaves_the_tree_untouched(self):
        """check_tree never changes the tree it reads."""
        before = snapshot(self.tree)
        self.check()
        self.assertEqual(snapshot(self.tree), before)


class TestCheckTreeRoot(CheckCase):

    def test_missing_tree_is_one_message(self):
        """A tree path that doesn't exist yields exactly one message."""
        self.assertEqual(len(self.check(self.work / "nowhere")), 1)

    def test_missing_tree_runs_nothing(self):
        """A tree path that doesn't exist never runs agy."""
        self.check(self.work / "nowhere")
        self.assertEqual(calls_made(self.calls), [])

    def test_tree_as_a_file_is_one_message(self):
        """A tree path that is a file yields exactly one message."""
        target = self.work / "file"
        target.write_text("x\n")
        self.assertEqual(len(self.check(target)), 1)

    def test_extra_root_entry_fails(self):
        """A folder at the tree root other than ais and ais-max is one message naming it."""
        (self.tree / "third").mkdir()
        self.assert_one_message("third")

    def test_root_plugin_json_fails(self):
        """A plugin.json at the tree root is one message naming it."""
        write(self.tree / "plugin.json", dump({"name": "x"}))
        self.assert_one_message("plugin.json")

    def test_missing_plugin_folder_fails(self):
        """A missing ais-max folder is reported, starting with its name."""
        shutil.rmtree(self.tree / "ais-max")
        messages = self.check()
        self.assertTrue(any(m.startswith("ais-max") for m in messages), messages)


class TestCheckManifest(CheckCase):

    def test_missing_manifest_is_one_message(self):
        """A missing plugin.json is exactly one message, naming that file."""
        (self.tree / "ais" / "plugin.json").unlink()
        self.assert_one_message("ais/plugin.json")

    def test_missing_manifest_skips_agy_for_that_plugin(self):
        """agy is not run on a plugin with no plugin.json."""
        (self.tree / "ais" / "plugin.json").unlink()
        self.check()
        self.assertEqual([c[-1] for c in calls_made(self.calls)], [str(self.tree / "ais-max")])

    def test_invalid_json_fails(self):
        """A plugin.json that isn't valid JSON is one message naming it."""
        write(self.tree / "ais" / "plugin.json", b"{not json\n")
        self.assert_one_message("ais/plugin.json")

    def test_non_object_manifest_fails(self):
        """A plugin.json holding a JSON list, not an object, is one message naming it."""
        write(self.tree / "ais" / "plugin.json", b"[]\n")
        self.assert_one_message("ais/plugin.json")

    def test_name_not_kebab_case_fails(self):
        """A manifest name that isn't lowercase kebab-case is one message saying so."""
        edit_json(self.tree / "ais-max" / "plugin.json", lambda d: d.update(name="Ais_Max"))
        self.assert_one_message("ais-max/plugin.json", contains="kebab")

    def test_name_with_trailing_hyphen_fails(self):
        """A manifest name ending in a hyphen is not kebab-case."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.update(name="ais-"))
        self.assert_one_message("ais/plugin.json", contains="kebab")

    def test_missing_name_fails(self):
        """A manifest with no name is one message naming the file."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.pop("name"))
        self.assert_one_message("ais/plugin.json")

    def test_name_not_matching_folder_fails(self):
        """A kebab-case manifest name that differs from its folder name is one message."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.update(name="other"))
        self.assert_one_message("ais/plugin.json")

    def test_name_breaking_both_rules_is_one_kebab_message(self):
        """A name that is neither kebab-case nor the folder name is one message, about kebab-case."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.update(name="Other"))
        self.assert_one_message("ais/plugin.json", contains="kebab")

    def test_bad_version_fails(self):
        """A manifest version that isn't X.Y.Z is reported against that file."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.update(version="1.0"))
        messages = self.check()
        self.assertTrue(any(m.startswith("ais/plugin.json") for m in messages), messages)

    def test_versions_that_disagree_fail(self):
        """Two good versions that differ are one message."""
        edit_json(self.tree / "ais-max" / "plugin.json", lambda d: d.update(version="1.6.1"))
        self.assertEqual(len(self.check()), 1)


class TestCheckSkills(CheckCase):

    SKILL = Path("ais") / "skills" / "grill-docs"

    def put(self, data):
        write(self.tree / self.SKILL / "SKILL.md", data)

    def test_no_skills_fails(self):
        """A plugin whose skills folder holds no folder is one message naming the plugin."""
        shutil.rmtree(self.tree / "ais-max" / "skills")
        (self.tree / "ais-max" / "skills").mkdir()
        self.assert_one_message("ais-max")

    def test_missing_skills_folder_fails(self):
        """A plugin with no skills folder at all is one message naming the plugin."""
        shutil.rmtree(self.tree / "ais-max" / "skills")
        self.assert_one_message("ais-max")

    def test_missing_skill_md_is_one_message(self):
        """A skill folder with no SKILL.md is exactly one message, naming the folder."""
        (self.tree / self.SKILL / "SKILL.md").unlink()
        self.assert_one_message("ais/skills/grill-docs")

    def test_no_frontmatter_is_one_message(self):
        """A SKILL.md with no frontmatter block is exactly one message."""
        self.put(b"# grill-docs\n\nNo frontmatter.\n")
        self.assert_one_message("ais/skills/grill-docs")

    def test_unclosed_frontmatter_is_one_message(self):
        """A SKILL.md whose frontmatter never closes is exactly one message."""
        self.put(b"---\nname: grill-docs\ndescription: x\n")
        self.assert_one_message("ais/skills/grill-docs")

    def test_name_not_matching_folder_fails(self):
        """A frontmatter name that differs from the folder name is one message."""
        self.put(skill_md("grill"))
        self.assert_one_message("ais/skills/grill-docs")

    def test_missing_name_fails(self):
        """A frontmatter with no name is one message."""
        self.put(skill_md(None))
        self.assert_one_message("ais/skills/grill-docs")

    def test_missing_description_fails(self):
        """A frontmatter with no description is one message."""
        self.put(skill_md("grill-docs", description=None))
        self.assert_one_message("ais/skills/grill-docs")

    def test_empty_description_fails(self):
        """A description key with no value is one message."""
        self.put(b"---\nname: grill-docs\ndescription:\n---\n")
        self.assert_one_message("ais/skills/grill-docs")

    def test_folded_description_with_no_text_fails(self):
        """A ">" description with no indented text below is one message."""
        self.put(b"---\nname: grill-docs\ndescription: >\n---\n")
        self.assert_one_message("ais/skills/grill-docs")

    def test_missing_name_and_description_is_two_messages(self):
        """A frontmatter missing both name and description yields one message for each."""
        self.put(b"---\nother: x\n---\n")
        self.assertEqual(len(self.check()), 2)

    def test_skill_in_both_plugins_fails(self):
        """A skill folder name under both plugins is one message."""
        write(self.tree / "ais-max" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        self.assertEqual(len(self.check()), 1)

    def test_skill_in_both_plugins_message_names_all(self):
        """The duplicate message names the skill and both plugins."""
        write(self.tree / "ais-max" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        message = self.check()[0]
        found = [bool(re.search(p, message)) for p in (r"grill-docs", r"\bais\b(?!-)", r"\bais-max\b")]
        self.assertEqual(found, [True, True, True], message)

    def test_skill_in_both_plugins_named_once(self):
        """The duplicate message names the skill only once."""
        write(self.tree / "ais-max" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        self.assertEqual(self.check()[0].count("grill-docs"), 1)


class TestCheckOrder(CheckCase):

    def test_reports_every_rule_broken(self):
        """A tree breaking several rules gets a message for each, not just the first."""
        edit_json(self.tree / "ais" / "plugin.json", lambda d: d.update(name="Bad_Name"))
        write(self.tree / "ais-max" / "skills" / "unslop" / "SKILL.md", skill_md("other"))
        self.assertEqual(len(self.check()), 2)

    def test_manifest_problems_come_before_skill_problems(self):
        """An ais-max manifest problem is listed before an ais skill problem."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("other"))
        edit_json(self.tree / "ais-max" / "plugin.json", lambda d: d.update(name="Bad_Name"))
        messages = self.check()
        self.assertEqual(starts(messages, ["ais-max/plugin.json", "ais/skills/grill-docs"]), True,
                         messages)

    def test_skill_problems_ordered_by_plugin_then_folder(self):
        """Skill problems come ais first, then by skill folder name."""
        for plugin, name in (("ais-max", "unslop"), ("ais", "new-ticket"), ("ais", "grill-docs")):
            write(self.tree / plugin / "skills" / name / "SKILL.md", skill_md(name, description=None))
        messages = self.check()
        self.assertEqual(starts(messages, ["ais/skills/grill-docs", "ais/skills/new-ticket",
                                           "ais-max/skills/unslop"]), True, messages)

    def test_agy_messages_come_last(self):
        """agy's findings follow the check's own messages."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("other"))
        self.agy, self.calls = fake_agy(self.bin, {
            "ais": (1, report("ais", [("error", "plugin.json", "broken")]), "")})
        self.assertIn(": agy: ", self.check()[-1])

    def test_every_message_is_one_line(self):
        """No message holds a newline."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", b"no frontmatter\n")
        edit_json(self.tree / "ais-max" / "plugin.json", lambda d: d.update(name="X"))
        self.assertEqual([m for m in self.check() if "\n" in m], [])


class TestCheckRunsAgy(CheckCase):

    def test_runs_agy_strict_on_each_plugin(self):
        """agy runs once per plugin, strict and as JSON, in PLUGINS order."""
        self.check()
        self.assertEqual(calls_made(self.calls), [
            ["plugin", "validate", "--strict", "--json", str(self.tree / name)] for name in PLUGINS])

    def test_zero_exit_adds_nothing(self):
        """A zero exit adds no message, even when the report lists findings."""
        self.agy, self.calls = fake_agy(self.bin, {
            "ais": (0, report("ais", [("warning", "plugin.json", "odd")]), "")})
        self.assertEqual(self.check(), [])

    def test_error_finding_becomes_a_message(self):
        """An error in agy's report becomes "<plugin>/<file>: agy: <message>"."""
        self.agy, self.calls = fake_agy(self.bin, {
            "ais-max": (1, report("ais-max", [("error", "skills/x/SKILL.md", "cannot load")]), "")})
        self.assertEqual(self.check(), ["ais-max/skills/x/SKILL.md: agy: cannot load"])

    def test_warning_finding_becomes_a_message(self):
        """A warning in agy's report becomes a message too, since the run is strict."""
        self.agy, self.calls = fake_agy(self.bin, {
            "ais": (1, report("ais", [("warning", "plugin.json", 'unknown field "bogus" is ignored')]),
                    "Error: validation failed in strict mode: 1 warning\n")})
        self.assertEqual(self.check(), ['ais/plugin.json: agy: unknown field "bogus" is ignored'])

    def test_note_finding_is_ignored(self):
        """A note in agy's report adds no message."""
        self.agy, self.calls = fake_agy(self.bin, {
            "ais": (1, report("ais", [("note", "plugin.json", "no logo"),
                                      ("error", "plugin.json", "broken")]), "")})
        self.assertEqual(self.check(), ["ais/plugin.json: agy: broken"])

    def test_findings_from_both_plugins_in_order(self):
        """Findings from both plugins are reported, ais first."""
        self.agy, self.calls = fake_agy(self.bin, {
            "ais-max": (1, report("ais-max", [("error", "plugin.json", "second")]), ""),
            "ais": (1, report("ais", [("error", "plugin.json", "first")]), "")})
        self.assertEqual(self.check(), ["ais/plugin.json: agy: first",
                                        "ais-max/plugin.json: agy: second"])

    def test_non_json_output_is_one_message(self):
        """A failing run whose stdout isn't JSON is one message with stderr's last line."""
        self.agy, self.calls = fake_agy(self.bin, {
            "ais": (2, "garbage", "starting\nError: something broke\n")})
        self.assertEqual(self.check(), ["ais: agy: Error: something broke"])

    def test_missing_agy_is_one_message(self):
        """When agy can't be started, the check reports it once, not once per plugin."""
        messages = self.check(agy=self.work / "no-such-agy")
        self.assertEqual(len(messages), 1, messages)

    def test_missing_agy_message_names_agy(self):
        """The missing-agy message says agy couldn't run (ADR-0009)."""
        messages = self.check(agy=self.work / "no-such-agy")
        self.assertIn("agy", messages[0])

    def test_missing_agy_fails_a_good_tree(self):
        """A good tree fails when agy can't be started. The check never skips it."""
        self.assertNotEqual(self.check(agy=self.work / "no-such-agy"), [])

    def test_default_agy_is_found_on_path(self):
        """With no agy argument, check_tree runs "agy" from PATH."""
        old = os.environ.get("PATH", "")
        self.addCleanup(os.environ.__setitem__, "PATH", old)
        os.environ["PATH"] = f"{self.bin}{os.pathsep}{old}"
        check_tree(self.tree)
        self.assertEqual(len(calls_made(self.calls)), 2)


# Command line


class TestMain(Case):
    """main, run as the release runs it, from a copy of the project in a temp folder."""

    def setUp(self):
        super().setUp()
        write(self.work / "scripts" / "build-agy.py", SCRIPT.read_bytes())
        self.agy, self.calls = fake_agy(self.bin)
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}")

    def run_main(self, *args):
        return subprocess.run([sys.executable, str(self.work / "scripts" / "build-agy.py"), *args],
                              cwd=self.work, env=self.env, capture_output=True, text=True)

    def test_build_exits_zero(self):
        """build with a good version exits 0."""
        self.assertEqual(self.run_main("build", VERSION).returncode, 0)

    def test_build_prints_a_count_per_plugin(self):
        """build prints one count line per plugin, ais first."""
        self.assertEqual(self.run_main("build", VERSION).stdout,
                         "Wrote 2 skills to .agy-build/ais\nWrote 2 skills to .agy-build/ais-max\n")

    def test_build_writes_the_build_folder_at_the_root(self):
        """build writes .agy-build beside ais and ais-max."""
        self.run_main("build", VERSION)
        self.assertTrue((self.work / ".agy-build" / "ais" / "plugin.json").is_file())

    def test_build_never_runs_the_check(self):
        """build writes the tree without calling agy."""
        result = self.run_main("build", VERSION)
        self.assertEqual((result.returncode, calls_made(self.calls)), (0, []))

    def test_bad_version_exits_one(self):
        """build with a bad version exits 1 cleanly, without a traceback."""
        result = self.run_main("build", "1.0")
        self.assertEqual((result.returncode, "Traceback" in result.stderr), (1, False))

    def test_bad_version_prints_one_error_line(self):
        """build with a bad version prints one "error: " line on stderr."""
        self.assertRegex(self.run_main("build", "1.0").stderr, r"^error: [^\n]*1\.0[^\n]*\n$")

    def test_bad_version_leaves_the_build_folder(self):
        """build with a bad version leaves an earlier tree as it was."""
        write(self.work / ".agy-build" / "ais" / "plugin.json", b"earlier\n")
        before = snapshot(self.work / ".agy-build")
        result = self.run_main("build", "1.0")
        self.assertEqual(("Traceback" in result.stderr, snapshot(self.work / ".agy-build")),
                         (False, before))

    def test_check_passes_a_built_tree(self):
        """check on a freshly built tree exits 0 and prints "Tree passes"."""
        self.run_main("build", VERSION)
        result = self.run_main("check")
        self.assertEqual((result.returncode, result.stdout), (0, "Tree passes\n"))

    def test_check_reads_the_build_folder_by_default(self):
        """check with no TREE runs agy on the plugins under .agy-build."""
        self.run_main("build", VERSION)
        self.run_main("check")
        self.assertEqual([c[-1] for c in calls_made(self.calls)],
                         [str(self.work / ".agy-build" / n) for n in PLUGINS])

    def test_check_takes_a_tree_argument(self):
        """check TREE checks that tree instead of the build folder."""
        tree = self.work / "elsewhere"
        write_tree(tree)
        result = self.run_main("check", str(tree))
        self.assertEqual((result.returncode, result.stdout), (0, "Tree passes\n"))

    def test_check_failure_exits_one(self):
        """check on a tree that breaks a rule exits 1."""
        tree = self.work / "elsewhere"
        write_tree(tree)
        (tree / "ais" / "plugin.json").unlink()
        result = self.run_main("check", str(tree))
        self.assertEqual((result.returncode, "Traceback" in result.stderr), (1, False))

    def test_check_failure_prints_each_message_on_stderr(self):
        """check prints each message on its own line to stderr."""
        tree = self.work / "elsewhere"
        write_tree(tree)
        (tree / "ais" / "plugin.json").unlink()
        write(tree / "ais-max" / "skills" / "unslop" / "SKILL.md", skill_md("other"))
        lines = self.run_main("check", str(tree)).stderr.splitlines()
        self.assertEqual(starts(lines, ["ais/plugin.json", "ais-max/skills/unslop"]), True, lines)

    def test_check_of_a_missing_tree_exits_one(self):
        """check with no build folder exits 1 without a traceback."""
        result = self.run_main("check")
        self.assertEqual((result.returncode, "Traceback" in result.stderr), (1, False))

    def test_no_arguments_exits_two(self):
        """No subcommand exits 2."""
        self.assertEqual(self.run_main().returncode, 2)

    def test_unknown_subcommand_exits_two(self):
        """An unknown subcommand exits 2."""
        self.assertEqual(self.run_main("publish", VERSION).returncode, 2)

    def test_build_without_version_exits_two(self):
        """build with no version exits 2."""
        self.assertEqual(self.run_main("build").returncode, 2)

    def test_too_many_arguments_exits_two(self):
        """check with two trees exits 2."""
        self.assertEqual(self.run_main("check", "a", "b").returncode, 2)

    def test_main_returns_the_code_in_process(self):
        """main returns its exit code instead of raising SystemExit."""
        self.assertEqual(build_agy.main(["nonsense"]), 2)


# This repo


class TestRealTree(unittest.TestCase):
    """This repo's own ais/ and ais-max/, built and checked with the real agy."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.dest = self.work / ".agy-build"

    def test_built_tree_passes_the_check(self):
        """The tree built from this repo passes every rule, agy's strict validation included."""
        build_tree("1.0.0", dest=self.dest)
        self.assertEqual(check_tree(self.dest), [])

    def test_built_tree_holds_every_skill(self):
        """Every skill folder in ais/ and ais-max/ is in the built tree."""
        written = build_tree("1.0.0", dest=self.dest)
        for plugin in PLUGINS:
            with self.subTest(plugin=plugin):
                expected = sorted(p.name for p in (ROOT / plugin).iterdir()
                                  if p.is_dir() and not p.name.startswith("."))
                self.assertEqual(written[plugin], expected)


if __name__ == "__main__":
    unittest.main()
