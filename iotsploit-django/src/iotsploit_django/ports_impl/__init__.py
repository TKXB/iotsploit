"""Django adapters implementing `iotsploit_core.ports.*`.

Stage-4: this package provides a stable import surface for the host app. The
current implementations may wrap legacy `sat_toolkit` adapters, but the import
direction is now explicit: iotsploit-django -> ports_impl -> (adapters).
"""


