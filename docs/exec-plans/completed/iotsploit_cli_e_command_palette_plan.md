# IoTSploit CLI `e` Command Palette Plan

Status: approved for implementation using Option B; no feature code has been implemented.

Date: 2026-07-14

Approved option: Option B — live prompt-toolkit command palette with the compatibility gate.

## 1. Goal

Add a keyboard-first command palette to `iotsploit-cli` inspired by the Codex CLI slash-command popup.

The intended user experience is:

1. The user starts typing `e` at an empty IoTSploit shell prompt.
2. A menu appears immediately, without requiring Enter or Tab.
3. The menu lists every currently available command whose name begins with `e` and shows a short explanation beside each command.
4. Additional characters, such as `ex`, filter the list in real time.
5. The user can navigate the list, insert or execute a selection, dismiss the menu, or continue typing arguments.

This plan assumes that “enter `e`” means typing the character at the interactive prompt, not submitting a standalone `e` command. Option A below covers the simpler submit-then-list interpretation.

## 2. Scope

### In scope

- Interactive command discovery for canonical, visible commands beginning with `e`.
- Runtime discovery of command names and descriptions; no hard-coded command list.
- Live prefix filtering.
- Keyboard navigation, selection, dismissal, and command execution.
- Preservation of existing `cmd2` parsing and dispatch.
- Linux/macOS terminal support and a defined Windows compatibility path.
- Deterministic unit and integration tests that do not require physical hardware or live services.
- README documentation for the new interaction.

### Out of scope for the MVP

- Replacing the whole IoTSploit shell with a full-screen TUI.
- Adding a general-purpose palette for every first letter.
- Changing the behavior or syntax of existing IoTSploit commands.
- Executing a command merely because its suggestion is displayed.
- Discovering device-operation names that are not top-level `cmd2` commands.
- Adding mutating MCP tools.
- Fuzzy or substring search; the MVP uses case-insensitive prefix matching.

## 3. Current implementation: facts

### 3.1 Codex reference behavior

The current Codex source separates the feature into distinct responsibilities:

- [`slash_command.rs`](https://github.com/openai/codex/blob/main/codex-rs/tui/src/slash_command.rs) defines canonical command names, presentation order, descriptions, aliases, argument support, and availability.
- [`command_popup.rs`](https://github.com/openai/codex/blob/main/codex-rs/tui/src/bottom_pane/command_popup.rs) builds display rows, filters exact and prefix matches, maintains selection/scroll state, and renders a command plus description.
- [`chat_composer.rs`](https://github.com/openai/codex/blob/main/codex-rs/tui/src/bottom_pane/chat_composer.rs) observes every text change, opens or closes the popup based on composer context, routes keys to the active popup, and dispatches accepted commands.

Relevant Codex design choices to retain:

- The trigger is recognized only in the initial command token, not anywhere in arbitrary text.
- The command catalog and the popup are separate concerns.
- Descriptions live with command metadata rather than in rendering code.
- Exact matches are preferred, followed by prefix matches.
- Hidden, alias-only, debug, or unavailable commands can be excluded.
- Editing the filter resets selection to a valid result.
- Escape dismisses the popup without destroying the draft.
- Selection does not bypass the normal command-dispatch layer.

Codex can do this directly because its full-screen composer receives individual key events and owns popup rendering.

### 3.2 IoTSploit CLI today

The current shell is implemented in [`iotsploit-cli/src/iotsploit_cli/console.py`](../iotsploit-cli/src/iotsploit_cli/console.py):

- `SAT_Shell` inherits from a dynamic `cmd2.Cmd` base plus auto-discovered command mixins.
- `cmd2.Cmd.cmdloop()` owns the interactive read/parse/dispatch loop.
- GNU Readline/pyreadline supplies line editing, history, and Tab completion.
- `SAT_Shell.get_all_commands_by_category()` discovers `do_*` methods dynamically.
- `SAT_Shell.get_command_doc()` already extracts the first docstring line for the custom help display.
- Command modules already use short docstrings such as “Execute a specific plugin,” which are suitable as palette explanations.
- The project pins `cmd2` 2.4.3 in the root [`pyproject.toml`](../pyproject.toml) and allows `^2.4` in [`iotsploit-cli/pyproject.toml`](../iotsploit-cli/pyproject.toml).

`cmd2` 2.4.3 has useful completion primitives, including `CompletionItem` descriptions, but its main input loop invokes completion only through Readline’s completion key. It has no application-level callback for “the user just typed `e`.” Therefore, a true live popup cannot be added cleanly through a `do_e()` method or a normal cmd2 completer alone.

`prompt-toolkit` 3.0.48 is already present transitively in the Poetry lock file, but `iotsploit-cli` does not declare it as a direct dependency. If the feature imports it, both the root project and standalone CLI package must declare it explicitly.

### 3.3 Test coverage gap

The root pytest configuration does not currently include `iotsploit-cli/tests`. The directory contains cache artifacts but no maintained Python test sources. A feature in the CLI package could therefore be missed by the required full Python test gate unless the root test paths are updated.

## 4. Required UX contract

The implementation should use the following observable behavior as its contract:

| Input or key | Expected behavior |
|---|---|
| `e` as the first command token | Open the menu and show all eligible `e*` commands with explanations. |
| `ex`, `exe`, and so on | Filter case-insensitively by command-name prefix. |
| `e` inside an argument or path | Do not open the command menu. |
| Up / Down | Move the active selection without changing the submitted command. |
| Tab | Insert the selected command name and leave the line editable for arguments. |
| Enter while a result is selected | Accept the selected command and submit it through the normal cmd2 dispatcher. |
| Enter when no result exists | Submit the literal line through normal cmd2 behavior. |
| Escape | Close the menu and retain the current input text. |
| Backspace to an empty line | Close the menu. |
| Type a space after a complete command | Close the menu and allow normal argument entry/completion. |
| Ctrl+C | Cancel the current input using the shell’s existing behavior. |
| Ctrl+D on an empty line | Preserve the shell’s existing EOF/exit behavior. |
| Piped input, startup scripts, or non-TTY stdin | Bypass the palette and preserve cmd2 behavior. |

Eligibility rules:

- Source candidates from `get_visible_commands()`, not raw `dir()` output.
- Include only canonical command names beginning with `e` after case-folding.
- Exclude hidden and disabled commands.
- Exclude the internal `eof` sentinel if cmd2 reports it as visible.
- Do not include aliases or macros in the MVP because they do not have the same stable explanation metadata. They can be added later with descriptions such as `Alias -> target`.
- Obtain the explanation from the first non-empty docstring line.
- Use `No description available` as a deterministic fallback.
- Normalize whitespace and strip terminal control characters from descriptions before display.

The catalog must be evaluated dynamically, or cheaply rebuilt when completion starts, so newly disabled commands and future `e*` command modules appear correctly without editing the palette.

## 5. Implementation options

| Criteria | Option A: submitted `e` helper | Option B: prompt-toolkit input adapter | Option C: full interactive TUI redesign |
|---|---|---|---|
| Approach | Add `do_e()` that prints or numerically selects `e*` commands after Enter. | Add a prompt-toolkit line editor/completer in front of cmd2 while retaining cmd2 parsing and dispatch. | Replace the line-oriented shell UI with a full-screen prompt-toolkit/Textual application. |
| Main goal | Lowest-cost command discovery. | Match the requested live Codex-like interaction. | Create a reusable foundation for several popups and richer terminal UI. |
| Code impact | Low | Medium | High |
| Likely files changed | `console.py`, tests, README | New palette module, `console.py`, dependency files, tests, README | New TUI package, composition/dispatch adapters, dependencies, extensive tests and docs |
| Development effort | Low | Medium | High |
| Implementation risk | Low | Medium | High |
| Performance impact | Negligible | Negligible for the small command catalog | Higher render/event-loop overhead |
| Compatibility impact | Very low; normal line editor remains unchanged | Must preserve cmd2 history, argument completion, scripts, redirection, nested prompts, and asynchronous output | Broad changes to terminal compatibility and cmd2 integration |
| Testing requirement | Catalog and output tests | Catalog, completer, key interaction, cmd2 adapter, TTY fallback, and manual PTY tests | Full terminal behavior, resize, event loop, subprocess output, and migration tests |
| Maintenance impact | Small, but behavior is not Codex-like | Moderate; a narrow adapter must track the pinned cmd2 completion API | Large; IoTSploit owns a second UI framework and more state |
| Future extension | Limited | Good for other prefix palettes and richer metadata | Excellent, but well beyond this feature |
| Recommended when | Showing the list after pressing Enter is acceptable. | Immediate suggestions are required and existing cmd2 behavior can be preserved. | A broader terminal UX redesign is already approved. |

## 6. Recommendation

Recommended option: **Option B — prompt-toolkit input adapter**, delivered behind a compatibility gate.

Reasons:

- It is the only scoped option that reproduces the important Codex behavior: show and filter suggestions as the user types.
- It leaves command parsing, command mixins, hooks, redirection, and execution in cmd2.
- `prompt-toolkit` already exists in the resolved environment and directly supports completion while typing plus per-item display metadata.
- It allows the catalog/filtering logic to remain small and independently testable.

Trade-offs:

- `prompt-toolkit` must become a declared direct dependency.
- cmd2 2.4.3’s completion engine is Readline-oriented. The adapter must prove that ordinary Tab completion, especially command-argument completion, still works before it replaces the default interactive reader.
- Prompt history and terminal redraw behavior need explicit integration rather than being inherited automatically from Readline.

The compatibility gate is mandatory: if a prototype cannot preserve existing cmd2 completion and history without copying a large portion of cmd2 internals, stop and choose Option A or separately approve a cmd2 upgrade/TUI redesign.

### Decision record

Option B was selected by the user on 2026-07-14.

This approval authorizes implementation of the plan beginning with the Phase 0 compatibility spike. It does not waive the compatibility gate: the default interactive input path must not change unless the spike demonstrates that existing cmd2 command completion, argument completion, history, scripts, nested prompts, and non-TTY behavior can be preserved with a narrow adapter.

If the gate fails, implementation pauses and returns to the user with evidence and revised options; it does not silently fall back to Option A or expand into Option C.

## 7. Proposed architecture

```text
prompt-toolkit input session
        |
        +-- text-insert event --> e-prefix catalog/filter --> menu rows
        |
        +-- explicit Tab ------> cmd2 completion adapter
        |
        +-- accepted line -------------------------------+
                                                         |
                                                         v
cmd2 cmdloop --> parser/hooks/redirection --> existing do_<command>()
```

### 7.1 Command metadata provider

Create `iotsploit-cli/src/iotsploit_cli/command_palette.py` containing UI-independent logic:

- An immutable `CommandPaletteEntry` value with `name`, `description`, and optionally `category`.
- A provider that calls the shell’s `get_visible_commands()` and `get_command_doc()` methods.
- A policy function that applies the eligibility rules in Section 4.
- Stable ordering: exact match first, then prefix matches alphabetically. With the initial `e`, all results are prefix matches and therefore alphabetical.
- Description sanitization and fallback behavior.

The provider must inspect metadata only. It must never call a `do_*` handler while constructing suggestions.

### 7.2 Live completer

Add an `ECommandCompleter` based on prompt-toolkit’s `Completer` interface:

- Inspect only the current line and cursor position.
- Activate only while the cursor is in the first token and that token begins with `e`, case-insensitively.
- Yield completions whose replacement range covers the partially typed token.
- Put the command name in the completion display field and its explanation in `display_meta`.
- Return no automatic completions outside the `e` context.
- Keep all work synchronous because the catalog is small and local.

### 7.3 cmd2 completion compatibility adapter

Automatic `e` completion and explicit Tab completion are different paths:

- A text-insert completion event should show only enhanced `e*` entries.
- An explicit Tab event outside the `e` context should delegate to existing cmd2 completion, including argument-specific completers and argparse completers.

Perform a time-boxed implementation spike before the main change:

1. Feed a prompt-toolkit `Document` line and cursor into a small adapter.
2. Derive the token text, `begidx`, and `endidx` expected by cmd2.
3. Reuse cmd2’s completion machinery for top-level command names and command arguments.
4. Verify completions for at least a command name, a command with an existing custom/argparse completer, a file path/redirection case, and a command with no matches.
5. Confirm that completion candidates can be read without mutating shell state beyond cmd2’s documented completion fields.

Because cmd2 2.4.3 exposes part of this path through protected methods, isolate any protected API calls in one adapter class and add version/behavior tests. Do not scatter cmd2-internal calls through `SAT_Shell`.

Gate result:

- If compatibility is demonstrated with a narrow adapter, continue with Option B.
- If it requires copying cmd2’s parser/completer implementation or breaks existing completion, stop. Present Option A and a separately scoped dependency-upgrade investigation to the user.

### 7.4 Input-session integration

Keep `cmd2.Cmd.cmdloop()` as the outer loop. Override the narrowest input seam rather than rewriting `cmdloop()`:

- Intercept `read_input()` only when cmd2 requests `CompletionMode.COMMANDS`, raw interactive input is enabled, and stdin/stdout are TTYs.
- Delegate every other call to `super().read_input()` so nested questions, scripts, test streams, and non-interactive use remain unchanged.
- Reuse a single prompt-toolkit `PromptSession` for the lifetime of `SAT_Shell`.
- Convert the existing ANSI-colored prompt through prompt-toolkit’s ANSI formatted-text adapter.
- Use a column menu layout that reserves a bounded number of rows and shows description metadata.
- Do not use a background completion thread; the provider is in-memory.

This seam is preferable to overriding cmd2’s private `_cmdloop()` or `_read_command_line()` because cmd2 should continue to own terminal-lock handling, EOF conversion, hook dispatch, and command lifecycle.

### 7.5 Key behavior

Use prompt-toolkit key bindings scoped to an active completion menu:

- Up/Down select suggestions.
- Tab applies the selected completion but does not submit.
- Enter applies the selected completion and accepts the resulting line, causing normal cmd2 dispatch.
- Escape cancels only the completion menu and retains the buffer.
- Normal Enter behavior remains unchanged when no completion is selected.

Do not intercept `e` as a global key binding. Activation must be based on buffer context so words, arguments, paths, pasted text, and nested `Input_Mgr` prompts are not corrupted.

### 7.6 History and terminal output

- Seed prompt-toolkit history from the current cmd2 session history where practical.
- Let prompt-toolkit retain newly accepted lines for Up/Down recall during the process.
- Continue allowing cmd2 to record accepted commands for its `history` command and persistence behavior.
- Add a duplication test so one accepted line does not appear twice in either history surface.
- Verify redraw behavior while background service output is present. Use prompt-toolkit’s supported stdout patching only around the prompt if required; do not globally replace stdout.

### 7.7 Dependency declaration

Declare `prompt-toolkit` directly in both:

- Root `pyproject.toml`, for the monorepo development/test environment.
- `iotsploit-cli/pyproject.toml`, so the independently published package is complete.

Regenerate `poetry.lock` through Poetry. Do not hand-edit the lock file. Prefer a compatible constraint anchored at the already resolved 3.0.48 version unless the compatibility spike proves a newer version is required.

## 8. File-level change plan

| File | Planned change |
|---|---|
| `iotsploit-cli/src/iotsploit_cli/command_palette.py` | New metadata provider, activation/parser policy, prompt-toolkit completer, and isolated cmd2 completion adapter. |
| `iotsploit-cli/src/iotsploit_cli/console.py` | Construct the palette/session after cmd2 initialization; override the interactive `read_input()` seam; add scoped key bindings and safe fallback. |
| `iotsploit-cli/tests/test_command_palette.py` | Unit tests for catalog eligibility, descriptions, filtering, replacement ranges, and no-activation contexts. |
| `iotsploit-cli/tests/test_command_palette_input.py` | Prompt-toolkit pipe-input integration tests for live display/selection/dismissal and cmd2 completion compatibility. |
| `iotsploit-cli/README.md` | Document the `e` trigger, filtering, keys, examples, and TTY-only behavior. |
| `iotsploit-cli/pyproject.toml` | Add the direct prompt-toolkit runtime dependency. |
| Root `pyproject.toml` | Add the same direct dependency and include `iotsploit-cli/tests` in root pytest test paths. |
| `poetry.lock` | Regenerate using Poetry after dependency metadata changes. |

Avoid adding palette logic to individual command modules. Their existing `do_*` method names and docstrings are the source of truth.

## 9. Implementation sequence

### Phase 0: compatibility spike

1. Build an isolated prompt-toolkit-to-cmd2 completion adapter.
2. Exercise command-name, argument, path, redirection, history, Ctrl+C, and Ctrl+D behavior.
3. Record whether protected cmd2 APIs are required and how much code is involved.
4. Apply the compatibility gate from Section 7.3.

Deliverable: a brief result added to this document or a small architecture-decision record before production integration.

### Phase 1: command catalog

1. Add the command entry model.
2. Discover visible commands dynamically.
3. Filter to eligible `e*` commands.
4. Extract and sanitize explanations.
5. Add catalog unit tests before UI integration.

### Phase 2: live completion UI

1. Add context-sensitive activation and prefix filtering.
2. Render command names with explanation metadata.
3. Add navigation, Tab, Enter, and Escape behavior.
4. Add deterministic prompt-toolkit pipe-input tests.

### Phase 3: shell integration

1. Add the TTY-only `read_input()` integration.
2. Preserve non-TTY and nested-input delegation.
3. Connect accepted text back to unchanged cmd2 dispatch.
4. Synchronize history and verify terminal redraw behavior.

### Phase 4: packaging and documentation

1. Add direct dependencies with Poetry and refresh the lock file.
2. Add CLI tests to the root test configuration.
3. Document the feature and keyboard controls.
4. Run targeted tests, then the full repository gate.

## 10. Test plan

### 10.1 Catalog unit tests

- Includes every visible canonical command beginning with `e`.
- Excludes non-`e` commands, hidden commands, disabled commands, aliases, macros, and `eof`.
- Uses the first non-empty docstring line.
- Uses the fallback description when no docstring exists.
- Normalizes whitespace and strips control characters.
- Reflects a command that becomes disabled after shell initialization.
- Does not call command handlers during discovery.

### 10.2 Completer unit tests

- `e` returns the complete eligible set.
- `ex` and longer prefixes narrow the set.
- Matching is case-insensitive.
- Completion replacement covers only the current first token.
- Leading shell whitespace is handled consistently.
- Empty input, a non-`e` first token, text after a space, multiline text, and `e` inside an argument produce no automatic palette results.
- Long descriptions do not break rendering or inject control sequences.

### 10.3 Input integration tests

Use prompt-toolkit’s pipe input and dummy output so these tests are deterministic and require no human or physical TTY:

- Typing `e` starts completion without Tab.
- Up/Down changes selection.
- Tab inserts a result and leaves the line editable.
- Enter submits the selected canonical command text exactly once.
- Escape dismisses while retaining the typed prefix.
- Backspacing to empty closes suggestions.
- Enter with zero matches preserves normal literal submission.
- Ctrl+C and Ctrl+D preserve expected shell semantics.
- Prompt ANSI styling does not become literal escape text.

### 10.4 cmd2 regression tests

- Existing top-level Tab completion still works.
- Existing argument/path completion still works for representative commands.
- `help`, aliases, macros, redirection, pipes, and command history still operate.
- cmd2 hooks receive the accepted line exactly once.
- `get_visible_commands()` exclusions are honored.
- Non-TTY stdin and startup scripts bypass prompt-toolkit.
- `Input_Mgr` nested prompts remain normal prompts and do not activate the palette.
- Disabled or unavailable commands are not dispatched from stale suggestions.

### 10.5 Manual terminal matrix

- Linux with GNU Readline-compatible terminal: required.
- macOS terminal: required before claiming support.
- Windows/pyreadline terminal: verify or document as fallback-to-cmd2 until supported.
- Narrow terminal, terminal resize, ANSI colors, rapid typing, paste, and background log output.

### 10.6 Required commands

Run project commands through Poetry:

```bash
poetry run pytest iotsploit-cli/tests
tools/testing/test-python-full.sh
```

The final implementation report must include passed, failed, skipped, and warning counts. Hardware/service tests must not be silently skipped or weakened to make the gate pass.

## 11. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Replacing Readline loses cmd2 argument completion | High | Mandatory Phase 0 adapter spike and regression gate; do not ship Option B if compatibility is incomplete. |
| Two history systems duplicate or reorder entries | Medium | Seed once, add accepted lines once, and test prompt recall separately from cmd2’s `history` command. |
| Prompt redraw conflicts with asynchronous output | Medium | Test with background output and scope any stdout patching to the active prompt. |
| Private cmd2 API changes | Medium | Keep version pinned, isolate protected calls in one adapter, assert the supported cmd2 version/behavior, and document the upgrade point. |
| Dynamic command docstrings are missing or too long | Low | Deterministic fallback, whitespace normalization, control stripping, and terminal-width truncation/wrapping. |
| Internal `eof` appears as a normal command | Low | Explicitly exclude the sentinel from palette eligibility. |
| Menu opens for ordinary letter `e` in arguments | Medium | Activate only in the first token before whitespace and only in the top-level command input session. |
| Published CLI works in monorepo but lacks dependency | High | Declare prompt-toolkit in both root and package manifests; validate the built wheel in a clean environment. |
| CLI tests remain outside the full gate | High | Add `iotsploit-cli/tests` to root pytest `testpaths`. |

## 12. Acceptance criteria

The feature is complete only when all of the following are true:

- Typing `e` at the top-level interactive prompt immediately displays all eligible `e*` commands and an explanation for each.
- The list is derived from the current runtime command registry, not duplicated in source.
- Typing more characters filters the list without submitting text.
- Tab, Enter, Escape, Up, and Down satisfy the contract in Section 4.
- Selection flows through normal cmd2 parsing, hooks, and command handlers.
- Ordinary cmd2 command and argument completion is preserved.
- History, Ctrl+C, Ctrl+D, aliases, macros, pipes, redirection, scripts, and non-TTY input do not regress.
- No command executes solely because the menu opened.
- The standalone `iotsploit-cli` package declares every runtime dependency it imports.
- CLI tests are included in the root full-test gate.
- Targeted tests and `tools/testing/test-python-full.sh` pass.
- README usage is updated.

## 13. Decision

- [ ] Option A — Minimal change: submit `e`, then show/select from the list.
- [x] Option B — Selected: live prompt-toolkit command palette with the compatibility gate.
- [ ] Option C — Full terminal UI redesign.
- [ ] Need more investigation or a UX mockup first.

Next action: begin Phase 0, the prompt-toolkit-to-cmd2 completion compatibility spike. Phase 0 must pass before the default interactive input path is changed.
