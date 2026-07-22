---
name: implement-with-review
description: >-
  Implement a requested feature or fix using the repo's existing architecture,
  conventions, and patterns, then harden it with dual independent review
  (behavioral + technical), a fixer pass, and final verification.
  Use when the user asks to implement a feature, build something end-to-end,
  land a non-trivial change, or wants implement → review → fix → verify
  before considering the work done. Triggers on: "implement", "build this",
  "add feature", "ship it properly", "with review", dual review, or any
  request to implement and then critically review before finishing.
---

# Implement with dual review

Implement the requested change using the **existing** architecture, conventions, and patterns. Prefer the smallest complete diff. Do not invent parallel abstractions or drive-by refactors.

Work in four phases: **understand → implement → dual review → verify**. Repeat the review/fix loop until both reviewers report no critical or high-severity issues.

## Before coding

1. **Read first.** Load the relevant production code, tests, types, fixtures, and nearby implementations that already solve similar problems.
2. **Map the change.** Identify expected behavior, edge cases, dependencies, affected public APIs, and failure modes.
3. **Match the house style.** Reuse existing helpers, error shapes, naming, file layout, and test patterns. If two approaches fit, pick the one already used in-tree.
4. **Plan the smallest complete change.** No unrelated refactors, placeholders, stubs, or "while we're here" cleanups unless they are required for correctness.

## Implementation

1. Implement only what the request needs.
2. Add or update tests for:
   - main / happy path
   - important edge cases
   - failure and error paths
3. Run the **relevant** validation for the touched area:
   - typecheck
   - lint
   - unit / integration tests
   - build (when the change can break it)
4. Do not mark the work done after a green local run alone — continue to dual review.

## Dual review (mandatory)

After the implementation is complete and initial checks pass, run **two independent reviewers**, then a **fixer**. Reviewers must **not** modify code.

Prefer spawning both reviewers as **parallel sub-agents** with **fresh context** so they do not anchor on each other or on the implementer's rationale. Give each reviewer:

- the original requirements / user request
- the full diff (e.g. `git diff` against the branch base or starting point)
- any directly relevant test output or type errors
- an explicit instruction: **assume the implementation is wrong** and only report findings

### Reviewer A — Behavioral correctness

Review **only** the diff and requirements. Focus on product/behavior truth:

- regressions vs prior behavior
- missing requirements or partial implementations
- incorrect behavior or wrong edge-case handling
- unintended API / contract changes
- weak or missing error handling
- test gaps (untested main path, edges, or failures)
- tests that assert the wrong thing or mirror bugs in the code

Do **not** modify code. Output a severity-tagged list: `critical` / `high` / `medium` / `low`, each with file/hunk references and a concrete expected vs actual.

### Reviewer B — Technical correctness

Independently review **only** the diff. Assume it compiles and tests may be green, but the design can still be flawed:

- concurrency / race conditions
- security issues (injection, authz, secret leakage, unsafe defaults)
- resource leaks (handles, listeners, connections, timers)
- invalid assumptions about inputs, environment, or callers
- maintainability risks and unnecessary complexity
- performance footguns that matter at realistic scale
- edge cases the tests would not catch
- violations of existing architecture or patterns

Do **not** modify code. Same severity-tagged format as Reviewer A.

### Fixer

1. Read both review reports.
2. **Apply** every valid `critical` and `high` finding; apply `medium` when clearly correct and in scope.
3. **Reject** invalid findings with a one-line concrete reason (e.g. contradicted by existing API, out of scope, already covered).
4. Add or tighten tests for each accepted bug or gap.
5. Re-run the relevant typecheck / lint / tests / build.

### Final verification

1. Give **both** reviewers the **updated** diff and prior findings (what was fixed vs rejected).
2. They re-inspect independently. Goal: **no remaining critical or high** issues.
3. If either still reports critical/high, return to **Fixer** and repeat.
4. When both are clear of critical/high:
   - run the full **relevant** validation suite once more
   - summarize: what changed, tests added, findings fixed, findings rejected (with reasons), residual medium/low risk

## Rules of engagement

- **One writer.** Only the implementer/fixer edits the tree; reviewers are read-only.
- **Diff-scoped reviews.** Reviewers reason from the diff + requirements, not from re-implementing the feature in their head as greenfield.
- **No scope creep.** Reject review suggestions that are pure nice-to-haves unless they block correctness, security, or required behavior.
- **House patterns win.** When a review pushes a new abstraction and the repo already has a pattern, keep the repo pattern unless it is actively wrong.
- **Stop condition.** Clear of critical/high from both reviewers + green relevant validation. Do not infinite-loop on low-severity nits.

## Output checklist (when reporting done)

- [ ] Requirements covered
- [ ] Smallest complete diff (no unrelated refactors)
- [ ] Tests for main, edge, and failure paths
- [ ] Reviewer A (behavioral) run
- [ ] Reviewer B (technical) run
- [ ] Fixer applied/rejected with reasons
- [ ] Re-review clear of critical/high
- [ ] Final validation suite green
