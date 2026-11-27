#!/usr/bin/env bash
# Copy the ais or ais-max skills from this clone into one coding agent's
# skills folder. For developers only: members install the plugins from the
# release repos (ADR-0004). Copies, never symlinks (ADR-0013).
#
# Usage: ./install.sh [--yes] [AGENT] [PLUGIN]
#
#   AGENT    claude   Claude Code   ~/.claude/skills
#            agy      Antigravity   ~/.gemini/config/skills
#            codex    Codex         ~/.agents/skills
#   PLUGIN   ais      every skill in ais/
#            ais-max  every skill in ais-max/, and every skill in ais/ too,
#                     since ais-max needs ais
#   --yes    apply the plan without asking. Flags may come before, between
#            or after AGENT and PLUGIN.
#   -h, --help  print this usage to stdout and exit 0
#
# Every folder is resolved from $HOME, so pointing HOME elsewhere moves all
# three targets.
#
# Ownership. Every skill folder this script writes holds a file named
# .ais-install. A folder in the agent's skills folder is "ours" when it holds
# that file, whichever clone wrote it, and is never ours otherwise. The script
# only ever replaces or removes folders that are ours.
#
# A run, in order:
#   1. Missing AGENT or PLUGIN: on a terminal (stdin and stdout both ttys) it
#      asks for the agent, then the plugin. Each prompt takes the name or its
#      number in the list, and asks again on anything else. Without a
#      terminal it prints this usage to stderr and exits 1.
#   2. Reads every skill folder directly inside the chosen plugin folders,
#      skipping names that start with ".". A skill whose SKILL.md is missing,
#      or whose frontmatter lacks a name or a description, or whose name
#      differs from its folder name, is reported on stderr as
#      "error: <plugin>/<skill>: <what is wrong>" and not copied.
#   3. For codex only, runs `python3 scripts/build-codex.py local` and copies
#      from .codex-local/<skill> instead of the plugin folder. When python3 is
#      missing or the build fails, it prints why on stderr, writes nothing
#      and exits 1.
#   4. Prints the plan, one line per folder, adds first, then updates, then
#      removals, each group sorted by skill name:
#        "  + <skill>"   no folder of that name yet, will be copied
#        "  ~ <skill>"   ours, will be replaced by a fresh copy
#        "  - <skill>"   ours, but no folder of that name exists in ais/ or
#                        ais-max/ of this clone, so will be removed. This holds
#                        whichever PLUGIN was chosen.
#      A folder of a valid skill's name that is not ours goes on stderr as
#      "warning: <path> is not from install.sh, skipping" and is left alone.
#      When the plan is empty it prints "Nothing to change" and exits.
#   5. Asks "Apply? [y/N] " on a terminal. Anything but y or Y writes nothing,
#      prints "Nothing written" and ends the run. Without a terminal it applies
#      only with --yes, and otherwise writes nothing and exits 1.
#   6. Applies the plan. Each copy holds every file of the source skill folder
#      except those on a path with a part starting with ".", plus .ais-install.
#      A replaced folder holds nothing from its earlier copy. Prints one line
#      per folder touched: "added <path>", "updated <path>" or
#      "removed <path>", where path is the folder's full path.
#
# Exit status: 1 when any skill was invalid, any folder was skipped as not
# ours, an argument was unknown, or step 1, 3 or 5 stopped the run without a
# terminal. 0 otherwise, which includes an empty plan and a declined one. An
# unknown AGENT, PLUGIN or flag prints "error: <what>" and the usage on
# stderr, and writes nothing.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER=".ais-install"

usage() {
  cat <<'EOF'
Usage: ./install.sh [--yes] [AGENT] [PLUGIN]

  AGENT    claude   Claude Code   ~/.claude/skills
           agy      Antigravity   ~/.gemini/config/skills
           codex    Codex         ~/.agents/skills
  PLUGIN   ais      every skill in ais/
           ais-max  every skill in ais-max/, plus every skill in ais/
  --yes    apply the plan without asking
  -h, --help  print this usage and exit
EOF
}

die_arg() {
  echo "error: $1" >&2
  usage >&2
  exit 1
}

agent="" plugin="" yes=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --yes) yes=1 ;;
    -*) die_arg "unknown flag $arg" ;;
    *)
      if [ -z "$agent" ]; then agent="$arg"
      elif [ -z "$plugin" ]; then plugin="$arg"
      else die_arg "unexpected argument $arg"
      fi ;;
  esac
done

valid_agent() { case "$1" in claude|agy|codex) return 0 ;; *) return 1 ;; esac; }
valid_plugin() { case "$1" in ais|ais-max) return 0 ;; *) return 1 ;; esac; }

[ -z "$agent" ] || valid_agent "$agent" || die_arg "unknown agent '$agent'"
[ -z "$plugin" ] || valid_plugin "$plugin" || die_arg "unknown plugin '$plugin'"

interactive=0
if [ -t 0 ] && [ -t 1 ]; then interactive=1; fi

# ask <label> <name>...  Sets $answer to one of the listed names.
ask() {
  local label="$1" i reply name
  shift
  while true; do
    echo "Choose the $label:"
    i=1
    for name in "$@"; do echo "  $i) $name"; i=$((i + 1)); done
    printf '%s> ' "$label"
    if ! IFS= read -r reply; then echo >&2; exit 1; fi
    i=1
    for name in "$@"; do
      if [ "$reply" = "$name" ] || [ "$reply" = "$i" ]; then answer="$name"; return 0; fi
      i=$((i + 1))
    done
  done
}

if [ -z "$agent" ] || [ -z "$plugin" ]; then
  if [ "$interactive" -eq 0 ]; then
    echo "error: missing AGENT or PLUGIN" >&2
    usage >&2
    exit 1
  fi
  if [ -z "$agent" ]; then ask agent claude agy codex; agent="$answer"; fi
  if [ -z "$plugin" ]; then ask plugin ais ais-max; plugin="$answer"; fi
fi

case "$agent" in
  claude) target="$HOME/.claude/skills" ;;
  agy)    target="$HOME/.gemini/config/skills" ;;
  codex)  target="$HOME/.agents/skills" ;;
esac

rc=0

# check_skill <plugin> <skill>: prints what is wrong and returns 1, or returns 0.
check_skill() {
  local file="$ROOT/$1/$2/SKILL.md" info name desc
  [ -f "$file" ] || { echo "SKILL.md is missing"; return 1; }
  info="$(awk '
    NR == 1 { if ($0 !~ /^---[ \t\r]*$/) bad = 1; next }
    bad || done { next }
    /^---[ \t\r]*$/ { done = 1; next }
    /^name:/ { v = $0; sub(/^name:[ \t]*/, "", v); gsub(/[\r"\047]/, "", v); sub(/[ \t]+$/, "", v); name = v; indesc = 0; next }
    /^description:/ { v = $0; sub(/^description:[ \t]*/, "", v); gsub(/\r/, "", v); sub(/[ \t]+$/, "", v); if (v != "" && v != ">" && v != "|" && v != ">-" && v != "|-") desc = 1; indesc = 1; next }
    indesc && /^[ \t]+[^ \t\r]/ { desc = 1; next }
    { indesc = 0 }
    END { print name; print desc + 0 }
  ' "$file")"
  name="$(printf '%s\n' "$info" | sed -n 1p)"
  desc="$(printf '%s\n' "$info" | sed -n 2p)"
  [ -n "$name" ] || { echo "frontmatter has no name"; return 1; }
  [ "$desc" = "1" ] || { echo "frontmatter has no description"; return 1; }
  [ "$name" = "$2" ] || { echo "frontmatter name '$name' differs from the folder name"; return 1; }
  return 0
}

# skill_names <plugin>: prints the name of every skill folder in <plugin>/,
# one per line. Hidden folders are not skills.
skill_names() {
  local d
  for d in "$ROOT/$1"/*/; do
    if [ -d "$d" ]; then basename "$d"; fi
  done
}

clone_skills=""
for p in ais ais-max; do
  if [ -d "$ROOT/$p" ]; then clone_skills="$clone_skills$(skill_names "$p")"$'\n'; fi
done

plugins="ais"
[ "$plugin" = "ais-max" ] && plugins="ais ais-max"

# valid: lines of "<skill> <plugin>", sorted by skill.
valid=""
for p in $plugins; do
  [ -d "$ROOT/$p" ] || { echo "error: $ROOT/$p is not a folder" >&2; exit 1; }
  while IFS= read -r s; do
    [ -n "$s" ] || continue
    if problem="$(check_skill "$p" "$s")"; then
      valid="$valid$s $p"$'\n'
    else
      echo "error: $p/$s: $problem" >&2
      rc=1
    fi
  done < <(skill_names "$p")
done
valid="$(printf '%s' "$valid" | LC_ALL=C sort)"

srcroot=""
if [ "$agent" = "codex" ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 is needed to build the Codex skills and was not found" >&2
    exit 1
  fi
  if ! build_out="$(cd "$ROOT" && python3 scripts/build-codex.py local 2>&1)"; then
    echo "error: the Codex build failed" >&2
    printf '%s\n' "$build_out" >&2
    exit 1
  fi
  srcroot="$ROOT/.codex-local"
fi

is_ours() { [ -d "$1" ] && [ ! -L "$1" ] && [ -f "$1/$MARKER" ]; }

adds="" updates="" removals=""
while read -r s p; do
  [ -n "$s" ] || continue
  dest="$target/$s"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    if is_ours "$dest"; then
      updates="$updates$s $p"$'\n'
    else
      echo "warning: $dest is not from install.sh, skipping" >&2
      rc=1
    fi
  else
    adds="$adds$s $p"$'\n'
  fi
done <<EOF
$valid
EOF

if [ -d "$target" ]; then
  for d in "$target"/*/; do
    [ -d "$d" ] || continue
    d="${d%/}"
    s="$(basename "$d")"
    if is_ours "$d" && ! printf '%s' "$clone_skills" | grep -qxF -- "$s"; then
      removals="$removals$s"$'\n'
    fi
  done
fi
removals="$(printf '%s' "$removals" | LC_ALL=C sort)"

# print_group <mark> <lines>: prints "  <mark> <skill>" for each
# "<skill> [plugin]" line.
print_group() {
  local s p
  while read -r s p; do
    if [ -n "$s" ]; then echo "  $1 $s"; fi
  done <<EOF
$2
EOF
}

print_group + "$adds"
print_group "~" "$updates"
print_group - "$removals"

if [ -z "$adds$updates$removals" ]; then
  echo "Nothing to change"
  exit "$rc"
fi

if [ "$yes" -eq 0 ]; then
  if [ "$interactive" -eq 1 ]; then
    printf 'Apply? [y/N] '
    reply=""
    IFS= read -r reply || reply=""
    case "$reply" in
      y|Y) ;;
      *) echo "Nothing written"; exit "$rc" ;;
    esac
  else
    echo "error: not a terminal, pass --yes to apply the plan" >&2
    exit 1
  fi
fi

# copy_skill <source folder> <dest folder>
copy_skill() {
  local src="$1" dest="$2" rel
  mkdir -p "$dest"
  (cd "$src" && find . -type f ! -path '*/.*') | while IFS= read -r rel; do
    rel="${rel#./}"
    mkdir -p "$dest/$(dirname "$rel")"
    cp "$src/$rel" "$dest/$rel"
  done
  : > "$dest/$MARKER"
}

source_of() {
  if [ -n "$srcroot" ]; then echo "$srcroot/$1"; else echo "$ROOT/$2/$1"; fi
}

mkdir -p "$target"
while read -r s p; do
  [ -n "$s" ] || continue
  copy_skill "$(source_of "$s" "$p")" "$target/$s"
  echo "added $target/$s"
done <<EOF
$adds
EOF
while read -r s p; do
  [ -n "$s" ] || continue
  rm -rf "${target:?}/$s"
  copy_skill "$(source_of "$s" "$p")" "$target/$s"
  echo "updated $target/$s"
done <<EOF
$updates
EOF
while read -r s; do
  [ -n "$s" ] || continue
  rm -rf "${target:?}/$s"
  echo "removed $target/$s"
done <<EOF
$removals
EOF

exit "$rc"
