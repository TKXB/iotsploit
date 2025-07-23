import logging

from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
from iot_protocol_fuzzer.harnesses.can_harness import CANHarness
from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig

# Configure logging to show detailed CAN data
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set specific logger levels
logging.getLogger("can.interface").setLevel(logging.DEBUG)
logging.getLogger("fuzzer.monitor").setLevel(logging.WARNING)
logging.getLogger("fuzzer.orchestrator").setLevel(logging.INFO)

if __name__ == "__main__":
    seeds = [b"\x00\x01\x02\x03"]
    
    # Initialize Radamsa generator
    # Option 1: Use custom path (update this to your radamsa location)
    radamsa_path = "/home/tkxb/Projects/radamsa/bin/radamsa"
    # Option 2: Use system PATH (if radamsa is installed system-wide)
    # radamsa_path = "radamsa"
    
    gen = RadamsaGenerator(radamsa_path=radamsa_path)
    gen.seed_corpus = lambda: seeds  # type: ignore

    harness = CANHarness()
    orch = Orchestrator(gen, harness, config=CampaignConfig(iterations=100))
    orch.run() 