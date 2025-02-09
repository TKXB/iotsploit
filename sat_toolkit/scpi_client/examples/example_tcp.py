"""Example of using SCPI client with TCP transport."""

from sat_toolkit.scpi_client import ScpiClient, ScpiTcpTransport


def main():
    # Create TCP transport
    transport = ScpiTcpTransport(
        host="192.168.1.100",  # Replace with your instrument's IP
        port=5025,             # Common SCPI port, adjust as needed
        timeout=1.0
    )
    
    # Create SCPI client
    client = ScpiClient(transport)
    
    try:
        # Connect to instrument
        client.connect()
        
        # Get instrument identification
        idn = client.identify()
        print(f"Connected to instrument: {idn}")
        
        # Example commands
        client.send_command("*CLS")  # Clear status
        client.send_command("*RST")  # Reset instrument
        
        # Example measurement
        voltage = client.query("MEAS:VOLT:DC?")
        print(f"Measured voltage: {voltage}V")
        
    finally:
        # Always disconnect properly
        client.disconnect()


if __name__ == "__main__":
    main() 