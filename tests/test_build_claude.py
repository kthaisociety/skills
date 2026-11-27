"""Tests for scripts/build-claude.py, which builds and checks the ais-claude tree.

Every test runs in a temp folder against fake ais and ais-max folders and a
fake `claude` command, except TestRealTree, which builds from this repo's own
ais/ and ais-max/ and runs the real Claude Code.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build-claude.py"
spec = importlib.util.spec_from_file_location("build_claude", SCRIPT)
build_claude = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_claude)

build_tree = build_claude.build_tree
check_tree = build_claude.check_tree
BuildError = build_claude.BuildError

VERSION = "1.4.0"
AIS_SKILLS = ("grill-docs", "new-ticket")
MAX_SKILLS = ("architect-ticket", "unslop")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def skill_md(name, description="Does a thing."):
    lines = ["---", f"name: {name}"]
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
    write(tree / ".claude-plugin" / "marketplace.json", dump({
        "name": "ais-claude",
        "owner": {"name": "KTHAIS"},
        "description": "KTHAIS skills.",
        "plugins": [
            {"name": "ais", "source": "./ais", "version": version, "description": "Base."},
            {"name": "ais-max", "source": "./ais-max", "version": version,
             "description": "Extras. Install ais first."},
        ],
    }))
    for plugin, skills in (("ais", ais_skills), ("ais-max", max_skills)):
        write(tree / plugin / ".claude-plugin" / "plugin.json", dump({
            "name": plugin, "version": version, "description": "A plugin.",
            "author": {"name": "KTHAIS"},
        }))
        for name in skills:
            write(tree / plugin / "skills" / name / "SKILL.md", skill_md(name))


def edit_json(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_bytes(dump(data))


def fake_claude(folder, code=0, stdout="", stderr=""):
    """An executable `claude` in folder that logs its arguments, prints, and exits with code."""
    calls = folder / "claude-calls.jsonl"
    script = folder / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"with open({str(calls)!r}, 'a') as log:\n"
        "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({code})\n")
    script.chmod(0o755)
    return script, calls


def calls_made(calls):
    if not calls.exists():
        return []
    return [json.loads(line) for line in calls.read_text().splitlines()]


def report(errors=(), warnings=()):
    """A JSON report shaped like `claude plugin validate --json` prints."""
    return json.dumps({
        "success": not errors and not warnings,
        "manifest": {
            "errors": [{"path": p, "message": m, "code": None} for p, m in errors],
            "warnings": [{"path": p, "message": m, "code": None} for p, m in warnings],
        },
    })


class Case(unittest.TestCase):

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.ais = self.work / "ais"
        self.ais_max = self.work / "ais-max"
        self.dest = self.work / ".claude-build"
        self.bin = self.work / "bin"
        self.bin.mkdir()
        build_sources(self.ais, self.ais_max)

    def build(self, version=VERSION):
        return build_tree(version, ais=self.ais, ais_max=self.ais_max, dest=self.dest)

    def seed_dest(self):
        write(self.dest / "stale" / "old.md", b"from an earlier build\n")


class TestBuildWrites(Case):

    def test_returns_skill_names_per_plugin(self):
        """build_tree returns each plugin's skill folder names, sorted."""
        self.assertEqual(self.build(), {"ais": sorted(AIS_SKILLS), "ais-max": sorted(MAX_SKILLS)})

    def test_writes_the_marketplace_manifest(self):
        """The marketplace manifest holds exactly the promised keys and values, in order."""
        self.build()
        expected = dump({
            "name": "ais-claude",
            "owner": {"name": build_claude.AUTHOR},
            "description": build_claude.MARKETPLACE_DESCRIPTION,
            "plugins": [
                {"name": name, "source": f"./{name}", "version": VERSION,
                 "description": build_claude.DESCRIPTIONS[name]}
                for name in ("ais", "ais-max")
            ],
        })
        self.assertEqual((self.dest / ".claude-plugin" / "marketplace.json").read_bytes(), expected)

    def test_writes_each_plugin_manifest(self):
        """Each plugin.json holds the name, the shared version, its description and the author, in order."""
        self.build()
        for name in ("ais", "ais-max"):
            with self.subTest(plugin=name):
                expected = dump({"name": name, "version": VERSION,
                                 "description": build_claude.DESCRIPTIONS[name],
                                 "author": {"name": build_claude.AUTHOR}})
                self.assertEqual((self.dest / name / ".claude-plugin" / "plugin.json").read_bytes(),
                                 expected)

    def test_ais_max_description_says_to_install_ais_first(self):
        """The ais-max marketplace entry tells the reader to install ais first."""
        self.build()
        manifest = json.loads((self.dest / ".claude-plugin" / "marketplace.json").read_text())
        entry = next(p for p in manifest["plugins"] if p["name"] == "ais-max")
        self.assertIn("install ais first", entry["description"].lower())

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

    def test_skills_never_cross_plugins(self):
        """No ais skill appears under ais-max and no ais-max skill under ais."""
        self.build()
        self.assertEqual({p.name for p in (self.dest / "ais" / "skills").iterdir()}, set(AIS_SKILLS))
        self.assertEqual({p.name for p in (self.dest / "ais-max" / "skills").iterdir()}, set(MAX_SKILLS))

    def test_copies_extra_files_unchanged(self):
        """A skill's files beside SKILL.md, non-ASCII bytes included, are copied unchanged."""
        self.build()
        self.assertEqual((self.dest / "ais-max" / "skills" / "unslop" / "LICENSE").read_bytes(),
                         b"license \xc3\xa5\n")

    def test_copies_nested_files(self):
        """Files in a skill's subfolders are copied at the same relative path."""
        self.build()
        self.assertEqual(
            (self.dest / "ais" / "skills" / "grill-docs" / "deep" / "nested.md").read_bytes(), b"nested\n")

    def test_skips_hidden_files(self):
        """A file whose name starts with "." in a skill folder is not copied."""
        self.build()
        self.assertFalse((self.dest / "ais" / "skills" / "grill-docs" / ".hidden").exists())

    def test_skips_hidden_folders(self):
        """A folder whose name starts with "." in a skill folder is not copied."""
        self.build()
        self.assertFalse((self.dest / "ais" / "skills" / "grill-docs" / ".hidden-dir").exists())

    def test_skips_hidden_files_in_subfolders(self):
        """A hidden file deeper inside a skill folder is not copied."""
        self.build()
        self.assertFalse((self.dest / "ais" / "skills" / "grill-docs" / "deep" / ".also-hidden").exists())

    def test_sync_record_never_reaches_the_tree(self):
        """ais-max/.source.json is nowhere in the tree."""
        self.build()
        self.assertEqual([p for p in self.dest.rglob(".source.json")], [])

    def test_loose_files_are_not_copied(self):
        """A file lying loose in a plugin's source folder is nowhere in the tree."""
        self.build()
        self.assertEqual([p for p in self.dest.rglob("loose.md")], [])

    def test_tree_holds_only_what_is_promised(self):
        """The tree holds the manifests and the skill files, and nothing else."""
        self.build()
        files = {str(p.relative_to(self.dest)) for p in self.dest.rglob("*") if p.is_file()}
        self.assertEqual(files, {
            ".claude-plugin/marketplace.json",
            "ais/.claude-plugin/plugin.json",
            "ais/skills/grill-docs/SKILL.md",
            "ais/skills/grill-docs/RECORD-FORMAT.md",
            "ais/skills/grill-docs/deep/nested.md",
            "ais/skills/new-ticket/SKILL.md",
            "ais-max/.claude-plugin/plugin.json",
            "ais-max/skills/architect-ticket/SKILL.md",
            "ais-max/skills/unslop/SKILL.md",
            "ais-max/skills/unslop/LICENSE",
        })

    def test_removes_an_earlier_tree(self):
        """Anything an earlier build left in dest is gone after the build."""
        self.seed_dest()
        self.build()
        self.assertFalse((self.dest / "stale").exists())

    def test_creates_dest_when_missing(self):
        """A dest whose parent folders don't exist yet is created."""
        self.dest = self.work / "deeper" / "still" / ".claude-build"
        self.build()
        self.assertTrue((self.dest / ".claude-plugin" / "marketplace.json").is_file())

    def test_second_build_is_byte_identical(self):
        """Building twice with the same version and inputs leaves dest byte-identical."""
        self.build()
        first = snapshot(self.dest)
        self.build()
        self.assertEqual(snapshot(self.dest), first)

    def test_new_version_reaches_every_manifest(self):
        """Rebuilding with a new version writes it into all three manifests."""
        self.build("1.0.0")
        self.build("2.0.0")
        marketplace = json.loads((self.dest / ".claude-plugin" / "marketplace.json").read_text())
        versions = [p["version"] for p in marketplace["plugins"]] + [
            json.loads((self.dest / n / ".claude-plugin" / "plugin.json").read_text())["version"]
            for n in ("ais", "ais-max")]
        self.assertEqual(versions, ["2.0.0"] * 4)

    def test_never_writes_the_sources(self):
        """ais and ais-max are byte-identical after a build."""
        before = (snapshot(self.ais), snapshot(self.ais_max))
        self.build()
        self.assertEqual((snapshot(self.ais), snapshot(self.ais_max)), before)

    def test_writes_nothing_beside_dest(self):
        """Nothing outside dest changes, temp files included."""
        before = {p.name: snapshot(p) for p in self.work.iterdir() if p != self.dest}
        self.build()
        after = {p.name: snapshot(p) for p in self.work.iterdir() if p != self.dest}
        self.assertEqual(after, before)

    def test_build_copies_a_skill_in_both_plugins(self):
        """A skill name in both sources is copied into both plugins, for the check to report."""
        write(self.ais_max / "new-ticket" / "SKILL.md", skill_md("new-ticket"))
        self.build()
        self.assertTrue((self.dest / "ais-max" / "skills" / "new-ticket" / "SKILL.md").is_file())


class TestBuildStops(Case):

    BAD_VERSIONS = ("1.0", "v1.0.0", "1.0.0-rc1", "1.0.0.0", "a.b.c", "1..0", " 1.0.0", "1.0.0 ", "1.0.0\n")

    def test_bad_version_raises(self):
        """A version that is not X.Y.Z raises BuildError naming the version."""
        for version in self.BAD_VERSIONS:
            with self.subTest(version=version):
                with self.assertRaises(BuildError) as caught:
                    self.build(version)
                self.assertIn(version.strip(), str(caught.exception))

    def test_empty_version_raises(self):
        """An empty version raises BuildError."""
        with self.assertRaises(BuildError):
            self.build("")

    def test_bad_version_writes_nothing(self):
        """A bad version leaves a missing dest missing."""
        with self.assertRaises(BuildError):
            self.build("1.0")
        self.assertFalse(self.dest.exists())

    def test_bad_version_leaves_an_earlier_tree(self):
        """A bad version leaves an existing dest exactly as it was."""
        self.seed_dest()
        before = snapshot(self.dest)
        with self.assertRaises(BuildError):
            self.build("1.0")
        self.assertEqual(snapshot(self.dest), before)

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

    def test_missing_source_leaves_an_earlier_tree(self):
        """A missing source folder leaves an existing dest exactly as it was."""
        self.seed_dest()
        before = snapshot(self.dest)
        shutil.rmtree(self.ais_max)
        with self.assertRaises(BuildError):
            self.build()
        self.assertEqual(snapshot(self.dest), before)

    def test_error_message_is_one_line(self):
        """Every BuildError message is a single line."""
        with self.assertRaises(BuildError) as caught:
            self.build("nope")
        self.assertNotIn("\n", str(caught.exception))


class CheckCase(Case):

    def setUp(self):
        super().setUp()
        self.tree = self.work / "tree"
        write_tree(self.tree)
        self.claude, self.calls = fake_claude(self.bin)

    def check(self):
        return check_tree(self.tree, claude=str(self.claude))

    def assert_reports(self, *needles):
        messages = self.check()
        hits = [m for m in messages if all(n in m for n in needles)]
        self.assertTrue(hits, f"no message holds {needles}: {messages}")

    def skill(self, plugin, name):
        return self.tree / plugin / "skills" / name / "SKILL.md"


class TestCheckPasses(CheckCase):

    def test_good_tree_passes(self):
        """A tree laid out as promised, with Claude Code accepting it, gives no messages."""
        self.assertEqual(self.check(), [])

    def test_runs_claude_strict_on_the_tree(self):
        """The check runs claude plugin validate --strict --json on the tree, once."""
        self.check()
        self.assertEqual(calls_made(self.calls),
                         [["plugin", "validate", "--strict", "--json", str(self.tree)]])

    def test_never_writes_the_tree(self):
        """The tree is byte-identical after a check."""
        before = snapshot(self.tree)
        self.check()
        self.assertEqual(snapshot(self.tree), before)


class TestCheckSkills(CheckCase):

    def test_skill_in_both_plugins_fails(self):
        """A skill folder name under both plugins gives a message naming it."""
        write(self.skill("ais-max", "new-ticket"), skill_md("new-ticket"))
        self.assert_reports("new-ticket")

    def test_skill_in_both_plugins_names_both(self):
        """The duplicate-skill message names ais and ais-max."""
        write(self.skill("ais-max", "new-ticket"), skill_md("new-ticket"))
        self.assert_reports("new-ticket", "ais", "ais-max")

    def test_skill_in_both_plugins_is_reported_once(self):
        """A skill in both plugins gives one duplicate message, not one per plugin."""
        write(self.skill("ais-max", "new-ticket"), skill_md("new-ticket"))
        messages = [m for m in self.check() if "new-ticket" in m]
        self.assertEqual(len(messages), 1, messages)

    def test_frontmatter_name_mismatch_fails(self):
        """A SKILL.md whose name differs from its folder gives a message naming the skill's path."""
        write(self.skill("ais", "new-ticket"), skill_md("old-ticket"))
        self.assert_reports("ais/skills/new-ticket")

    def test_missing_frontmatter_name_fails(self):
        """A SKILL.md whose frontmatter has no name gives a message naming the skill's path."""
        write(self.skill("ais", "new-ticket"), b"---\ndescription: Does a thing.\n---\n")
        self.assert_reports("ais/skills/new-ticket")

    def test_missing_description_fails(self):
        """A SKILL.md with no description gives a message naming the skill's path."""
        write(self.skill("ais-max", "unslop"), skill_md("unslop", description=None))
        self.assert_reports("ais-max/skills/unslop")

    def test_empty_description_fails(self):
        """A SKILL.md with an empty description gives a message naming the skill's path."""
        write(self.skill("ais-max", "unslop"), skill_md("unslop", description=""))
        self.assert_reports("ais-max/skills/unslop")

    def test_no_frontmatter_fails(self):
        """A SKILL.md with no frontmatter block gives a message naming the skill's path."""
        write(self.skill("ais-max", "unslop"), b"# unslop\n\nJust text.\n")
        self.assert_reports("ais-max/skills/unslop")

    def test_missing_skill_md_fails(self):
        """A skill folder with no SKILL.md gives a message naming the skill's path."""
        self.skill("ais", "grill-docs").unlink()
        self.assert_reports("ais/skills/grill-docs")

    def test_unterminated_frontmatter_fails(self):
        """A SKILL.md whose frontmatter never closes gives a message naming the skill's path."""
        write(self.skill("ais", "new-ticket"), b"---\nname: new-ticket\ndescription: Does a thing.\n")
        self.assert_reports("ais/skills/new-ticket")

    def test_block_scalar_description_passes(self):
        """A description written as a folded YAML block counts as present."""
        write(self.skill("ais", "new-ticket"),
              b"---\nname: new-ticket\ndescription: >\n  Does a thing\n  over two lines.\n---\n")
        self.assertEqual(self.check(), [])

    def test_quoted_frontmatter_passes(self):
        """A quoted name and description count like plain ones."""
        write(self.skill("ais", "new-ticket"),
              b'---\nname: "new-ticket"\ndescription: \'Does a thing.\'\n---\n')
        self.assertEqual(self.check(), [])


class TestCheckManifests(CheckCase):

    def marketplace(self):
        return self.tree / ".claude-plugin" / "marketplace.json"

    def plugin_json(self, name):
        return self.tree / name / ".claude-plugin" / "plugin.json"

    def test_listed_plugin_folder_missing_fails(self):
        """A marketplace entry whose source folder doesn't exist gives a message naming the folder."""
        shutil.rmtree(self.tree / "ais-max")
        self.assert_reports("ais-max")

    def test_source_naming_a_missing_folder_fails(self):
        """An entry whose source names a missing folder fails even when the plugin's own folder exists."""
        edit_json(self.marketplace(), lambda d: d["plugins"][0].update(source="./gone"))
        self.assert_reports("gone")

    def test_missing_source_fails(self):
        """An entry with no source gives a message naming the marketplace file and the plugin."""
        edit_json(self.marketplace(), lambda d: d["plugins"][1].pop("source"))
        self.assert_reports(".claude-plugin/marketplace.json", "ais-max")

    def test_source_outside_the_tree_fails(self):
        """An entry whose source leaves the tree fails even when that folder exists."""
        (self.work / "outside").mkdir()
        edit_json(self.marketplace(), lambda d: d["plugins"][0].update(source="../outside"))
        self.assert_reports(".claude-plugin/marketplace.json", "ais")

    def test_entry_version_disagrees_with_plugin_json_fails(self):
        """A marketplace entry version unlike its plugin.json version gives a message."""
        edit_json(self.plugin_json("ais-max"), lambda d: d.update(version="1.4.1"))
        self.assert_reports("1.4.1")

    def test_plugin_versions_disagree_fails(self):
        """Two marketplace entries with different versions give a message."""
        edit_json(self.marketplace(), lambda d: d["plugins"][1].update(version="9.9.9"))
        self.assert_reports("9.9.9")

    def test_version_not_x_y_z_fails(self):
        """Every manifest agreeing on a version that is not X.Y.Z still gives a message."""
        write_tree(self.tree, version="latest")
        self.assert_reports("latest")

    def test_missing_marketplace_fails(self):
        """A tree with no marketplace manifest gives a message naming the file."""
        self.marketplace().unlink()
        self.assert_reports(".claude-plugin/marketplace.json")

    def test_marketplace_not_json_fails(self):
        """A marketplace manifest that is not JSON gives a message naming the file."""
        write(self.marketplace(), b"{not json")
        self.assert_reports(".claude-plugin/marketplace.json")

    def test_marketplace_not_an_object_fails(self):
        """A marketplace manifest holding a JSON list gives a message naming the file."""
        write(self.marketplace(), b"[]\n")
        self.assert_reports(".claude-plugin/marketplace.json")

    def test_marketplace_missing_a_plugin_fails(self):
        """A marketplace that doesn't list ais-max gives a message naming it."""
        edit_json(self.marketplace(), lambda d: d.update(plugins=d["plugins"][:1]))
        self.assert_reports(".claude-plugin/marketplace.json", "ais-max")

    def test_marketplace_extra_plugin_fails(self):
        """A marketplace listing a plugin besides ais and ais-max gives a message naming it."""
        def add(d):
            d["plugins"].append({"name": "stray", "source": "./stray", "version": VERSION,
                                 "description": "x"})
        edit_json(self.marketplace(), add)
        self.assert_reports("stray")

    def test_marketplace_plugin_listed_twice_fails(self):
        """A marketplace listing ais twice gives a message naming the file."""
        edit_json(self.marketplace(), lambda d: d["plugins"].append(dict(d["plugins"][0])))
        self.assert_reports(".claude-plugin/marketplace.json")

    def test_marketplace_plugins_not_a_list_fails(self):
        """A marketplace whose plugins is not a list gives a message naming the file."""
        edit_json(self.marketplace(), lambda d: d.update(plugins={}))
        self.assert_reports(".claude-plugin/marketplace.json", "plugins is not a list")

    def test_missing_plugin_json_fails(self):
        """A plugin folder with no plugin.json gives a message naming the file."""
        self.plugin_json("ais").unlink()
        self.assert_reports("ais/.claude-plugin/plugin.json")

    def test_plugin_json_not_json_fails(self):
        """A plugin.json that is not JSON gives a message naming the file."""
        write(self.plugin_json("ais-max"), b"nope")
        self.assert_reports("ais-max/.claude-plugin/plugin.json")

    def test_plugin_json_wrong_name_fails(self):
        """A plugin.json whose name differs from its plugin gives a message naming the file."""
        edit_json(self.plugin_json("ais"), lambda d: d.update(name="base"))
        self.assert_reports("ais/.claude-plugin/plugin.json")


class TestCheckReporting(CheckCase):

    def break_three_rules(self):
        edit_json(self.tree / "ais" / ".claude-plugin" / "plugin.json", lambda d: d.update(name="base"))
        write(self.skill("ais-max", "unslop"), skill_md("unslop", description=None))
        write(self.skill("ais", "new-ticket"), skill_md("old-ticket"))

    def test_reports_every_broken_rule(self):
        """A tree breaking three rules gets a message about each."""
        self.break_three_rules()
        messages = "\n".join(self.check())
        for needle in ("ais/.claude-plugin/plugin.json", "ais-max/skills/unslop", "ais/skills/new-ticket"):
            with self.subTest(needle=needle):
                self.assertIn(needle, messages)

    def test_messages_are_one_line_and_start_with_a_relative_path(self):
        """Every message is one line, starts with a path relative to the tree, then ": "."""
        self.break_three_rules()
        for message in self.check():
            with self.subTest(message=message):
                self.assertNotIn("\n", message)
                self.assertNotIn(str(self.tree), message)
                self.assertRegex(message, r"^[^\s:][^:]*: \S")

    def test_messages_come_in_the_promised_order(self):
        """Marketplace, then plugin manifest, then skills by plugin and folder, then Claude Code."""
        edit_json(self.tree / ".claude-plugin" / "marketplace.json",
                  lambda d: d["plugins"].append({"name": "stray", "source": "./stray",
                                                 "version": VERSION, "description": "x"}))
        edit_json(self.tree / "ais-max" / ".claude-plugin" / "plugin.json", lambda d: d.update(name="max"))
        write(self.skill("ais-max", "unslop"), skill_md("unslop", description=None))
        write(self.skill("ais", "new-ticket"), skill_md("old-ticket"))
        self.claude, self.calls = fake_claude(self.bin, code=1, stdout=report(errors=[("x", "bad")]))
        messages = self.check()

        def first(needle):
            return next(i for i, m in enumerate(messages) if needle in m)

        order = [first("stray"), first("ais-max/.claude-plugin/plugin.json"),
                 first("ais/skills/new-ticket"), first("ais-max/skills/unslop"), first("claude: ")]
        self.assertEqual(order, sorted(order), messages)


class TestCheckClaude(CheckCase):

    def test_claude_errors_become_messages(self):
        """Each error in Claude Code's report becomes "claude: <path>: <message>"."""
        self.claude, self.calls = fake_claude(
            self.bin, code=1, stdout=report(errors=[("plugins[0].source", "Path not found")]))
        self.assertIn("claude: plugins[0].source: Path not found", self.check())

    def test_claude_warnings_become_messages(self):
        """Each warning in Claude Code's report becomes "claude: <path>: <message>"."""
        self.claude, self.calls = fake_claude(
            self.bin, code=1, stdout=report(warnings=[("description", "No marketplace description")]))
        self.assertIn("claude: description: No marketplace description", self.check())

    def test_one_message_per_claude_problem(self):
        """Two errors and a warning in the report give three claude messages."""
        self.claude, self.calls = fake_claude(self.bin, code=1, stdout=report(
            errors=[("a", "one"), ("b", "two")], warnings=[("c", "three")]))
        self.assertEqual([m for m in self.check() if m.startswith("claude: ")],
                         ["claude: a: one", "claude: b: two", "claude: c: three"])

    def test_claude_zero_exit_adds_nothing(self):
        """A zero exit from Claude Code adds no message, whatever it prints."""
        self.claude, self.calls = fake_claude(self.bin, code=0, stdout=report(warnings=[("x", "y")]))
        self.assertEqual(self.check(), [])

    def test_claude_output_not_json_gives_last_stderr_line(self):
        """A non-zero exit without a JSON report gives one message holding stderr's last line."""
        self.claude, self.calls = fake_claude(self.bin, code=2, stdout="garbage",
                                              stderr="first line\nunknown option --strict\n")
        messages = [m for m in self.check() if "unknown option --strict" in m]
        self.assertEqual(len(messages), 1, self.check())

    def test_claude_not_installed_fails(self):
        """When the claude command can't be started, the check gives a message instead of passing."""
        messages = check_tree(self.tree, claude=str(self.work / "no-such-claude"))
        self.assertEqual(len(messages), 1, messages)

    def test_claude_not_installed_still_reports_own_rules(self):
        """A missing claude command doesn't stop the check reporting the tree's own problems."""
        write(self.skill("ais-max", "unslop"), skill_md("unslop", description=None))
        messages = check_tree(self.tree, claude=str(self.work / "no-such-claude"))
        self.assertEqual(len(messages), 2, messages)


class TestCheckMissingTree(CheckCase):

    def test_missing_tree_gives_one_message(self):
        """A tree folder that doesn't exist gives exactly one message."""
        shutil.rmtree(self.tree)
        self.assertEqual(len(self.check()), 1)

    def test_missing_tree_runs_nothing(self):
        """A tree folder that doesn't exist never runs claude."""
        shutil.rmtree(self.tree)
        self.check()
        self.assertEqual(calls_made(self.calls), [])


class TestMain(Case):
    """main, run as the release runs it, from a copy of the project in a temp folder."""

    def setUp(self):
        super().setUp()
        write(self.work / "scripts" / "build-claude.py", SCRIPT.read_bytes())
        self.claude, self.calls = fake_claude(self.bin)
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}")

    def run_main(self, *args):
        return subprocess.run([sys.executable, str(self.work / "scripts" / "build-claude.py"), *args],
                              cwd=self.work, env=self.env, capture_output=True, text=True)

    def test_build_exits_zero(self):
        """build with a good version exits 0."""
        self.assertEqual(self.run_main("build", VERSION).returncode, 0)

    def test_build_prints_a_count_per_plugin(self):
        """build prints one count line per plugin, ais first."""
        self.assertEqual(self.run_main("build", VERSION).stdout,
                         "Wrote 2 skills to .claude-build/ais\nWrote 2 skills to .claude-build/ais-max\n")

    def test_build_writes_the_build_folder_at_the_root(self):
        """build writes .claude-build beside ais and ais-max."""
        self.run_main("build", VERSION)
        self.assertTrue((self.work / ".claude-build" / ".claude-plugin" / "marketplace.json").is_file())

    def test_build_never_runs_the_check(self):
        """build writes the tree without calling claude."""
        self.run_main("build", VERSION)
        self.assertEqual(calls_made(self.calls), [])

    def test_bad_version_exits_one(self):
        """build with a bad version exits 1."""
        self.assertEqual(self.run_main("build", "1.0").returncode, 1)

    def test_bad_version_prints_one_error_line(self):
        """build with a bad version prints one "error: " line on stderr and no traceback."""
        stderr = self.run_main("build", "1.0").stderr
        self.assertRegex(stderr, r"^error: [^\n]*1\.0[^\n]*\n$")

    def test_check_passing_tree_exits_zero(self):
        """check on a passing tree exits 0."""
        write_tree(self.dest)
        self.assertEqual(self.run_main("check").returncode, 0)

    def test_check_passing_tree_prints_tree_passes(self):
        """check on a passing tree prints "Tree passes"."""
        write_tree(self.dest)
        self.assertEqual(self.run_main("check").stdout, "Tree passes\n")

    def test_check_defaults_to_the_build_folder(self):
        """check with no tree runs claude on .claude-build at the root."""
        write_tree(self.dest)
        self.run_main("check")
        self.assertEqual(calls_made(self.calls),
                         [["plugin", "validate", "--strict", "--json", str(self.dest)]])

    def test_check_takes_a_tree_path(self):
        """check TREE checks that tree, not the build folder."""
        other = self.work / "elsewhere"
        write_tree(other)
        self.run_main("check", str(other))
        self.assertEqual(calls_made(self.calls),
                         [["plugin", "validate", "--strict", "--json", str(other)]])

    def test_check_failing_tree_exits_one(self):
        """check on a tree that breaks a rule exits 1."""
        write_tree(self.dest)
        write(self.dest / "ais" / "skills" / "new-ticket" / "SKILL.md", skill_md("other"))
        self.assertEqual(self.run_main("check").returncode, 1)

    def test_check_failing_tree_prints_no_traceback(self):
        """check on a tree that breaks a rule fails cleanly, without a traceback."""
        write_tree(self.dest)
        write(self.dest / "ais" / "skills" / "new-ticket" / "SKILL.md", skill_md("other"))
        self.assertNotIn("Traceback", self.run_main("check").stderr)

    def test_check_failing_tree_prints_every_message(self):
        """check prints each message check_tree returns on its own stderr line, in order."""
        write_tree(self.dest)
        write(self.dest / "ais" / "skills" / "new-ticket" / "SKILL.md", skill_md("other"))
        write(self.dest / "ais-max" / "skills" / "unslop" / "SKILL.md", skill_md("unslop", None))
        expected = check_tree(self.dest, claude=str(self.claude))
        self.assertEqual(self.run_main("check").stderr, "".join(m + "\n" for m in expected))

    def test_wrong_arguments_exit_two(self):
        """No subcommand, an unknown one, or the wrong number of arguments exits 2."""
        for args in ((), ("deploy",), ("build",), ("build", "1.0.0", "extra"), ("check", "a", "b")):
            with self.subTest(args=args):
                self.assertEqual(self.run_main(*args).returncode, 2)


class TestBuildFolderIgnored(unittest.TestCase):

    def test_build_folder_is_git_ignored(self):
        """Git ignores .claude-build/ in this repo."""
        result = subprocess.run(["git", "check-ignore", "-q", ".claude-build/marketplace.json"],
                                cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 0)


@unittest.skipUnless(shutil.which("claude"), "Claude Code is not installed")
class TestRealTree(unittest.TestCase):
    """This repo's own ais/ and ais-max/, built and checked with the real Claude Code."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)
        self.dest = self.work / ".claude-build"

    def test_built_tree_passes_the_check(self):
        """The tree built from this repo passes every rule, Claude Code's strict validation included."""
        build_tree("1.0.0", dest=self.dest)
        self.assertEqual(check_tree(self.dest), [])

    def test_built_tree_holds_every_skill(self):
        """Every skill folder in ais/ and ais-max/ is in the built tree."""
        written = build_tree("1.0.0", dest=self.dest)
        for plugin in ("ais", "ais-max"):
            with self.subTest(plugin=plugin):
                expected = sorted(p.name for p in (ROOT / plugin).iterdir()
                                  if p.is_dir() and not p.name.startswith("."))
                self.assertEqual(written[plugin], expected)


if __name__ == "__main__":
    unittest.main()
