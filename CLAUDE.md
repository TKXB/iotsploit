# Claude Code

Read `.agents/local.md` when it exists for machine-specific toolchain paths and
commands. Use Poetry for Python dependency management and command execution.

## Pre-Commit Test Gate

Before committing Python code, run the full test gate:

```bash
tools/testing/test-python-full.sh
```

See `.agents/standards/testing.md` for the complete policy, including
the rules for writing tests — read those before adding or changing a test.
Enable the local git hook once per working copy:

```bash
git config core.hooksPath tools/git-hooks
```
