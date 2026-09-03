# Writing Plugins

An exploit plugin subclasses `BasePlugin` and runs against a `Target`; a device
driver subclasses `BaseDeviceDriver` and owns a physical interface. Register
either as an entry point — `iotsploit.exploit_plugins` or
`iotsploit.device_drivers` — in its package's `pyproject.toml`, then
`poetry install`; an unregistered plugin fails invisibly. See
`docs/architecture.md` for the layout, `.agents/standards/testing.md` for tests.

## What a good plugin is

1. Answers one question, reusing the drivers, protocol packages, and privileged
   helper that exist rather than growing its own.
2. Declares what it takes and needs — `Parameters` and `REQUIRES` — instead of
   degrading quietly when something is missing.
3. Produces evidence: a failure never looks like an empty result, a measured
   value is never a copied declaration, a sample is never marked a census.
4. Is bounded and reversible: every loop has a limit, everything opened is
   closed in a `finally`, and it takes down only what it brought up.
5. Says what it does to the world, physical effects included — read-only
   software is not electrically inert.

## Exploit plugin

```python
hookimpl = pluggy.HookimplMarker("exploit_mgr")


class MyScanPlugin(BasePlugin):
    REQUIRES = ()  # "platform:linux", "module:can", "privileged-helper", "wifi"

    def __init__(self):
        super().__init__({
            'Name': 'My Scan',
            'Description': 'What it does, in one line.',
            'License': 'GPL',
            'Author': ['iotsploit'],
            'Parameters': {                      # type: str | int | bool | list
                'duration': {'type': 'int', 'required': False, 'default': 30,
                             'description': 'Seconds to run',
                             'validation': {'min': 1, 'max': 600}},
            },
        })

    @hookimpl
    def initialize(self, ctx=None):
        self.ctx = ctx          # cached once; per-run state belongs in execute

    @hookimpl
    def execute(self, target=None, parameters=None) -> ExploitResult:
        try:
            found = self._run(target, (parameters or {}).get('duration', 30))
        except ValueError as exc:            # bad input: say so, no traceback
            return ExploitResult(False, str(exc), {})
        finally:
            self._undo()                     # routes, links, sockets
        return ExploitResult(True, f"{len(found)} found.", {'found': found})
```

Long-running or streaming work implements `execute_async` returning
`AsyncExploitResult`, and awaits `ctx.interaction.a*` to prompt the operator.
`ctx` also carries `wifi` and `has_interaction`; `iotsploit_priv.call` runs
root-only actions, `iotsploit_protocols` holds the CAN/DoIP/UDS/SOME-IP codecs.
Pluggy rejects a hookimpl whose argument names are not in the hookspec, and a
blocking `request()` inside `execute_async` raises — use `arequest`.

## Reading the target

`target` is a model (Django) or a plain dict (MCP, CLI, tests) — read both:

```python
def _target_ip(target):
    if isinstance(target, dict):
        return str(target.get('ip_address') or '').strip()
    return str(getattr(target, 'ip_address', '') or '').strip()
```

Fields: `target_id`, `name`, `type`, `ip_address`, `properties`; a vehicle adds
`buses[]`, `edges[]`, and `components[]` each carrying `facets{}`. Prefer an
existing reader (`TargetCanCatalog.from_target`) to walking components. A
missing target or field is an input error, never a default.

## Recording observations

Optional pair. The manager opens a scan per declared scope before the run, so a
crash records as a failed scan rather than as silence.

```python
def observation_scopes(self, target, parameters):
    ip = _target_ip(target)                    # [] records nothing
    return [ObservationScope(scope_key=f"host:{ip}")] if ip else []

def observation_batches(self, result):
    key = (getattr(result, 'data', None) or {}).get('scope_key')
    if not key:                                # gate on this, not on success
        return []
    facts = [Fact(protocol='tcp', subject_kind='port', subject_id='22',
                  observed_property='state', value='open')]
    return [ObservationBatch(scope_key=key, facts=facts, is_complete=True)]
```

Scope decides comparability — a fast and a full scan are different scopes, and
no credential belongs in `scope_key`. `is_complete=True` is a census and clears
prior state; a time-boxed sample is `False`. Every declared scope must return a
batch or it is recorded failed, ids must be canonical (`"0x123"` and `"123"`
never reconcile), and `subject_kind='self'` takes `subject_id=None`.
`ExploitResult.data` is the response and is not persisted; facts are.

## Device driver

Implement the lifecycle and set `self.supported_commands`; the base class wires
the rest.

```python
_scan_impl() -> List[Device]     # then initialize, connect, command, reset, close
_initialize_impl(device) -> bool
_connect_impl(device) -> bool
_command_impl(device, command, args=None) -> Optional[str]
_reset_impl(device) -> bool
_close_impl(device) -> bool
```

For continuous data add `_setup_acquisition` / `_acquisition_loop` /
`_cleanup_acquisition` and broadcast `StreamData`; streaming is already wired.

## Test

Take the highest rung and say which: real hardware on the rig (`hardware`), a
virtual device (`vcan0`, `os.openpty()`, a loopback listener), or a fake at the
transport seam (`test_drv_socketcan.py`). Add a `contract` test that the entry
point loads and a `django` test through `POST /api/execute_plugin/` — coercion
and serialization happen only there. Mark every file with `pytestmark`.

```bash
tools/testing/test-python-full.sh   # the gate, before commit
poetry run pytest -m hardware       # on the rig, before claiming it works
```
