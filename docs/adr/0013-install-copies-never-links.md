# ADR-0013: install.sh copies skills and never links them

**Decision:** `install.sh` MUST copy each skill from the clone into the agent's skills folder, and MUST NOT symlink it.

**Reason:** Symlinking from the clone, as the Custom-skills installer did, was weighed and lost. Several maintainers push to this repo, so with a link a `git pull` changes the skills an agent runs without the developer doing anything, and they find out only when a skill behaves differently. A copy changes only when the developer reruns the installer, which prints what it added, updated and removed.

**Consequence:** An edit in the clone reaches an agent only after a rerun, so a developer testing a skill they're editing reruns `install.sh` after each change. The installer has to recognise the copies it wrote, since a copy carries no link back to the clone. A symlink, or a mode that offers one, breaks this record.

**Scope:** `install.sh`

**Date:** 2026-11-27
