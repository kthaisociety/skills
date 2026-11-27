"""Acceptance tests for #7: scripts/build-codex.py builds and checks the ais-codex tree.

Most tests build from fake ais/ and ais-max/ folders in a temp folder. The
TestRealSources and TestMain tests read the ais/ and ais-max/ committed in
this repo.
"""

import contextlib
import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build-codex.py"
spec = importlib.util.spec_from_file_location("build_codex", SCRIPT)
build_codex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_codex)

build_tree = build_codex.build_tree
skill_owners = build_codex.skill_owners
check_tree = build_codex.check_tree
main = build_codex.main
BuildError = build_codex.BuildError

POLICY = b"policy:\n  allow_implicit_invocation: false\n"
MARKETPLACE = Path(".agents/plugins/marketplace.json")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def skill_md(name, extra="", body=""):
    return f"---\nname: {name}\ndescription: The {name} skill.\n{extra}---\n\n{body}"


def build_sources(work):
    """Write fake ais/ and ais-max/ source folders under work. Returns (ais, ais_max)."""
    ais = work / "ais"
    ais_max = work / "ais-max"
    write(ais / "new-ticket" / "SKILL.md", skill_md(
        "new-ticket", extra="disable-model-invocation: true\n",
        body="Run /grill-docs first. Read ../grill-docs/FORMAT.md.\n"
             "Keep — this dash and “these quotes”.\n"))
    write(ais / "grill-docs" / "SKILL.md", skill_md("grill-docs", body="Grill the user.\n"))
    write(ais / "grill-docs" / "FORMAT.md", "Then hand back to /new-ticket.\n")
    write(ais / "grill-docs" / "LICENSE", b"\x00\x01binary licence\xff")
    write(ais_max / "architect-ticket" / "SKILL.md", skill_md(
        "architect-ticket",
        extra="disable-model-invocation: false\nuser-invocable: true\ncontext: fork\n"
              "agent: general-purpose\nmodel: opus\n",
        body="Point at /new-ticket. Then /architect-ticket again. "
             "Leave /not-a-skill alone. Read ../helper-skill/shapes.md.\n"))
    write(ais_max / "architect-ticket" / "notes.txt", "/new-ticket stays in a text file.\n")
    write(ais_max / "helper-skill" / "SKILL.md", skill_md("helper-skill"))
    write(ais_max / "helper-skill" / "shapes.md", "Shapes for /architect-ticket.\n")
    write(ais_max / "helper-skill" / ".hidden", "hidden file\n")
    write(ais_max / "helper-skill" / ".hidden-dir" / "inside.md", "hidden folder\n")
    write(ais_max / "helper-skill" / "deep" / ".also-hidden", "deep hidden\n")
    write(ais_max / ".source.json", '{"commit": "abc", "tag": "v2.1.0"}\n')
    write(ais_max / ".hidden-skill" / "SKILL.md", skill_md(".hidden-skill"))
    return ais, ais_max


def snapshot(folder):
    """Every file and folder under folder, hidden ones included, with file bytes."""
    if not folder.exists():
        return None
    return {str(p.relative_to(folder)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(folder.rglob("*"))}


def dumps(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


class WorkCase(unittest.TestCase):
    """A fresh work folder per test, holding fake ais/ and ais-max/ and a dest path."""

    def setUp(self):
        self._work_dir = tempfile.mkdtemp()
        self.work = Path(self._work_dir)
        self.ais, self.ais_max = build_sources(self.work)
        self.dest = self.work / "out" / "tree"
        self.scratch = self.work / "scratch"
        self.scratch.mkdir()
        self._old_tempdir = tempfile.tempdir
        tempfile.tempdir = str(self.scratch)

    def tearDown(self):
        tempfile.tempdir = self._old_tempdir
        shutil.rmtree(self._work_dir)

    def run_build(self, version="1.2.3"):
        return build_tree(version, ais=self.ais, ais_max=self.ais_max, dest=self.dest)

    def built(self, *parts):
        return self.dest.joinpath(*parts)

    def seed_dest(self):
        write(self.dest / "stale" / "file.md", "from an older build\n")


class TestBuildTreeWrites(WorkCase):

    def test_returns_sorted_skill_names_per_plugin(self):
        """build_tree returns each plugin's written skill folder names, sorted."""
        self.assertEqual(self.run_build(), {
            "ais": ["grill-docs", "new-ticket"],
            "ais-max": ["architect-ticket", "helper-skill"],
        })

    def test_removes_an_earlier_tree(self):
        """Whatever dest held before the build is gone after it."""
        self.seed_dest()
        self.run_build()
        self.assertFalse(self.built("stale").exists())

    def test_writes_the_marketplace_manifest(self):
        """The marketplace manifest names ais-codex and points at both plugin folders."""
        self.run_build()
        entry = lambda name: {
            "name": name,
            "source": {"source": "local", "path": f"./{name}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }
        expected = {
            "name": "ais-codex",
            "interface": {"displayName": "KTHAIS skills for Codex"},
            "plugins": [entry("ais"), entry("ais-max")],
        }
        self.assertEqual(self.built(MARKETPLACE).read_text(), dumps(expected))

    def test_marketplace_manifest_carries_no_version(self):
        """The version appears nowhere in the marketplace manifest."""
        self.run_build("7.8.9")
        self.assertNotIn("7.8.9", self.built(MARKETPLACE).read_text())

    def test_writes_each_plugin_manifest(self):
        """Each plugin manifest holds its name, the version, its description and the author."""
        self.run_build()
        for name in ("ais", "ais-max"):
            with self.subTest(plugin=name):
                expected = {
                    "name": name,
                    "version": "1.2.3",
                    "description": build_codex.DESCRIPTIONS[name],
                    "author": {"name": "KTHAIS"},
                }
                path = self.built(name, ".codex-plugin", "plugin.json")
                self.assertEqual(path.read_text(), dumps(expected))

    def test_keeps_non_ascii_in_json(self):
        """JSON files keep non-ASCII characters as written rather than escaping them."""
        original = build_codex.DESCRIPTIONS["ais"]
        build_codex.DESCRIPTIONS["ais"] = "Åstrand's skills"
        try:
            self.run_build()
        finally:
            build_codex.DESCRIPTIONS["ais"] = original
        self.assertIn("Åstrand", self.built("ais", ".codex-plugin", "plugin.json").read_text())

    def test_places_skills_flat_under_their_plugin(self):
        """Each skill lands at <plugin>/skills/<skill>/SKILL.md."""
        self.run_build()
        self.assertTrue(self.built("ais-max", "skills", "architect-ticket", "SKILL.md").is_file())

    def test_frontmatter_keeps_only_name_and_description(self):
        """Every frontmatter key other than name and description is dropped."""
        self.run_build()
        text = self.built("ais-max", "skills", "architect-ticket", "SKILL.md").read_text()
        self.assertTrue(text.startswith(
            "---\nname: architect-ticket\ndescription: The architect-ticket skill.\n---\n"))

    def test_rewrites_a_mention_of_a_skill_in_the_same_plugin(self):
        """A slash mention of a skill in the same plugin becomes $<plugin>:<skill>."""
        self.run_build()
        text = self.built("ais", "skills", "new-ticket", "SKILL.md").read_text()
        self.assertIn("Run $ais:grill-docs first.", text)

    def test_rewrites_a_mention_of_an_ais_skill_from_ais_max(self):
        """A slash mention of an ais skill inside ais-max takes the ais prefix."""
        self.run_build()
        text = self.built("ais-max", "skills", "architect-ticket", "SKILL.md").read_text()
        self.assertIn("Point at $ais:new-ticket.", text)

    def test_rewrites_a_mention_of_an_ais_max_skill_from_ais_max(self):
        """A slash mention of an ais-max skill inside ais-max takes the ais-max prefix."""
        self.run_build()
        text = self.built("ais-max", "skills", "architect-ticket", "SKILL.md").read_text()
        self.assertIn("Then $ais-max:architect-ticket again.", text)

    def test_leaves_a_mention_of_an_unknown_name(self):
        """A slash mention of a name that is no skill in either plugin stays as written."""
        self.run_build()
        text = self.built("ais-max", "skills", "architect-ticket", "SKILL.md").read_text()
        self.assertIn("Leave /not-a-skill alone.", text)

    def test_leaves_a_relative_path_through_a_skill_folder(self):
        """A ../<skill>/<file> path is not mistaken for a mention."""
        self.run_build()
        text = self.built("ais", "skills", "new-ticket", "SKILL.md").read_text()
        self.assertIn("Read ../grill-docs/FORMAT.md.", text)

    def test_rewrites_mentions_in_other_markdown_files(self):
        """Mentions in a .md file other than SKILL.md are rewritten too."""
        self.run_build()
        text = self.built("ais-max", "skills", "helper-skill", "shapes.md").read_text()
        self.assertEqual(text, "Shapes for $ais-max:architect-ticket.\n")

    def test_leaves_mentions_in_non_markdown_files(self):
        """A file that is not .md is copied byte for byte, mentions and all."""
        self.run_build()
        self.assertEqual(self.built("ais-max", "skills", "architect-ticket", "notes.txt").read_bytes(),
                         b"/new-ticket stays in a text file.\n")

    def test_copies_binary_files_byte_for_byte(self):
        """A binary file reaches the tree with its bytes unchanged."""
        self.run_build()
        self.assertEqual(self.built("ais", "skills", "grill-docs", "LICENSE").read_bytes(),
                         b"\x00\x01binary licence\xff")

    def test_keeps_dashes_and_curly_quotes(self):
        """The build leaves em dashes and curly quotes as written (ADR-0008)."""
        self.run_build()
        text = self.built("ais", "skills", "new-ticket", "SKILL.md").read_text()
        self.assertIn("Keep — this dash and “these quotes”.", text)

    def test_blocks_implicit_invocation_where_model_invocation_was_disabled(self):
        """A skill with disable-model-invocation: true gets the blocking agents/openai.yaml."""
        self.run_build()
        self.assertEqual(self.built("ais", "skills", "new-ticket", "agents", "openai.yaml").read_bytes(),
                         POLICY)

    def test_no_policy_file_where_model_invocation_is_allowed(self):
        """A skill without disable-model-invocation: true gets no agents/openai.yaml."""
        self.run_build()
        self.assertFalse(self.built("ais", "skills", "grill-docs", "agents").exists())

    def test_no_policy_file_where_model_invocation_is_set_false(self):
        """disable-model-invocation: false does not block implicit invocation."""
        self.run_build()
        self.assertFalse(self.built("ais-max", "skills", "architect-ticket", "agents").exists())

    def test_skips_hidden_files(self):
        """A file whose name starts with a dot never reaches the tree."""
        self.run_build()
        self.assertFalse(self.built("ais-max", "skills", "helper-skill", ".hidden").exists())

    def test_skips_hidden_folders(self):
        """A folder whose name starts with a dot never reaches the tree."""
        self.run_build()
        self.assertFalse(self.built("ais-max", "skills", "helper-skill", ".hidden-dir").exists())

    def test_skips_hidden_files_in_subfolders(self):
        """A dot file deeper in a skill never reaches the tree."""
        self.run_build()
        self.assertFalse(self.built("ais-max", "skills", "helper-skill", "deep", ".also-hidden").exists())

    def test_skips_hidden_skill_folders(self):
        """A dot-named folder at the top of a plugin is not a skill."""
        self.run_build()
        self.assertFalse(self.built("ais-max", "skills", ".hidden-skill").exists())

    def test_sync_record_never_reaches_the_tree(self):
        """ais-max/.source.json appears nowhere in the tree."""
        self.run_build()
        self.assertEqual(list(self.dest.rglob(".source.json")), [])

    def test_tree_holds_only_the_manifests_and_plugins(self):
        """The top of dest holds only .agents, ais and ais-max."""
        self.run_build()
        self.assertEqual(sorted(p.name for p in self.dest.iterdir()), [".agents", "ais", "ais-max"])

    def test_rerun_is_byte_identical(self):
        """Building twice with the same version and inputs leaves dest byte-identical."""
        self.run_build()
        first = snapshot(self.dest)
        self.run_build()
        self.assertEqual(snapshot(self.dest), first)

    def test_writes_nothing_outside_dest(self):
        """A build changes nothing in the work folder outside dest."""
        before = snapshot(self.work)
        self.run_build()
        after = {k: v for k, v in snapshot(self.work).items()
                 if not k.startswith("out")}
        self.assertEqual(after, {k: v for k, v in before.items() if not k.startswith("out")})

    def test_built_tree_passes_the_check(self):
        """check_tree finds nothing wrong with a tree build_tree wrote."""
        self.run_build()
        self.assertEqual(check_tree(self.dest), [])


class TestBuildTreeRefuses(WorkCase):

    def assert_refused(self, *needles, version="1.2.3"):
        self.seed_dest()
        before = snapshot(self.dest)
        with self.assertRaises(BuildError) as caught:
            self.run_build(version)
        self.assertEqual(snapshot(self.dest), before)
        message = str(caught.exception)
        self.assertNotIn("\n", message)
        for needle in needles:
            self.assertIn(needle, message)

    def test_refuses_a_version_with_a_v_prefix(self):
        """A version like v1.2.3 stops the build, naming the version, with dest untouched."""
        self.assert_refused("v1.2.3", version="v1.2.3")

    def test_refuses_a_version_with_two_parts(self):
        """A version like 1.2 stops the build."""
        self.assert_refused("1.2", version="1.2")

    def test_refuses_a_version_with_a_suffix(self):
        """A version like 1.2.3-rc1 stops the build."""
        self.assert_refused("1.2.3-rc1", version="1.2.3-rc1")

    def test_refuses_an_empty_version(self):
        """An empty version stops the build."""
        self.assert_refused(version="")

    def test_checks_the_version_before_reading_sources(self):
        """A bad version is reported even when the source folders are missing."""
        shutil.rmtree(self.ais)
        self.assert_refused("1.x.3", version="1.x.3")

    def test_refuses_a_missing_ais_folder(self):
        """A missing ais folder stops the build, naming the path."""
        shutil.rmtree(self.ais)
        self.assert_refused(str(self.ais))

    def test_refuses_a_missing_ais_max_folder(self):
        """A missing ais-max folder stops the build, naming the path."""
        shutil.rmtree(self.ais_max)
        self.assert_refused(str(self.ais_max))

    def test_refuses_a_skill_in_both_plugins(self):
        """A skill name found in both plugins stops the build, naming it."""
        write(self.ais_max / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        self.assert_refused("grill-docs")

    def test_refuses_a_reference_into_the_other_plugin(self):
        """A ../<skill>/<file> reference into the other plugin stops the build."""
        write(self.ais_max / "helper-skill" / "cross.md", "See ../grill-docs/FORMAT.md.\n")
        self.assert_refused("../grill-docs/FORMAT.md", "cross.md")

    def test_refuses_a_reference_to_a_missing_file(self):
        """A ../<skill>/<file> reference to a file that doesn't exist stops the build."""
        write(self.ais_max / "helper-skill" / "broken.md", "See ../architect-ticket/gone.md.\n")
        self.assert_refused("../architect-ticket/gone.md", "broken.md")

    def test_refuses_a_reference_to_a_missing_skill(self):
        """A ../<skill>/<file> reference to a skill in neither plugin stops the build."""
        write(self.ais / "new-ticket" / "ghost.md", "See ../ghost/file.md.\n")
        self.assert_refused("../ghost/file.md", "ghost.md")


class TestSkillOwners(WorkCase):

    def owners(self):
        return skill_owners(ais=self.ais, ais_max=self.ais_max)

    def test_maps_each_skill_to_its_plugin(self):
        """Each skill folder maps to the plugin that holds it."""
        self.assertEqual(self.owners(), {
            "grill-docs": "ais", "new-ticket": "ais",
            "architect-ticket": "ais-max", "helper-skill": "ais-max",
        })

    def test_orders_by_plugin_then_skill_name(self):
        """The lookup lists ais skills first, each plugin's sorted by name."""
        self.assertEqual(list(self.owners()),
                         ["grill-docs", "new-ticket", "architect-ticket", "helper-skill"])

    def test_skips_hidden_folders_and_loose_files(self):
        """Dot-named folders and loose files are not skills."""
        self.assertNotIn(".hidden-skill", self.owners())

    def test_refuses_a_skill_in_both_plugins(self):
        """A name in both plugins raises BuildError naming the skill and both plugins."""
        write(self.ais_max / "new-ticket" / "SKILL.md", skill_md("new-ticket"))
        with self.assertRaises(BuildError) as caught:
            self.owners()
        message = str(caught.exception)
        for needle in ("new-ticket", "ais", "ais-max"):
            with self.subTest(needle=needle):
                self.assertIn(needle, message)

    def test_names_the_first_clash_in_sorted_order(self):
        """With several clashing names, the message names the first in sorted order."""
        write(self.ais_max / "new-ticket" / "SKILL.md", skill_md("new-ticket"))
        write(self.ais_max / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        with self.assertRaises(BuildError) as caught:
            self.owners()
        self.assertIn("grill-docs", str(caught.exception))

    def test_refuses_a_missing_plugin_folder(self):
        """A missing plugin folder raises BuildError naming the path."""
        shutil.rmtree(self.ais_max)
        with self.assertRaises(BuildError) as caught:
            self.owners()
        self.assertIn(str(self.ais_max), str(caught.exception))


def valid_tree(tree, version="1.2.3"):
    """Write by hand a tree that passes every rule check_tree has."""
    entry = lambda name: {
        "name": name,
        "source": {"source": "local", "path": f"./{name}"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Productivity",
    }
    write(tree / MARKETPLACE, dumps({
        "name": "ais-codex",
        "interface": {"displayName": "KTHAIS skills for Codex"},
        "plugins": [entry("ais"), entry("ais-max")],
    }))
    for name in ("ais", "ais-max"):
        write(tree / name / ".codex-plugin" / "plugin.json", dumps({
            "name": name, "version": version,
            "description": f"The {name} plugin.", "author": {"name": "KTHAIS"},
        }))
    write(tree / "ais" / "skills" / "new-ticket" / "SKILL.md", skill_md(
        "new-ticket", body="Run $ais:grill-docs. Read ../grill-docs/FORMAT.md.\n"))
    write(tree / "ais" / "skills" / "new-ticket" / "agents" / "openai.yaml", POLICY)
    write(tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
    write(tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "Format.\n")
    write(tree / "ais-max" / "skills" / "architect-ticket" / "SKILL.md", skill_md(
        "architect-ticket", body="Point at $ais:new-ticket. Leave /not-a-skill.\n"))


class CheckCase(unittest.TestCase):

    def setUp(self):
        self._work_dir = tempfile.mkdtemp()
        self.tree = Path(self._work_dir) / "tree"
        valid_tree(self.tree)

    def tearDown(self):
        shutil.rmtree(self._work_dir)

    def edit_json(self, relative, change):
        path = self.tree / relative
        data = json.loads(path.read_text())
        change(data)
        path.write_text(dumps(data))

    def assert_one_message(self, prefix):
        """check_tree returns exactly one message, starting with prefix and ': '."""
        messages = check_tree(self.tree)
        self.assertEqual(len(messages), 1, messages)
        self.assertTrue(messages[0].startswith(f"{prefix}: "), messages[0])


class TestCheckTree(CheckCase):

    def test_passes_a_valid_tree(self):
        """A tree that keeps every rule gets no messages."""
        self.assertEqual(check_tree(self.tree), [])

    def test_never_writes_to_the_tree(self):
        """check_tree leaves the tree byte-identical, even when it finds problems."""
        (self.tree / "ais" / ".codex-plugin" / "plugin.json").unlink()
        before = snapshot(self.tree)
        check_tree(self.tree)
        self.assertEqual(snapshot(self.tree), before)

    def test_reports_a_missing_tree_once(self):
        """A tree path that is no folder gets exactly one message."""
        self.assertEqual(len(check_tree(self.tree / "nowhere")), 1)

    def test_reports_a_missing_marketplace(self):
        """A tree without the marketplace manifest is reported against that file."""
        (self.tree / MARKETPLACE).unlink()
        self.assertTrue(any(m.startswith(f"{MARKETPLACE.as_posix()}: ")
                            for m in check_tree(self.tree)))

    def test_reports_a_marketplace_that_is_not_json(self):
        """A marketplace manifest that isn't a JSON object is reported."""
        (self.tree / MARKETPLACE).write_text("[not an object")
        self.assertTrue(any(m.startswith(f"{MARKETPLACE.as_posix()}: ")
                            for m in check_tree(self.tree)))

    def test_reports_a_wrong_marketplace_name(self):
        """A marketplace named other than ais-codex is reported."""
        self.edit_json(MARKETPLACE, lambda d: d.update(name="other"))
        self.assert_one_message(MARKETPLACE.as_posix())

    def test_reports_a_missing_plugin_entry(self):
        """A marketplace that doesn't list ais-max is reported."""
        self.edit_json(MARKETPLACE, lambda d: d["plugins"].pop())
        self.assertTrue(any(m.startswith(f"{MARKETPLACE.as_posix()}: ")
                            for m in check_tree(self.tree)))

    def test_reports_a_plugin_listed_twice(self):
        """A marketplace that lists ais twice is reported."""
        self.edit_json(MARKETPLACE, lambda d: d["plugins"].append(d["plugins"][0]))
        self.assert_one_message(MARKETPLACE.as_posix())

    def test_reports_an_unknown_plugin_entry(self):
        """A marketplace that lists a plugin outside PLUGINS is reported."""
        self.edit_json(MARKETPLACE, lambda d: d["plugins"].append(dict(d["plugins"][0], name="extra")))
        self.assertTrue(any(m.startswith(f"{MARKETPLACE.as_posix()}: ")
                            for m in check_tree(self.tree)))

    def test_reports_a_wrong_source_path(self):
        """A plugin entry whose source path isn't ./<name> is reported."""
        self.edit_json(MARKETPLACE, lambda d: d["plugins"][0]["source"].update(path="./plugins/ais"))
        self.assertTrue(any(m.startswith(f"{MARKETPLACE.as_posix()}: ")
                            for m in check_tree(self.tree)))

    def test_reports_a_missing_plugin_folder(self):
        """A listed plugin whose folder is missing from the tree is reported."""
        shutil.rmtree(self.tree / "ais-max")
        self.assertTrue(any("ais-max" in m for m in check_tree(self.tree)))

    def test_reports_a_missing_plugin_manifest(self):
        """A plugin without .codex-plugin/plugin.json is reported against that file."""
        (self.tree / "ais" / ".codex-plugin" / "plugin.json").unlink()
        self.assert_one_message("ais/.codex-plugin/plugin.json")

    def test_reports_a_plugin_manifest_that_is_not_json(self):
        """A plugin manifest that isn't a JSON object is reported."""
        (self.tree / "ais" / ".codex-plugin" / "plugin.json").write_text("{")
        self.assertTrue(any(m.startswith("ais/.codex-plugin/plugin.json: ")
                            for m in check_tree(self.tree)))

    def test_reports_a_wrong_plugin_name(self):
        """A plugin manifest whose name doesn't match its plugin is reported."""
        self.edit_json("ais-max/.codex-plugin/plugin.json", lambda d: d.update(name="max"))
        self.assert_one_message("ais-max/.codex-plugin/plugin.json")

    def test_reports_an_empty_plugin_description(self):
        """A plugin manifest with an empty description is reported."""
        self.edit_json("ais/.codex-plugin/plugin.json", lambda d: d.update(description=""))
        self.assert_one_message("ais/.codex-plugin/plugin.json")

    def test_reports_a_malformed_version(self):
        """A plugin version that isn't X.Y.Z is reported."""
        self.edit_json("ais/.codex-plugin/plugin.json", lambda d: d.update(version="v1.2.3"))
        self.assertTrue(any(m.startswith("ais/.codex-plugin/plugin.json: ")
                            for m in check_tree(self.tree)))

    def test_reports_versions_that_differ(self):
        """Two plugin manifests with different versions are reported."""
        self.edit_json("ais-max/.codex-plugin/plugin.json", lambda d: d.update(version="1.2.4"))
        self.assertEqual(len(check_tree(self.tree)), 1)

    def test_reports_a_hidden_file_in_a_skill(self):
        """A dot-named file under a plugin's skills folder is reported."""
        write(self.tree / "ais-max" / "skills" / "architect-ticket" / ".source.json", "{}\n")
        self.assert_one_message("ais-max/skills/architect-ticket/.source.json")

    def test_reports_a_skill_without_skill_md(self):
        """A skill folder with no SKILL.md is reported."""
        write(self.tree / "ais-max" / "skills" / "empty" / "notes.md", "No skill file.\n")
        self.assertTrue(any(m.startswith("ais-max/skills/empty") for m in check_tree(self.tree)))

    def test_reports_an_extra_frontmatter_key(self):
        """A SKILL.md frontmatter with a key other than name and description is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md",
              skill_md("grill-docs", extra="disable-model-invocation: true\n"))
        self.assert_one_message("ais/skills/grill-docs/SKILL.md")

    def test_reports_a_name_that_differs_from_the_folder(self):
        """A SKILL.md whose name doesn't match its folder is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill"))
        self.assert_one_message("ais/skills/grill-docs/SKILL.md")

    def test_reports_an_empty_skill_description(self):
        """A SKILL.md with an empty description is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md",
              "---\nname: grill-docs\ndescription:\n---\n")
        self.assert_one_message("ais/skills/grill-docs/SKILL.md")

    def test_reports_a_skill_in_both_plugins_once(self):
        """A skill name under both plugins is one message naming the skill and both plugins."""
        write(self.tree / "ais-max" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill-docs"))
        messages = check_tree(self.tree)
        clashes = [m for m in messages if "grill-docs" in m and "ais-max" in m]
        self.assertEqual(len(clashes), 1, messages)

    def test_reports_a_slash_mention_of_a_skill(self):
        """A /<skill> mention left in a .md file is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "Back to /new-ticket.\n")
        self.assert_one_message("ais/skills/grill-docs/FORMAT.md")

    def test_ignores_a_slash_mention_of_an_unknown_name(self):
        """A /<word> that names no skill in the tree is no problem."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "See /usr/bin and /help.\n")
        self.assertEqual(check_tree(self.tree), [])

    def test_reports_a_mention_with_the_wrong_plugin(self):
        """A $ais-max:<skill> mention of a skill ais holds is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "Back to $ais-max:new-ticket.\n")
        self.assert_one_message("ais/skills/grill-docs/FORMAT.md")

    def test_reports_a_mention_of_an_unknown_plugin(self):
        """A $<plugin>:<skill> mention naming a plugin outside PLUGINS is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "Back to $max:new-ticket.\n")
        self.assert_one_message("ais/skills/grill-docs/FORMAT.md")

    def test_reports_a_mention_of_a_missing_skill(self):
        """A $ais:<skill> mention of a skill not in the tree is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "Back to $ais:ghost.\n")
        self.assert_one_message("ais/skills/grill-docs/FORMAT.md")

    def test_reports_a_reference_to_a_missing_file(self):
        """A ../<skill>/<file> reference to a file not in the tree is reported."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "FORMAT.md", "See ../new-ticket/gone.md.\n")
        self.assert_one_message("ais/skills/grill-docs/FORMAT.md")

    def test_reports_a_reference_into_the_other_plugin(self):
        """A ../<skill>/<file> reference to a skill under the other plugin is reported."""
        write(self.tree / "ais-max" / "skills" / "architect-ticket" / "ref.md",
              "See ../grill-docs/FORMAT.md.\n")
        self.assert_one_message("ais-max/skills/architect-ticket/ref.md")

    def test_reports_a_wrong_policy_file(self):
        """An agents/openai.yaml that doesn't hold exactly the blocking policy is reported."""
        write(self.tree / "ais" / "skills" / "new-ticket" / "agents" / "openai.yaml",
              "policy:\n  allow_implicit_invocation: true\n")
        self.assert_one_message("ais/skills/new-ticket/agents/openai.yaml")

    def test_reports_every_broken_rule(self):
        """Two separate problems give two messages."""
        self.edit_json(MARKETPLACE, lambda d: d.update(name="other"))
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill"))
        self.assertEqual(len(check_tree(self.tree)), 2)

    def test_orders_marketplace_then_manifests_then_skills(self):
        """Marketplace messages come before plugin manifest messages, then skill messages."""
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill"))
        self.edit_json("ais-max/.codex-plugin/plugin.json", lambda d: d.update(name="max"))
        self.edit_json(MARKETPLACE, lambda d: d.update(name="other"))
        prefixes = [m.split(": ", 1)[0] for m in check_tree(self.tree)]
        self.assertEqual(prefixes, [MARKETPLACE.as_posix(), "ais-max/.codex-plugin/plugin.json",
                                    "ais/skills/grill-docs/SKILL.md"])

    def test_orders_skills_by_plugin_then_name(self):
        """Skill messages come in plugin order, then skill folder name."""
        write(self.tree / "ais-max" / "skills" / "architect-ticket" / "SKILL.md", skill_md("arch"))
        write(self.tree / "ais" / "skills" / "new-ticket" / "SKILL.md", skill_md("new"))
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill"))
        prefixes = [m.split(": ", 1)[0] for m in check_tree(self.tree)]
        self.assertEqual(prefixes, ["ais/skills/grill-docs/SKILL.md", "ais/skills/new-ticket/SKILL.md",
                                    "ais-max/skills/architect-ticket/SKILL.md"])

    def test_messages_are_single_lines(self):
        """No message holds a newline."""
        (self.tree / "ais" / ".codex-plugin" / "plugin.json").write_text("{")
        write(self.tree / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill"))
        self.assertTrue(all("\n" not in m for m in check_tree(self.tree)))


class TestRealSources(unittest.TestCase):
    """Build from the ais/ and ais-max/ committed in this repo."""

    @classmethod
    def setUpClass(cls):
        cls._work_dir = tempfile.mkdtemp()
        cls.dest = Path(cls._work_dir) / "tree"
        build_tree("1.0.0", dest=cls.dest)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._work_dir)

    def test_real_tree_passes_the_check(self):
        """The tree built from this repo's skills breaks no rule."""
        self.assertEqual(check_tree(self.dest), [])

    def test_ais_max_mentions_an_ais_skill_with_the_ais_prefix(self):
        """brainstorming in ais-max mentions new-ticket as $ais:new-ticket."""
        text = (self.dest / "ais-max" / "skills" / "brainstorming" / "SKILL.md").read_text()
        self.assertIn("$ais:new-ticket", text)


class TestMain(unittest.TestCase):

    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_build_exits_zero(self):
        """build with a good version exits 0."""
        self.assertEqual(self.run_main("build", "1.0.0")[0], 0)

    def test_build_prints_one_line_per_plugin(self):
        """build prints how many skills it wrote for each plugin, in PLUGINS order."""
        owners = skill_owners()
        counts = {p: sum(1 for o in owners.values() if o == p) for p in ("ais", "ais-max")}
        _, out, _ = self.run_main("build", "1.0.0")
        self.assertEqual(out, f"Wrote {counts['ais']} skills to .codex-build/ais\n"
                              f"Wrote {counts['ais-max']} skills to .codex-build/ais-max\n")

    def test_build_with_a_bad_version_exits_one(self):
        """build with a bad version exits 1."""
        self.assertEqual(self.run_main("build", "v1.0.0")[0], 1)

    def test_build_with_a_bad_version_prints_an_error(self):
        """build with a bad version prints one error line to stderr."""
        _, _, err = self.run_main("build", "v1.0.0")
        self.assertRegex(err, r"\Aerror: [^\n]+\n\Z")

    def test_check_of_a_good_tree_exits_zero(self):
        """check on a valid tree exits 0."""
        with tempfile.TemporaryDirectory() as work:
            valid_tree(Path(work))
            self.assertEqual(self.run_main("check", work)[0], 0)

    def test_check_of_a_good_tree_prints_passes(self):
        """check on a valid tree prints Tree passes."""
        with tempfile.TemporaryDirectory() as work:
            valid_tree(Path(work))
            self.assertEqual(self.run_main("check", work)[1], "Tree passes\n")

    def test_check_of_a_bad_tree_exits_one(self):
        """check on a broken tree exits 1."""
        with tempfile.TemporaryDirectory() as work:
            valid_tree(Path(work))
            (Path(work) / MARKETPLACE).unlink()
            self.assertEqual(self.run_main("check", work)[0], 1)

    def test_check_of_a_bad_tree_prints_each_message(self):
        """check on a broken tree prints each message on its own line to stderr."""
        with tempfile.TemporaryDirectory() as work:
            valid_tree(Path(work))
            write(Path(work) / "ais" / "skills" / "grill-docs" / "SKILL.md", skill_md("grill"))
            expected = "".join(m + "\n" for m in check_tree(Path(work)))
            self.assertEqual(self.run_main("check", work)[2], expected)

    def test_check_defaults_to_the_build_folder(self):
        """check with no tree checks the build folder that build wrote."""
        self.run_main("build", "1.0.0")
        self.assertEqual(self.run_main("check")[0], 0)

    def test_no_subcommand_exits_two(self):
        """No arguments exits 2."""
        self.assertEqual(self.run_main()[0], 2)

    def test_unknown_subcommand_exits_two(self):
        """An unknown subcommand exits 2."""
        self.assertEqual(self.run_main("publish")[0], 2)

    def test_build_without_a_version_exits_two(self):
        """build without a version exits 2."""
        self.assertEqual(self.run_main("build")[0], 2)

    def test_check_with_two_trees_exits_two(self):
        """check with more than one tree exits 2."""
        self.assertEqual(self.run_main("check", "a", "b")[0], 2)


if __name__ == "__main__":
    unittest.main()
