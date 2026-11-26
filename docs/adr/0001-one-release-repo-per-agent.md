# ADR-0001: Publish each agent's plugins to its own release repo

**Decision:** Each agent's plugins MUST publish to a release repo of their own, one per agent, and this repo MUST NOT be the install target of any agent's plugin marketplace.

**Reason:** Serving the Claude and Codex marketplaces straight from this repo was weighed and lost. Each agent reads a different layout, and Antigravity reads one plugin per repo root or subfolder with no custom marketplace, so a shared tree has to satisfy every agent at once. Separate repos stay small, each holds only what its agent reads, and supporting a new agent means adding one repo rather than reworking a shared one.

**Consequence:** Every agent needs a build step here and a publish step to its release repo. A plugin file added by hand to a release repo is overwritten by the next publish. Adding an agent never changes another agent's release repo.

**Date:** 2026-11-26
