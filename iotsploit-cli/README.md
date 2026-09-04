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

Choose the backend and MCP listening addresses when the defaults are not suitable:

```bash
iotsploit --runserver \
  --host 0.0.0.0 --api-port 8080 --ws-port 8081 \
  --mcp-host 127.0.0.1 --mcp-port 9901
```

The same options are available inside the shell:

```text
<IoX_SHELL> service start --host 0.0.0.0 --api-port 8080 --ws-port 8081
```

`--host` controls the API and WebSocket listeners. MCP remains on loopback by
default because it does not authenticate incoming requests; expose it only on
a protected network. All ports must be distinct.

### Custom plugins

`IOTSPLOIT_EXPLOIT_PLUGINS_DIR` can be used for user custom exploit plugins.
`IOTSPLOIT_DEVICE_PLUGINS_DIR` can be used for user custom device plugins.

## Command standard

Application commands use a predictable `resource action` grammar:

```text
device list
driver status
firmware flash <firmware> <device>
plugin run <plugin>
target export [file]
service status
```

The top-level resources are `host`, `device`, `driver`, `firmware`, `plugin`,
`target`, `service`, `wifi`, and `config`. Run `help` for the concise public
surface, `help <resource>` for its actions, or `help --all` for advanced cmd2
commands and the legacy-name migration table.

Previous command names and abbreviations remain executable during the
migration. They print a deprecation warning with the canonical replacement.

## Command Palette

The IoTSploit shell includes a live command palette for the canonical command
surface. When you type at the top-level prompt, a menu shows matching resources
with a short explanation. After a resource and a space, it shows that
resource's actions.

### How it works

1. Start typing any character at the empty prompt.
2. The menu lists canonical resources and essential shell commands matching
   the typed prefix (for example, `d` shows `device` and `driver`).
3. Type a resource and a space to see its actions (for example, `plugin `
   shows `list`, `run`, `run-all`, and `refresh`).
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
| Space after a resource | Show the resource's actions |
| Space after `service start` | Show the available endpoint options |
| Space after another action | Close the menu and allow argument entry |
| Ctrl+C | Cancel the current input (normal shell behavior) |
| Ctrl+D on empty line | Exit the shell (normal EOF behavior) |

### Behaviour notes

- The palette is **TTY-only**.  Non-interactive use (piped input, startup
  scripts, non-TTY stdin) bypasses the palette entirely and uses the normal
  cmd2 input path.
- The command list comes from the same canonical registry as help and the
  argparse command definitions, so names and explanations stay aligned.
- Tab completion for arguments (after a space) still uses cmd2's existing
  completion engine, including argument-specific completers and argparse
  completers.
- Selecting a command from the palette does **not** execute it; it inserts the
  command name so you can type arguments before pressing Enter.

## License

GPL-3.0-or-later. See [LICENSE](../LICENSE) for details.
For commercial use, contact wang3919379@gmail.com.
