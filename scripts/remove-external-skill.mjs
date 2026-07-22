// scripts/remove-external-skill.mjs
import {
  existsSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { join, resolve } from "node:path";

const skillName = parseSkillName(process.argv.slice(2));

if (!skillName) {
  console.error(
    [
      "Usage:",
      "  npm run skill:remove -- <skill-name>",
      "  npm run skill:remove -- --skill <skill-name>",
    ].join("\n"),
  );
  process.exit(1);
}

const root = resolve(import.meta.dirname, "..");
const manifestPath = join(root, "sources.json");
const skillsShPath = join(root, "skills.sh.json");

if (!existsSync(manifestPath)) {
  throw new Error("sources.json not found");
}

const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const entry = manifest.skills.find((skill) => skill.name === skillName);

if (!entry) {
  console.error(`No external skill named "${skillName}" in sources.json`);
  process.exit(1);
}

const destinationPath = join(root, entry.destination);

rmSync(destinationPath, { recursive: true, force: true });

manifest.skills = manifest.skills
  .filter((skill) => skill.name !== skillName)
  .sort((a, b) => a.name.localeCompare(b.name));

writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`);

if (existsSync(skillsShPath)) {
  const skillsSh = JSON.parse(readFileSync(skillsShPath, "utf8"));

  if (Array.isArray(skillsSh.groupings)) {
    skillsSh.groupings = skillsSh.groupings
      .map((group) => ({
        ...group,
        skills: (group.skills ?? []).filter((name) => name !== skillName),
      }))
      .filter((group) => group.skills.length > 0);

    writeFileSync(skillsShPath, `${JSON.stringify(skillsSh, null, 2)}\n`);
  }
}

console.log(`Removed external skill "${skillName}" (${entry.destination})`);

function parseSkillName(args) {
  const positionals = [];

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];

    if (arg === "--skill" || arg === "-s") {
      return args[++i];
    }

    if (arg.startsWith("--skill=")) {
      return arg.slice("--skill=".length);
    }

    if (arg.startsWith("-")) {
      throw new Error(`Unknown option: ${arg}`);
    }

    positionals.push(arg);
  }

  return positionals[0];
}
