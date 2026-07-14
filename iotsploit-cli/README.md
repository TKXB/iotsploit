# iotsploit-cli

IoTSploit interactive CLI shell for IoT security testing.

## Overview

This package provides the `iotsploit` command-line shell built on top of `cmd2`.
It bundles the core console loop (`console.py`) and all command modules
(`commands/`) that implement device management, plugin execution, target
management, network operations, and more.

## Installation

```bash
pip install iotsploit-cli
```

## Usage

```bash
iotsploit
```

Or with the Django server started immediately:

```bash
iotsploit --runserver
```

### Custom plugins

`IOTSPLOIT_EXPLOIT_PLUGINS_DIR` can be used for user custom exploit plugins.
`IOTSPLOIT_DEVICE_PLUGINS_DIR` can be used for user custom device plugins.

## Command Palette

The IoTSploit shell includes a live command palette for all commands.  When
you type any character at the top-level interactive prompt, a menu appears
immediately showing every eligible command matching that prefix with a short
description beside each entry.

### How it works

1. Start typing any character at the empty prompt.
2. The menu lists all visible commands matching the typed prefix (e.g. `e`
   shows `edit`, `exploit`, `exit`, `execute_plugin`; `h` shows `help`,
   `history`).
3. Additional characters filter the list in real time (e.g. `ex` narrows to
   `exit`, `execute_plugin`, `exploit`).
4. Navigate the list, insert a selection, or dismiss the menu.

### Keyboard controls

| Key | Behavior |
|-----|----------|
| Any first-token character | Open the palette menu |
| Additional characters | Filter the list case-insensitively |
| Up / Down | Move selection without changing the buffer |
| Tab | Insert the selected command name (does not submit) |
| Enter | Accept the selected command and submit through cmd2 dispatch |
| Escape | Close the menu and retain the current input text |
| Backspace to empty | Close the menu |
| Space after a command | Close the menu and allow argument entry |
| Ctrl+C | Cancel the current input (normal shell behavior) |
| Ctrl+D on empty line | Exit the shell (normal EOF behavior) |

### Behaviour notes

- The palette is **TTY-only**.  Non-interactive use (piped input, startup
  scripts, non-TTY stdin) bypasses the palette entirely and uses the normal
  cmd2 input path.
- The command list is derived dynamically from the runtime command registry,
  so newly loaded command modules appear without editing the palette.
- Tab completion for arguments (after a space) still uses cmd2's existing
  completion engine, including argument-specific completers and argparse
  completers.
- Selecting a command from the palette does **not** execute it; it inserts the
  command name so you can type arguments before pressing Enter.

## License

GPL-3.0-or-later. See [LICENSE](../LICENSE) for details.
For commercial use, contact wang3919379@gmail.com.
