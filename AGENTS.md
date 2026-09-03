# IoTSploit Agent Setup

## Core Principles (CRITICAL)

Less is more. The simplest solution is the best solution. The action hierarchy
for every change: Delete > Replace > Add.

- Solve at the owner: Put behavior in the code path that owns or observes it.
  For fixes, never guard a symptom with a staleness check, initialization flag,
  skip-first-call branch, or try/except around broken logic; relocate the
  trigger and delete the wrong path. For features, extend the existing owner
  rather than creating a parallel abstraction.
- Search and reuse first: Search the whole repository before creating a
  feature, component, helper, workflow, or utility. Reuse or adapt what exists,
  consolidate in-scope duplication in the shared owner, and delete duplicate
  paths. Three similar lines beat a helper nobody else calls.
- Delete and modify existing code before creating new code: Bugfixes are
  net-negative by default unless deletion and relocation are demonstrably
  impossible. A new file must first prove it cannot fit cleanly in an existing
  owner.
- Keep scope minimal: Implement only the simplest complete solution. Avoid
  impossible-state handling, speculative flags, compatibility shims, policy
  scaffolding, and unrelated cleanup. Tests are out of scope by default — rely
  on existing coverage and focused validation; only an uncovered, high-risk
  regression path justifies minimal new test code.
- Ship zero-regression, production-ready changes: Understand what you remove
  instead of retaining broken code as insurance. Remove unused imports,
  functions, types, files, and comments; run relevant cleanup checks; and
  thoroughly debug and validate the changed owner. Do not break existing
  features or workflows unless the PR intentionally removes them with evidence.

Read `.agents/local.md` when it exists for machine-specific toolchain paths and
commands. Use Poetry for Python dependency management and command execution.

Read `docs/architecture.md` before adding or moving Python code — it describes
the ports-and-adapters layout and the dependency rule the packages follow.

Read `docs/writing-plugins.md` before adding an exploit plugin or a device
driver — it carries the templates, the framework capabilities, and the rules.

IoTSploit's MCP server runs on the rig that has access to the hardware and the
Django backend. External agents connect over HTTP.

1. Start `iotsploit-django` on the rig.
2. Start the MCP server:

```bash
iotsploit-mcp http --host 127.0.0.1 --port 9900
```

3. Configure your agent from `.mcp.json`, replacing the host as needed.

`iotsploit-mcp/README.md` owns the tool surface and the rules for adding a
mutating tool. Read it before changing what MCP exposes.

## Execution Plans

Plans live in `docs/exec-plans/`: `active/` (in progress), `pending/`
(decided, not started), `completed/` (done/stale — don't act on unless stated).
Search there before writing a new plan.

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
