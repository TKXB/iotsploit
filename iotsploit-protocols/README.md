# iotsploit-protocols

Wire-protocol clients for IoTSploit: SOME/IP today, DoIP/UDS next.

Nothing in this package reads a database, a config file, an environment
variable, or the current target, and nothing runs `sudo` or prompts a human. A
client is built from an explicit config object supplied by the caller. That is
what lets it run under Celery, under MCP, in a test, or from a plugin — and what
keeps one lab bench's IP addresses out of a library.

scapy is used as a **codec, not as a socket**: packets are built and parsed with
`scapy.contrib.automotive`, but I/O happens on ordinary sockets, so calling a
method needs no root.

## SOME/IP

Call a method:

```python
from iotsploit_protocols.someip import SomeIpClient, SomeIpConfig

with SomeIpClient(SomeIpConfig(host="198.18.34.10", port=30509)) as client:
    response = client.call(service=0x1234, instance=0x0001, method=0x0002, payload=b"\x01")
    if response.ok:
        print(response.payload.hex())
    else:
        print("refused:", response.return_code_name)
```

Fire-and-forget:

```python
client.notify(service=0x1234, instance=0x0001, method=0x0003, payload=b"\x07")
```

Hear what a segment announces — passive, no traffic generated, no root:

```python
from iotsploit_protocols.someip import ServiceDiscovery, SdConfig

sd = ServiceDiscovery(SdConfig(group="224.244.224.245", interface="eth0"))
for offer in sd.listen(timeout=10.0):
    print(offer.canonical_id, offer.endpoints)   # "1234:0001" [('198.18.34.10', 30509, 'tcp')]
```

`canonical_id` is the form observations store as `subject_id`, so a discovered
service joins against the reference catalog without any string munging at the
call site.

## Configuration from a target

Inside the IoTSploit app, don't build the config by hand — the Django binding
layer resolves it from the current target's `someip` facet and component
address:

```python
from iotsploit_django.adapters.django.protocol_binding import someip_client_for

with someip_client_for("TCAM") as client:
    ...
```

An unconfigured target raises `NotConfigured` rather than falling back to a
built-in address, because a helper that guesses a host probes whatever is at
that address and reports its silence as a finding.

## Errors

| exception | meaning |
|---|---|
| `NotConfigured` | settings are missing — fix the target, not the code |
| `NegativeResponse` | the peer answered and said no |
| `ProtocolError` | malformed or unmatchable traffic |

Transport failures are left as stdlib `ConnectionError` / `TimeoutError` rather
than re-spelled in a new namespace.

## Tests

```bash
poetry run pytest iotsploit-protocols/tests
```

No hardware and no network: loopback servers stand in for ECUs.
