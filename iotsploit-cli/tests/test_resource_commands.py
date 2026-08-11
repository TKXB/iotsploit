"""Contract tests for the canonical resource/action command surface."""

import cmd2
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from iotsploit_cli.command_palette import (
    Cmd2CompletionAdapter,
    CommandCatalog,
    CommandPaletteCompleter,
)
from iotsploit_cli.command_registry import LEGACY_REPLACEMENTS, RESOURCE_SPECS
from iotsploit_cli.commands.resource_commands import ResourceCommands


class ResourceShell(cmd2.Cmd, ResourceCommands):
    """Small shell that records calls made by compatibility adapters."""

    def __init__(self):
        super().__init__()
        self._canonical_command_registry = True
        self.calls = []

    def _record(self, name, argument):
        self.calls.append((name, argument))

    def do_list_devices(self, argument):
        self._record("list_devices", argument)

    def do_execute_device_command(self, argument):
        self._record("execute_device_command", argument)

    def do_add_firmware(self, argument):
        self._record("add_firmware", argument)

    def do_execute_plugin(self, argument):
        self._record("execute_plugin", argument)

    def do_flash_firmware(self, argument):
        self._record("flash_firmware", argument)

    def complete_firmware(self, text, line, begidx, endidx):
        """Stand-in for a cmd2 argument completer on the legacy command."""
        return [name for name in ("esp32_blink", "esp32_wifi") if name.startswith(text)]


def _completions(shell, text):
    completer = CommandPaletteCompleter(shell, CommandCatalog(shell), Cmd2CompletionAdapter(shell))
    document = Document(text=text, cursor_position=len(text))
    event = CompleteEvent(text_inserted=False, completion_requested=True)
    return list(completer.get_completions(document, event))


def test_registry_has_unique_resources_and_legacy_names():
    resource_names = [resource.name for resource in RESOURCE_SPECS]
    assert len(resource_names) == len(set(resource_names))
    all_legacy = [
        legacy
        for resource in RESOURCE_SPECS
        for action in resource.actions
        for legacy in action.legacy_commands
    ]
    assert len(all_legacy) == len(set(all_legacy))
    assert set(all_legacy).issubset(LEGACY_REPLACEMENTS)


def test_device_actions_dispatch_to_existing_handlers():
    shell = ResourceShell()
    shell.onecmd_plus_hooks("device list")
    shell.onecmd_plus_hooks("device run AT Z")
    assert shell.calls == [
        ("list_devices", ""),
        ("execute_device_command", "AT Z"),
    ]


def test_firmware_adapter_preserves_paths_with_spaces():
    shell = ResourceShell()
    shell.onecmd_plus_hooks("firmware add demo '/tmp/a b.bin' esp32 1.0")
    assert shell.calls == [
        ("add_firmware", "demo '/tmp/a b.bin' esp32 1.0"),
    ]


def test_palette_only_shows_canonical_top_level_commands():
    shell = ResourceShell()
    catalog = CommandCatalog(shell)
    names = [entry.name for entry in catalog.get_eligible_entries("d")]
    assert names == ["device", "driver"]
    assert "device_info" not in names


def test_palette_completes_resource_actions_while_typing():
    shell = ResourceShell()
    catalog = CommandCatalog(shell)
    completer = CommandPaletteCompleter(shell, catalog, Cmd2CompletionAdapter(shell))
    document = Document(text="device s", cursor_position=8)
    event = CompleteEvent(text_inserted=True, completion_requested=False)
    completions = list(completer.get_completions(document, event))
    assert [completion.text for completion in completions] == ["scan", "select"]
    assert all(completion.start_position == -1 for completion in completions)


def test_palette_lists_actions_after_resource_space():
    shell = ResourceShell()
    catalog = CommandCatalog(shell)
    names = [entry.name for entry in catalog.get_context_entries("plugin ")]
    assert names == ["list", "refresh", "run", "run-all"]


def test_palette_handles_empty_input_without_raising():
    """Empty input has no last word; the completer must not IndexError."""
    shell = ResourceShell()
    assert _completions(shell, "") == []
    assert CommandCatalog(shell).get_context_entries("") == []


def test_palette_delegates_argument_completion_to_cmd2():
    """Past `resource action`, cmd2 keeps owning completion."""
    shell = ResourceShell()
    completions = _completions(shell, "firmware flash esp")
    assert [completion.text for completion in completions] == ["esp32_blink", "esp32_wifi"]
