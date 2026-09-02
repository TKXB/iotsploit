import cmd2

from iotsploit_cli.commands import priv_commands
from iotsploit_cli.commands.priv_commands import PrivCommands
from iotsploit_priv.native import NativeStatus


class PrivShell(cmd2.Cmd, PrivCommands):
    pass


def test_priv_verbs_lists_only_the_four_bounded_operations(capsys):
    shell = PrivShell()

    shell.onecmd_plus_hooks("priv verbs")

    output = capsys.readouterr().out
    assert "can-up:" in output
    assert "can-link-state:" in output
    assert "doip-config:" in output
    assert "route-via:" in output
    assert shell.last_result == 0


def test_priv_status_preserves_documented_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(priv_commands, "native_status", lambda _user: NativeStatus(2, ("broken",)))
    shell = PrivShell()

    shell.onecmd_plus_hooks("priv status --service-user sat")

    assert "broken" in capsys.readouterr().err
    assert shell.last_result == 2


def test_priv_install_requires_explicit_confirmation(monkeypatch):
    monkeypatch.setattr(priv_commands.os.path, "exists", lambda _path: False)
    shell = PrivShell()
    monkeypatch.setattr(shell, "read_input", lambda _prompt: "no")

    shell.onecmd_plus_hooks("priv install")

    assert shell.last_result == 1
