// scripts/add-external-skill.mjs
import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const [, , repository, skillName, sourcePathArg] = process.argv;

if (!repository || !skillName) {
  console.error(
    "Usage: npm run skill:add -- <owner/repo> <skill-name> [source-path]",
  );
  process.exit(1);
}

const root = resolve(import.meta.dirname, "..");
const manifestPath = join(root, "sources.json");
const destination = `skills/external/${skillName}`;
const destinationPath = join(root, destination);
const temporaryDirectory = mkdtempSync(join(tmpdir(), "kthais-skills-"));

try {
  execFileSync(
    "git",
    [
      "clone",
      "--depth",
      "1",
      `https://github.com/${repository}.git`,
      temporaryDirectory,
    ],
    { stdio: "inherit" },
  );

  const sourcePath = sourcePathArg
    ? join(temporaryDirectory, sourcePathArg)
    : findSkillDirectory(temporaryDirectory, skillName);

  if (!sourcePath || !existsSync(join(sourcePath, "SKILL.md"))) {
    throw new Error(`Could not find skill "${skillName}" in ${repository}`);
  }

  rmSync(destinationPath, { recursive: true, force: true });
  cpSync(sourcePath, destinationPath, { recursive: true });

  const commit = execFileSync(
    "git",
    ["-C", temporaryDirectory, "rev-parse", "HEAD"],
    { encoding: "utf8" },
  ).trim();

  const manifest = existsSync(manifestPath)
    ? JSON.parse(readFileSync(manifestPath, "utf8"))
    : { skills: [] };

  const entry = {
    name: skillName,
    repository,
    path: sourcePathArg ?? relativeToRepository(temporaryDirectory, sourcePath),
    destination,
    commit,
  };

  manifest.skills = [
    ...manifest.skills.filter((skill) => skill.name !== skillName),
    entry,
  ].sort((a, b) => a.name.localeCompare(b.name));

  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

  console.log(`Added ${skillName} from ${repository} at ${commit.slice(0, 8)}`);
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}

function findSkillDirectory(repositoryRoot, name) {
  const candidates = [
    join(repositoryRoot, "skills", name),
    join(repositoryRoot, name),
  ];

  return candidates.find((candidate) =>
    existsSync(join(candidate, "SKILL.md")),
  );
}

function relativeToRepository(repositoryRoot, path) {
  return path.slice(repositoryRoot.length + 1);
}
