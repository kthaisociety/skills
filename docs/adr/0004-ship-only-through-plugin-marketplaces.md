# ADR-0004: Ship through plugin marketplaces, and install.sh for developers

**Decision:** This repo MUST ship skills to members only as plugins through the release repos, MAY offer `install.sh` for developers installing from a local clone, and MUST NOT be a skills.sh install source or offer any other install path.

**Reason:** Keeping `npx skills add kthaisociety/skills` alongside the plugins was weighed and lost. It installs loose, unprefixed skills that ignore the **ais**/**ais-max** split and would expose **ais-max** to every member. `install.sh` stays because a developer needs a skill from their clone in their agent before it is released, which a marketplace install can't give.

**Consequence:** `skills.sh.json` and the skills.sh install instructions go. The folder layout only has to suit the build scripts and `install.sh`, not skills.sh discovery. A member using the old install path keeps a stale copy until they move to a marketplace. A third install path, such as a package registry, needs this record amended first.

**Date:** 2026-11-27
