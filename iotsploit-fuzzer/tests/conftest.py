"""Load IoTSploit's target pack.

The registry is empty until a pack is imported -- that is what lets another
application use this engine without IoTSploit's targets coming along. The
tests here are about IoTSploit's, so they import its pack once.
"""

import iotsploit_fuzzer.targets.iotsploit  # noqa: F401  - imported for its register() calls
