# PCR-0001: Write repo scripts in Python with the standard library only

**Decision:** Every script in this repo MUST be Python 3 using only the standard library, with its tests run by `unittest`.

**Reason:** Keeping the existing Node scripts and rewriting the Custom-skills builds in Node was weighed and lost. The Custom-skills build, release and helper-skill scripts already work, are Python with no extra packages, and come with tests, so porting them is less work and keeps both repos readable by the same person.

**Consequence:** No `package.json`, `requirements.txt` or other dependency file is needed to run a script, and CI needs only `actions/setup-python`. A script that imports a third-party package, or a new script written in another language, breaks this record.

**Exceptions:** `install.sh`, the developer installer ported from Custom-skills, stays bash.

**Date:** 2026-11-26
