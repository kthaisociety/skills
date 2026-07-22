// scripts/sync-external-skills.mjs
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

const checkOnly = process.argv.includes("--check");
const root = resolve(import.meta.dirname, "..");
const manifestPath = join(root, "sources.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

let hasUpdates = false;

for (const skill of manifest.skills) {
  const temporaryDirectory = mkdtempSync(join(tmpdir(), "kthais-skills-"));

  try {
    execFileSync(
      "git",
      [
        "clone",
        "--depth",
        "1",
        `https://github.com/${skill.repository}.git`,
        temporaryDirectory,
      ],
      { stdio: "ignore" },
    );

    const latestCommit = execFileSync(
      "git",
      ["-C", temporaryDirectory, "rev-parse", "HEAD"],
      { encoding: "utf8" },
    ).trim();

    if (latestCommit === skill.commit) {
      console.log(`✓ ${skill.name} is current`);
      continue;
    }

    hasUpdates = true;
    console.log(
      `↑ ${skill.name}: ${skill.commit.slice(0, 8)} -> ${latestCommit.slice(0, 8)}`,
    );

    if (checkOnly) {
      continue;
    }

    const sourcePath = join(temporaryDirectory, skill.path);
    const destinationPath = join(root, skill.destination);

    if (!existsSync(join(sourcePath, "SKILL.md"))) {
      throw new Error(
        `Missing SKILL.md for ${skill.name} at ${skill.path}`,
      );
    }

    rmSync(destinationPath, { recursive: true, force: true });
    cpSync(sourcePath, destinationPath, { recursive: true });

    skill.commit = latestCommit;
  } finally {
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
}

if (!checkOnly) {
  writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);
}

if (checkOnly && hasUpdates) {
  process.exitCode = 1;
}
