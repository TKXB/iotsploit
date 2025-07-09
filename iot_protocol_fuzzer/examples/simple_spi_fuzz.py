import logging

from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
from iot_protocol_fuzzer.harnesses.spi_harness import SPIHarness
from iot_protocol_fuzzer.interfaces.spi_interface import SPIInterface
from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    # SPI-specific seed corpus - common patterns for SPI devices
    seeds = [
        b"\x00",                      # NOP command
        b"\x01\x00",                  # Read command
        b"\x02\x00\xff",              # Write command
        b"\x03",                      # Status command
        b"\x04\x00\x00\x00",          # Erase command
        b"\x05",                      # Read ID
        b"\x06",                      # Write enable
        b"\x07",                      # Write disable
        b"\x08\x00\x00\x00\x00",      # Read with address
        b"\x09\x00\x00\x00\xaa",      # Write with data
        b"\xff\xff\xff\xff",          # All high bits
        b"\x00\x00\x00\x00",          # All low bits
        b"\xaa\x55\xaa\x55",          # Alternating pattern
        b"\x5a\xa5\x5a\xa5",          # Inverted alternating
    ]
    
    # Initialize Radamsa generator
    # Option 1: Use custom path (update this to your radamsa location)
    radamsa_path = "/home/tkxb/Projects/radamsa/bin/radamsa"
    # Option 2: Use system PATH (if radamsa is installed system-wide)
    # radamsa_path = "radamsa"
    
    gen = RadamsaGenerator(radamsa_path=radamsa_path)
    gen.seed_corpus = lambda: seeds  # type: ignore

    # Create SPI interface with custom settings
    # Default: bus=0, device=0, 500kHz
    spi_interface = SPIInterface(
        bus=0,                        # SPI bus number
        device=0,                     # Device select (CS0)
        max_speed_hz=500000          # 500kHz SPI clock
    )
    
    # Create SPI harness
    harness = SPIHarness(interface=spi_interface)
    
    # You can also use default settings:
    # harness = SPIHarness()
    
    # Configure fuzzing campaign
    config = CampaignConfig(
        iterations=150,        # Moderate iterations for SPI
        delay=0.01,           # Fast SPI communication
        save_crashes=True     # Save crash artifacts
    )
    
    # Create and run orchestrator
    orch = Orchestrator(gen, harness, config=config)
    
    print("Starting SPI fuzzing campaign...")
    print("Target: SPI bus 0, device 0")
    print("Clock: 500kHz")
    print("Seeds: 14 different command patterns")
    print("Iterations: 150")
    print("=" * 50)
    
    try:
        orch.run()
    except KeyboardInterrupt:
        print("\nFuzzing campaign interrupted by user")
    except Exception as e:
        print(f"\nFuzzing campaign failed: {e}")
        print("Common issues:")
        print("- Check if SPI is enabled (raspi-config on RPi)")
        print("- Verify device permissions (may need sudo)")
        print("- Ensure SPI device is connected properly")
        print("- Check SPI bus and device numbers")
        print("- Install spidev: pip install spidev")
        print("- SPI is typically Linux-only")
    finally:
        # Cleanup SPI interface
        try:
            spi_interface.close()
        except:
            pass 