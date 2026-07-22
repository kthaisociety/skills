// scripts/add-external-skill.mjs
import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const { repositoryArg, skillName, sourcePathArg } = parseArgs(
  process.argv.slice(2),
);

if (!repositoryArg || !skillName) {
  console.error(
    [
      "Usage:",
      "  npm run skill:add -- <owner/repo|github-url> <skill-name> [source-path]",
      "  npm run skill:add -- <owner/repo|github-url> --skill <skill-name>",
    ].join("\n"),
  );
  process.exit(1);
}

const repository = normalizeRepository(repositoryArg);
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

  const relativePath =
    sourcePathArg ?? relativeToRepository(temporaryDirectory, sourcePath);

  const entry = {
    name: skillName,
    repository,
    path: relativePath,
    destination,
    commit,
  };

  manifest.skills = [
    ...manifest.skills.filter((skill) => skill.name !== skillName),
    entry,
  ].sort((a, b) => a.name.localeCompare(b.name));

  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

  console.log(
    `Added ${skillName} from ${repository} (${relativePath}) at ${commit.slice(0, 8)}`,
  );
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}

function parseArgs(args) {
  let repositoryArg;
  let skillName;
  let sourcePathArg;
  const positionals = [];

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];

    if (arg === "--skill" || arg === "-s") {
      skillName = args[++i];
      continue;
    }

    if (arg.startsWith("--skill=")) {
      skillName = arg.slice("--skill=".length);
      continue;
    }

    if (arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}`);
    }

    positionals.push(arg);
  }

  repositoryArg = positionals[0];
  skillName ??= positionals[1];
  sourcePathArg = positionals[2];

  return { repositoryArg, skillName, sourcePathArg };
}

function normalizeRepository(value) {
  const trimmed = value.trim().replace(/\.git$/, "");
  const githubMatch = trimmed.match(
    /^(?:https?:\/\/)?(?:www\.)?github\.com\/([^/]+\/[^/]+?)(?:\/.*)?$/i,
  );

  if (githubMatch) {
    return githubMatch[1];
  }

  if (/^[^/]+\/[^/]+$/.test(trimmed)) {
    return trimmed;
  }

  throw new Error(
    `Invalid repository "${value}". Use owner/repo or a GitHub URL.`,
  );
}

function findSkillDirectory(repositoryRoot, name) {
  const preferred = [
    join(repositoryRoot, "skills", name),
    join(repositoryRoot, name),
  ];

  for (const candidate of preferred) {
    if (existsSync(join(candidate, "SKILL.md"))) {
      return candidate;
    }
  }

  const matches = [];
  const skillsRoot = join(repositoryRoot, "skills");

  if (existsSync(skillsRoot)) {
    walkForSkill(skillsRoot, name, matches);
  }

  if (matches.length === 0) {
    walkForSkill(repositoryRoot, name, matches);
  }

  if (matches.length === 0) {
    return undefined;
  }

  matches.sort((a, b) => {
    // Prefer exact folder-name matches over frontmatter-only matches.
    if (a.byFolder !== b.byFolder) {
      return a.byFolder ? -1 : 1;
    }

    // Prefer skills living under a skills/ directory.
    if (a.underSkills !== b.underSkills) {
      return a.underSkills ? -1 : 1;
    }

    return a.depth - b.depth || a.path.localeCompare(b.path);
  });

  return matches[0].path;
}

function walkForSkill(directory, name, matches, depth = 0) {
  let entries;

  try {
    entries = readdirSync(directory);
  } catch {
    return;
  }

  for (const entry of entries) {
    if (
      entry === ".git" ||
      entry === "node_modules" ||
      entry === "examples" ||
      entry === "evals" ||
      entry === "docs" ||
      entry === ".next" ||
      entry === "dist"
    ) {
      continue;
    }

    const fullPath = join(directory, entry);
    let stats;

    try {
      stats = statSync(fullPath);
    } catch {
      continue;
    }

    if (!stats.isDirectory()) {
      continue;
    }

    const skillMdPath = join(fullPath, "SKILL.md");

    if (existsSync(skillMdPath)) {
      const byFolder = entry === name;
      const byFrontmatter = frontmatterName(skillMdPath) === name;

      if (byFolder || byFrontmatter) {
        matches.push({
          path: fullPath,
          depth,
          byFolder,
          underSkills: /(?:^|[\\/])skills[\\/]/.test(fullPath),
        });
      }
    }

    // Bound depth so huge repos stay cheap; skills are usually shallow.
    if (depth < 6) {
      walkForSkill(fullPath, name, matches, depth + 1);
    }
  }
}

function frontmatterName(skillMdPath) {
  try {
    const contents = readFileSync(skillMdPath, "utf8");
    const match = contents.match(/^---\r?\n([\s\S]*?)\r?\n---/);

    if (!match) {
      return undefined;
    }

    const nameMatch = match[1].match(/^name:\s*["']?([^\n"']+)["']?\s*$/m);
    return nameMatch?.[1]?.trim();
  } catch {
    return undefined;
  }
}

function relativeToRepository(repositoryRoot, path) {
  return path.slice(repositoryRoot.length + 1);
}
