"""
Example of using the SCPI client with Serial transport.

This example demonstrates:
  - Connecting to a SCPI device via a serial port.
  - Querying version and status (using SYSTem:VERSion? and SYSTem:STATus?).
  - Sending commands *CLS (clear) and *RST (reset).
  - Querying WiFi AP SSID and scanning for available APs.
  - Properly closing the connection.

Example output:
    Connecting to SCPI device...
    Connection established.
    Device Version: 1.0.0
    Device Status: READY
    Clearing device status with *CLS...
    Resetting device with *RST...

    Querying WiFi AP SSID...
    WiFi AP SSID: ManagementAP

    Scanning for available WiFi APs...
    (This may take up to 10 seconds...)
    Available WiFi APs:

    Found 5 access points:
    ------------------------------------------------------------
    SSID                     RSSI  Channel Security       
    ------------------------------------------------------------
    ASUS                  -30 dBm        7 WPA2_PSK       
    1902                  -66 dBm        1 WPA_WPA2_PSK   
    CMCC-DucF             -72 dBm        1 WPA_WPA2_PSK   
    hcc180602             -73 dBm        6 WPA2_PSK       
    NARWAL-9C2E           -76 dBm        2 WPA2_PSK       
    ------------------------------------------------------------
"""

from sat_toolkit.scpi_client.transport import ScpiSerialTransport
from sat_toolkit.scpi_client.client import ScpiClient
import time

def get_auth_mode_str(auth_mode):
    """Convert auth mode number to string description."""
    auth_modes = {
        0: "OPEN",
        1: "WEP",
        2: "WPA_PSK",
        3: "WPA2_PSK",
        4: "WPA_WPA2_PSK",
        5: "WPA2_ENTERPRISE",
        6: "WPA3_PSK",
        7: "WPA2_WPA3_PSK"
    }
    return auth_modes.get(int(auth_mode), f"UNKNOWN({auth_mode})")

def main():
    # Create Serial transport. Update the port and baudrate as needed.
    transport = ScpiSerialTransport(
        port="/dev/ttyUSB1",  # Replace with your actual serial port
        baudrate=115200,
        timeout=1.0
    )
    
    # Create SCPI client using the transport
    client = ScpiClient(transport)
    
    try:
        print("Connecting to SCPI device...")
        client.connect()
        print("Connection established.")
        
        # Query device version using 'SYSTem:VERSion?'
        version = client.get_version()  # Expects the SCPI server to return version info (e.g., "1.0.0")
        print(f"Device Version: {version}")
        
        # Query device status using 'SYSTem:STATus?'
        status = client.get_status()  # Expects the SCPI server to return status (e.g., "READY")
        print(f"Device Status: {status}")
        
        # Clear device status using the SCPI *CLS command.
        print("Clearing device status with *CLS...")
        client.send_command("*CLS")
        time.sleep(0.1)  # slight delay if needed
        
        # Reset the device using *RST command.
        print("Resetting device with *RST...")
        client.send_command("*RST")
        time.sleep(0.1)
        
        # Query WiFi AP SSID
        print("\nQuerying WiFi AP SSID...")
        ap_ssid = client.query("WIFi:AP:SSID?")
        print(f"WiFi AP SSID: {ap_ssid}")
        
        # Query available WiFi APs
        print("\nScanning for available WiFi APs...")
        print("(This may take up to 10 seconds...)")
        
        # Send scan command and wait for results with longer timeout
        ap_list = client.query("WIFi:AP:LIST?", timeout=10.0)  # Increase timeout to 10 seconds
        
        # If first attempt returns empty, try again after a delay
        if not ap_list:
            print("Waiting for scan results...")
            time.sleep(3)  # Wait for 3 seconds
            ap_list = client.query("WIFi:AP:LIST?", timeout=10.0)  # Try again
        
        print("Available WiFi APs:")
        
        if ap_list and ap_list != "NO_AP_FOUND" and not ap_list.startswith("ERROR"):
            # Split the response into individual AP entries and filter out empty ones
            ap_entries = [ap for ap in ap_list.strip().split(';') if ap]
            
            if ap_entries:
                print("\nFound {} access points:".format(len(ap_entries)))
                print("-" * 60)
                print("{:<20} {:>8} {:>8} {:<15}".format("SSID", "RSSI", "Channel", "Security"))
                print("-" * 60)
                
                for ap in ap_entries:
                    try:
                        ssid, rssi, channel, auth = ap.split(',')
                        print("{:<20} {:>8} {:>8} {:<15}".format(
                            ssid,
                            f"{rssi} dBm",
                            channel,
                            get_auth_mode_str(auth)
                        ))
                    except ValueError as e:
                        print(f"Error parsing AP entry: {ap} - {str(e)}")
                
                print("-" * 60)
            else:
                print("No access points found in scan results")
        else:
            print(f"Scan result: {ap_list}")
        
    except Exception as e:
        print(f"Exception during SCPI communication: {e}")
    finally:
        print("Closing connection to SCPI device...")
        client.close()  # Close the underlying transport connection
        print("Connection closed.")

if __name__ == "__main__":
    main() 