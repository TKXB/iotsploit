# Architecture

This project follows **ports and adapters** (hexagonal). One rule:

> Dependencies point inward. `iotsploit-core` defines interfaces; other packages
> implement them. Core never imports Django, Celery, Channels, Redis, or
> OS-specific libraries.

## Layout

- `iotsploit-core/src/iotsploit_core/domain/` — entities, no I/O
- `iotsploit-core/src/iotsploit_core/ports/` — interfaces (`typing.Protocol`)
- `iotsploit-core/src/iotsploit_core/core/` — services orchestrating domain via ports
- `iotsploit-{django,cli,platforms,mcp}/.../adapters/` — concrete implementations

Ports: `TaskRunner`, `PluginMetaRepository`, `PluginGroupRepository`,
`DriverStateRepository`, `StreamBackend`, `WifiBackend`, `InteractionPort`,
`ObservationProducer`/`ObservationSink`.

Adapters are selected only in composition roots
(`iotsploit_django/composition_root/core_container.py`,
`iotsploit_mcp/composition_root.py`). Core never picks its own adapter.
