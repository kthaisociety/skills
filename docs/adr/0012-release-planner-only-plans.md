# ADR-0012: The release planner only plans the version

**Decision:** `scripts/plan-release.py` MUST only work out the release's version and report what it read to get there, and the release run's other steps MUST stay as steps in the release workflow, not move into a release script.

**Reason:** One `scripts/release.py` that runs every step, with the workflow calling it once, was weighed and lost. It would put the branch guard, the dry-run stop and the summary under test, but each of those is one line of shell, and their tests would mostly test fakes of git, the test suite and the three build scripts. The rules that can really go wrong are the version rules, and a small planner tests all of them against real git.

**Consequence:** The branch guard, the dry-run stop, the queueing of runs and the summary have no automated tests, and a change to them is checked by starting the workflow by hand. The publish stage joins the workflow as steps of its own. A script that runs the builds, the checks or a publish on the workflow's behalf breaks this record.

**Scope:** `scripts/plan-release.py`, `.github/workflows/release.yml`

**Date:** 2026-11-27
