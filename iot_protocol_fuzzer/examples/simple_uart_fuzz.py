import logging
import sys

from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig

# Configure logging to show DEBUG level messages and payload details
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def print_payload_details(payload: bytes, case_num: int):
    """Print detailed information about the payload"""
    print(f"\n[Case {case_num}] Payload Details:")
    print(f"  Length: {len(payload)} bytes")
    print(f"  Hex: {payload.hex()}")
    print(f"  Raw: {repr(payload)}")
    # Try to show printable ASCII characters
    printable = ''.join(chr(b) if 32 <= b <= 126 else f'\\x{b:02x}' for b in payload)
    print(f"  ASCII: {printable}")
    print("-" * 50)

if __name__ == "__main__":
    # UART-specific seed corpus - common command patterns
    seeds = [
        b"AT\r\n",                    # AT command
        b"VERSION\r\n",               # Version query
        b"HELP\r\n",                  # Help command
        b"CONFIG\r\n",                # Configuration command
        b"\x00\x01\x02\x03\x04",     # Binary data
        b"GET /\r\n",                 # HTTP-like request
        b"USER admin\r\n",            # Login attempt
        b"RESET\r\n",                 # Reset command
    ]
    
    # Initialize Radamsa generator
    # Option 1: Use custom path (update this to your radamsa location)
    radamsa_path = "/home/tkxb/Projects/radamsa/bin/radamsa"
    # Option 2: Use system PATH (if radamsa is installed system-wide)
    # radamsa_path = "radamsa"
    
    gen = RadamsaGenerator(radamsa_path=radamsa_path)
    gen.seed_corpus = lambda: seeds  # type: ignore

    # Create UART harness with default settings
    # Default: /dev/ttyUSB0, 115200 baud, 0.1s timeout
    harness = UARTHarness()
    
    # You can also customize UART parameters:
    # from iot_protocol_fuzzer.interfaces.uart_interface import UARTInterface
    # uart_interface = UARTInterface(device="/dev/ttyUSB0", baudrate=9600, timeout=0.5)
    # harness = UARTHarness(interface=uart_interface)
    
    # Configure fuzzing campaign
    config = CampaignConfig(
        iterations=100,        # Reduced iterations for detailed viewing
        delay=0.5,            # Longer delay to see each payload
        save_crashes=True     # Save crash artifacts
    )
    
    # Create orchestrator
    orch = Orchestrator(gen, harness, config=config)
    
    print("Starting UART fuzzing campaign...")
    print("Target: /dev/ttyUSB0 at 115200 baud")
    print("Seeds: 8 different command patterns")
    print("Iterations: 10 (reduced for detailed viewing)")
    print("=" * 50)
    
    # Override the orchestrator run method to show payload details
    original_run = orch.run
    
    def detailed_run():
        logger = logging.getLogger("fuzzer.orchestrator")
        logger.info("Starting fuzzing campaign: %s iterations", config.iterations)
        seeds = gen.seed_corpus()
        corpus_iter = gen.generate(seeds, config.iterations)

        for idx, payload in enumerate(corpus_iter, 1):
            print_payload_details(payload, idx)
            
            result = harness.execute(payload)
            orch.logger_backend.record(idx, payload, result)
            orch.monitor.process_case(idx, payload, result)

            if result.crashed and config.save_crashes:
                orch.logger_backend.save_crash(idx, payload, result)
                print(f"🚨 CRASH DETECTED in Case {idx}!")
            elif result.timeout:
                print(f"⏰ TIMEOUT in Case {idx} (no response)")
            elif result.response:
                print(f"✅ Response received in Case {idx}: {result.response.hex()}")
            else:
                print(f"✅ Success in Case {idx} (no response expected)")

            if config.delay:
                import time
                time.sleep(config.delay)

        # Post-campaign summary
        orch.logger_backend.summary()
        logger.info("Fuzzing campaign finished.")
    
    orch.run = detailed_run
    
    try:
        orch.run()
    except KeyboardInterrupt:
        print("\nFuzzing campaign interrupted by user")
    except Exception as e:
        print(f"\nFuzzing campaign failed: {e}")
        print("Common issues:")
        print("- Check if /dev/ttyUSB0 exists and is accessible")
        print("- Verify device permissions (may need sudo)")
        print("- Ensure target device is connected and responding")
        print("- Try different baud rates if communication fails") 