from enum import Enum
from typing import Optional, Callable, Dict, Any


class EventType(Enum):
    """Event types for fuzzer callbacks"""
    CAMPAIGN_STARTED = "campaign_started"
    CAMPAIGN_PAUSED = "campaign_paused"
    CAMPAIGN_RESUMED = "campaign_resumed"
    CAMPAIGN_STOPPED = "campaign_stopped"
    CAMPAIGN_COMPLETED = "campaign_completed"
    TEST_CASE_STARTED = "test_case_started"
    TEST_CASE_COMPLETED = "test_case_completed"
    CRASH_DETECTED = "crash_detected"
    STATISTICS_UPDATE = "statistics_update"
    PROGRESS_UPDATE = "progress_update"
    # A payload the ledger has seen before now does something else. Not
    # necessarily a bug -- a behaviour change that wants a human to say
    # whether it was intended.
    BOUNDARY_MOVED = "boundary_moved"
    # An outcome signature this target has never produced. The corpus grew.
    NEW_REGION = "new_region"
    # Replays of the same payload disagreed. Reported, never promoted: a
    # corpus built from results that do not reproduce is a corpus of noise.
    FLAKY_OUTCOME = "flaky_outcome"


class CampaignConfig:
    """Configuration object for fuzzing campaigns"""

    def __init__(
        self,
        iterations: int = 100,
        delay: float = 0.0,
        save_crashes: bool = True,
        event_callback: Optional[Callable[[EventType, Dict[str, Any]], None]] = None,
    ):
        self.iterations = iterations
        self.delay = delay  # seconds between test cases
        self.save_crashes = save_crashes
        self.event_callback = event_callback 