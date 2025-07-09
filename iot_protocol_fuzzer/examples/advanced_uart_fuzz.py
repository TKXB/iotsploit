import logging
import time

from iot_protocol_fuzzer.generators.radamsa_generator import RadamsaGenerator
from iot_protocol_fuzzer.harnesses.uart_harness import UARTHarness
from iot_protocol_fuzzer.interfaces.uart_interface import UARTInterface
from iot_protocol_fuzzer.core.orchestrator import Orchestrator, CampaignConfig

# Configure detailed logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('uart_fuzz.log'),
        logging.StreamHandler()
    ]
)

def create_at_command_seeds():
    """Generate AT command seed corpus for modem/cellular devices."""
    return [
        b"AT\r\n",
        b"AT+CGMI\r\n",      # Get manufacturer
        b"AT+CGMM\r\n",      # Get model
        b"AT+CGMR\r\n",      # Get revision
        b"AT+CGSN\r\n",      # Get serial number
        b"AT+CIMI\r\n",      # Get IMSI
        b"AT+CCID\r\n",      # Get SIM card ID
        b"AT+CREG?\r\n",     # Registration status
        b"AT+COPS?\r\n",     # Operator selection
        b"AT+CSQ\r\n",       # Signal quality
        b"AT+CMGF=1\r\n",    # SMS text mode
        b"AT+CNMI=2,1\r\n",  # SMS notification
    ]

def create_protocol_seeds():
    """Generate protocol-specific seed corpus."""
    return [
        # HTTP-like requests
        b"GET / HTTP/1.1\r\n\r\n",
        b"POST /api HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
        
        # Common IoT protocols
        b"PING\r\n",
        b"PONG\r\n",
        b"HELLO\r\n",
        b"STATUS\r\n",
        b"REBOOT\r\n",
        
        # Binary protocols
        b"\x02\x00\x00\x00\x04test\x03",  # STX/ETX framed
        b"\xff\xfe\x00\x00",              # Magic bytes
        b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f",
        
        # Configuration commands
        b"CONFIG SET baudrate 9600\r\n",
        b"CONFIG GET version\r\n",
        b"CONFIG SAVE\r\n",
        b"CONFIG RESET\r\n",
    ]

def create_malformed_seeds():
    """Generate malformed/edge case seeds."""
    return [
        b"A" * 1024,          # Buffer overflow attempt
        b"A" * 4096,          # Large buffer
        b"\x00" * 100,        # Null bytes
        b"\xff" * 100,        # 0xFF bytes
        b"\r\n" * 50,         # Many line endings
        b"\x00\r\n\x00",      # Mixed null and CRLF
        b"%" + b"A" * 100,    # Format string attempt
        b"/../" * 20,         # Directory traversal
        b"SELECT * FROM",     # SQL injection attempt
        b"<script>alert(1)</script>",  # XSS attempt
    ]

def main():
    # Choose seed corpus type
    seed_type = "at_commands"  # Options: "at_commands", "protocols", "malformed", "all"
    
    if seed_type == "at_commands":
        seeds = create_at_command_seeds()
        print("Using AT command seed corpus")
    elif seed_type == "protocols":
        seeds = create_protocol_seeds()
        print("Using protocol seed corpus")
    elif seed_type == "malformed":
        seeds = create_malformed_seeds()
        print("Using malformed/edge case seed corpus")
    else:  # all
        seeds = create_at_command_seeds() + create_protocol_seeds() + create_malformed_seeds()
        print("Using combined seed corpus")
    
    # Initialize Radamsa generator
    # Option 1: Use custom path (update this to your radamsa location)
    radamsa_path = "/home/tkxb/Projects/radamsa/bin/radamsa"
    # Option 2: Use system PATH (if radamsa is installed system-wide)
    # radamsa_path = "radamsa"
    
    gen = RadamsaGenerator(radamsa_path=radamsa_path)
    gen.seed_corpus = lambda: seeds  # type: ignore

    # Create UART interface with custom settings
    uart_interface = UARTInterface(
        device="/dev/ttyUSB0",  # Change this to your device
        baudrate=115200,        # Common baud rates: 9600, 38400, 115200
        timeout=0.5             # Longer timeout for slow devices
    )
    
    # Create UART harness
    harness = UARTHarness(interface=uart_interface)
    
    # Configure fuzzing campaign
    config = CampaignConfig(
        iterations=500,         # More comprehensive testing
        delay=0.05,            # Shorter delay for faster testing
        save_crashes=True      # Save crash artifacts
    )
    
    # Create orchestrator
    orch = Orchestrator(gen, harness, config=config)
    
    # Display campaign information
    print("=" * 60)
    print("UART Protocol Fuzzer - Advanced Demo")
    print("=" * 60)
    print(f"Target Device: {uart_interface.ser.port}")
    print(f"Baud Rate: {uart_interface.ser.baudrate}")
    print(f"Timeout: {uart_interface.ser.timeout}s")
    print(f"Seed Corpus: {len(seeds)} seeds")
    print(f"Total Iterations: {config.iterations}")
    print(f"Delay Between Tests: {config.delay}s")
    print("=" * 60)
    
    # Pre-flight checks
    print("Performing pre-flight checks...")
    try:
        # Test basic communication
        harness.execute(b"AT\r\n")
        print("✓ Device communication OK")
    except Exception as e:
        print(f"✗ Device communication failed: {e}")
        print("Please check:")
        print("- Device is connected and powered")
        print("- Correct device path (/dev/ttyUSB0)")
        print("- Proper permissions (may need sudo)")
        print("- Correct baud rate")
        return
    
    print("\nStarting fuzzing campaign...")
    start_time = time.time()
    
    try:
        orch.run()
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("Fuzzing campaign interrupted by user")
    except Exception as e:
        print(f"\n" + "=" * 60)
        print(f"Fuzzing campaign failed: {e}")
        print("\nTroubleshooting:")
        print("- Check device connection")
        print("- Verify baud rate settings")
        print("- Ensure device is responsive")
        print("- Check for hardware issues")
    finally:
        # Cleanup
        try:
            uart_interface.close()
        except:
            pass
        
        elapsed_time = time.time() - start_time
        print(f"\nCampaign duration: {elapsed_time:.2f} seconds")
        print("Check 'artifacts/' directory for test results")
        print("Check 'uart_fuzz.log' for detailed logs")

if __name__ == "__main__":
    main() 