# ADR-0008: The Codex build changes only what Codex needs to read a skill

**Decision:** The Codex build MUST NOT change a skill's text except where Codex can't read it as written: frontmatter keys Codex ignores, slash mentions of known skills, and the invocation policy.

**Reason:** Porting Custom-skills' swap of em dashes and curly quotes into plain punctuation was weighed and lost. Codex reads both characters, so the swap is a style rule, and a style rule applied only in one agent's tree makes the Codex copy of a skill differ from the source for no reason the reader can see.

**Consequence:** A Codex skill's body matches its source apart from the rewritten mentions. A style rule for skill text belongs in the source skills, where every agent's tree gets it, and a rewrite added to the Codex build for any reason other than Codex readability breaks this record.

**Scope:** the Codex build script

**Date:** 2026-11-27
