#!/usr/bin/env python3
"""
Safe Test Script for NetworkManager WiFi Backend

This script provides safe, interactive testing of the Linux WiFi Backend
without disrupting existing network connections.

Usage:
    python test_wifi_backend_safe.py [--interface wlan0]
"""

import argparse
import logging
import sys
import time
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from iotsploit_platforms.adapters.platforms.linux.wifi_backend import LinuxWifiBackend
    from iotsploit_core.utils.exceptions import NotSupportedError
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure you're in the correct environment and dependencies are installed.")
    sys.exit(1)


class SafeWiFiTester:
    """Safe WiFi Backend Tester with interactive prompts."""
    
    def __init__(self, interface: str = "wlan0"):
        """Initialize tester with WiFi interface."""
        self.interface = interface
        self.backend: Optional[LinuxWifiBackend] = None
        self.original_connection_state = None
        
    def print_header(self, title: str):
        """Print a formatted header."""
        print("\n" + "=" * 60)
        print(f"  {title}")
        print("=" * 60)
    
    def print_success(self, message: str):
        """Print success message."""
        print(f"✅ {message}")
    
    def print_error(self, message: str):
        """Print error message."""
        print(f"❌ {message}")
    
    def print_warning(self, message: str):
        """Print warning message."""
        print(f"⚠️  {message}")
    
    def print_info(self, message: str):
        """Print info message."""
        print(f"ℹ️  {message}")
    
    def confirm_action(self, message: str) -> bool:
        """Ask user to confirm an action."""
        response = input(f"\n{message} (yes/no): ").strip().lower()
        return response in ('yes', 'y')
    
    def test_initialization(self) -> bool:
        """Test 1: Initialize backend."""
        self.print_header("Test 1: Backend Initialization")
        
        try:
            self.print_info(f"Initializing WiFi backend for interface: {self.interface}")
            self.backend = LinuxWifiBackend(wifi_iface_name=self.interface)
            self.print_success(f"Backend initialized successfully!")
            self.print_info(f"Hardware address: {self.backend._device.get_hw_address()}")
            self.print_info(f"Device state: {self.backend._device.get_state().value_nick}")
            return True
        except NotSupportedError as e:
            self.print_error(f"Initialization failed: {e}")
            return False
        except Exception as e:
            self.print_error(f"Unexpected error during initialization: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_scan(self) -> bool:
        """Test 2: Scan for networks (read-only, safe)."""
        self.print_header("Test 2: Network Scanning (Safe - Read Only)")
        
        if not self.backend:
            self.print_error("Backend not initialized. Run test_initialization() first.")
            return False
        
        try:
            self.print_info("Starting network scan...")
            networks = self.backend.scan()
            
            if networks:
                self.print_success(f"Scan completed! Found {len(networks)} networks:")
                print("\n" + "-" * 60)
                print(f"{'SSID':<30} {'Signal':<10} {'Security':<10} {'BSSID'}")
                print("-" * 60)
                for net in networks[:10]:  # Show first 10
                    ssid = net.get('ssid', '')[:28]
                    signal = f"{net.get('signal', 0)}%"
                    security = net.get('security', 'UNKNOWN')
                    bssid = net.get('bssid', 'N/A')
                    print(f"{ssid:<30} {signal:<10} {security:<10} {bssid}")
                if len(networks) > 10:
                    print(f"... and {len(networks) - 10} more networks")
                print("-" * 60)
                return True
            else:
                self.print_warning("Scan completed but no networks found.")
                return True  # Still a success, just no networks
                
        except Exception as e:
            self.print_error(f"Scan failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_status(self) -> bool:
        """Test 3: Get status (read-only, safe)."""
        self.print_header("Test 3: Status Query (Safe - Read Only)")
        
        if not self.backend:
            self.print_error("Backend not initialized. Run test_initialization() first.")
            return False
        
        try:
            self.print_info("Querying WiFi status...")
            status = self.backend.status()
            
            self.print_success("Status retrieved successfully!")
            print("\nStatus Details:")
            print("-" * 60)
            for key, value in status.items():
                if key == "sta_conn_wifi_passwd" or key == "ap_passwd":
                    # Don't print passwords in full
                    print(f"  {key}: {'*' * len(str(value)) if value else 'None'}")
                elif key == "client_list":
                    print(f"  {key}: {len(value)} clients")
                    for client in value:
                        print(f"    - {client}")
                else:
                    print(f"  {key}: {value}")
            print("-" * 60)
            return True
            
        except Exception as e:
            self.print_error(f"Status query failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_sta_connect(self) -> bool:
        """Test 4: Connect to WiFi (requires user confirmation)."""
        self.print_header("Test 4: STA Mode Connection (⚠️  Will Disconnect Current Connection)")
        
        if not self.backend:
            self.print_error("Backend not initialized.")
            return False
        
        # Get current status first
        try:
            current_status = self.backend.status()
            if current_status.get("wifi_mode") == "STA":
                current_ssid = current_status.get("sta_conn_wifi_ssid", "Unknown")
                self.print_warning(f"Currently connected to: {current_ssid}")
                self.print_warning("This test will disconnect the current connection!")
        except:
            pass
        
        if not self.confirm_action("Do you want to test STA connection? This will disconnect current WiFi."):
            self.print_info("Test skipped by user.")
            return None  # Skipped, not failed
        
        # Get network info from user
        print("\nPlease provide network information:")
        ssid = input("  SSID: ").strip()
        if not ssid:
            self.print_error("SSID cannot be empty.")
            return False
        
        passwd = input("  Password (press Enter for open network): ").strip()
        
        try:
            self.print_info(f"Connecting to {ssid}...")
            self.backend.sta_connect(ssid, passwd)
            
            # Wait a bit and check status
            time.sleep(2)
            status = self.backend.status()
            
            if status.get("wifi_mode") == "STA":
                self.print_success(f"Successfully connected to {ssid}!")
                if "sta_status" in status:
                    ip = status["sta_status"].get("ip_address")
                    if ip:
                        self.print_info(f"Assigned IP address: {ip}")
                return True
            else:
                self.print_error("Connection may have failed. Check status.")
                return False
                
        except Exception as e:
            self.print_error(f"Connection failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_sta_disconnect(self) -> bool:
        """Test 5: Disconnect from WiFi."""
        self.print_header("Test 5: STA Mode Disconnect")
        
        if not self.backend:
            self.print_error("Backend not initialized.")
            return False
        
        status = self.backend.status()
        if status.get("wifi_mode") != "STA":
            self.print_warning("Not currently connected. Nothing to disconnect.")
            return True  # Not an error, just nothing to do
        
        if not self.confirm_action("Do you want to disconnect from current WiFi?"):
            self.print_info("Test skipped by user.")
            return None
        
        try:
            self.print_info("Disconnecting...")
            self.backend.sta_disconnect()
            time.sleep(1)
            
            status = self.backend.status()
            if status.get("wifi_mode") == "IDLE":
                self.print_success("Successfully disconnected!")
                return True
            else:
                self.print_warning(f"Disconnect completed, but mode is: {status.get('wifi_mode')}")
                return True
                
        except Exception as e:
            self.print_error(f"Disconnect failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_ap_start(self) -> bool:
        """Test 6: Start AP mode (requires user confirmation)."""
        self.print_header("Test 6: AP Mode Start (⚠️  Will Create Hotspot)")
        
        if not self.backend:
            self.print_error("Backend not initialized.")
            return False
        
        self.print_warning("This will start an access point (hotspot) on your WiFi interface.")
        self.print_warning("This will disconnect any existing WiFi connection!")
        
        if not self.confirm_action("Do you want to start AP mode?"):
            self.print_info("Test skipped by user.")
            return None
        
        # Get AP configuration
        print("\nAP Configuration (press Enter for defaults):")
        ssid = input("  SSID (default: auto-generated): ").strip() or None
        passwd = input("  Password (default: 12345678): ").strip() or None
        
        try:
            self.print_info("Starting AP mode...")
            actual_ssid, actual_passwd = self.backend.ap_start(ssid=ssid, passwd=passwd)
            
            time.sleep(2)
            status = self.backend.status()
            
            if status.get("wifi_mode") == "AP":
                self.print_success(f"AP started successfully!")
                self.print_info(f"  SSID: {actual_ssid}")
                self.print_info(f"  Password: {actual_passwd}")
                self.print_info(f"  Clients: {len(status.get('client_list', []))}")
                return True
            else:
                self.print_error("AP may not have started correctly.")
                return False
                
        except NotSupportedError as e:
            self.print_error(f"AP mode not supported: {e}")
            return False
        except Exception as e:
            self.print_error(f"AP start failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_ap_stop(self) -> bool:
        """Test 7: Stop AP mode."""
        self.print_header("Test 7: AP Mode Stop")
        
        if not self.backend:
            self.print_error("Backend not initialized.")
            return False
        
        status = self.backend.status()
        if status.get("wifi_mode") != "AP":
            self.print_warning("AP mode is not active. Nothing to stop.")
            return True
        
        if not self.confirm_action("Do you want to stop AP mode?"):
            self.print_info("Test skipped by user.")
            return None
        
        try:
            self.print_info("Stopping AP mode...")
            self.backend.ap_stop()
            time.sleep(1)
            
            status = self.backend.status()
            if status.get("wifi_mode") == "IDLE":
                self.print_success("AP stopped successfully!")
                return True
            else:
                self.print_warning(f"AP stop completed, but mode is: {status.get('wifi_mode')}")
                return True
                
        except Exception as e:
            self.print_error(f"AP stop failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_safe_tests(self):
        """Run only safe, read-only tests."""
        self.print_header("Running Safe Tests (Read-Only Operations)")
        
        results = {}
        
        # Test 1: Initialization
        results['initialization'] = self.test_initialization()
        if not results['initialization']:
            self.print_error("Cannot continue without initialization.")
            return results
        
        # Test 2: Scan (safe)
        results['scan'] = self.test_scan()
        
        # Test 3: Status (safe)
        results['status'] = self.test_status()
        
        return results
    
    def run_interactive_tests(self):
        """Run interactive tests with user confirmation."""
        self.print_header("Running Interactive Tests")
        
        results = {}
        
        # First run safe tests
        safe_results = self.run_safe_tests()
        results.update(safe_results)
        
        if not results.get('initialization'):
            return results
        
        # Interactive tests
        print("\n" + "=" * 60)
        print("  Interactive Tests (Require User Confirmation)")
        print("=" * 60)
        print("\nAvailable tests:")
        print("  1. STA Connect (will disconnect current connection)")
        print("  2. STA Disconnect")
        print("  3. AP Start (will create hotspot)")
        print("  4. AP Stop")
        print("  5. Run all interactive tests")
        print("  0. Exit")
        
        choice = input("\nSelect test (0-5): ").strip()
        
        if choice == "1":
            results['sta_connect'] = self.test_sta_connect()
        elif choice == "2":
            results['sta_disconnect'] = self.test_sta_disconnect()
        elif choice == "3":
            results['ap_start'] = self.test_ap_start()
        elif choice == "4":
            results['ap_stop'] = self.test_ap_stop()
        elif choice == "5":
            results['sta_connect'] = self.test_sta_connect()
            results['sta_disconnect'] = self.test_sta_disconnect()
            results['ap_start'] = self.test_ap_start()
            if results.get('ap_start'):
                time.sleep(2)  # Wait a bit before stopping
            results['ap_stop'] = self.test_ap_stop()
        elif choice == "0":
            self.print_info("Exiting...")
        else:
            self.print_error("Invalid choice.")
        
        return results
    
    def print_summary(self, results: dict):
        """Print test summary."""
        self.print_header("Test Summary")
        
        total = len(results)
        passed = sum(1 for v in results.values() if v is True)
        failed = sum(1 for v in results.values() if v is False)
        skipped = sum(1 for v in results.values() if v is None)
        
        print(f"\nTotal tests: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⏭️  Skipped: {skipped}")
        
        print("\nDetailed Results:")
        print("-" * 60)
        for test_name, result in results.items():
            if result is True:
                status = "✅ PASS"
            elif result is False:
                status = "❌ FAIL"
            else:
                status = "⏭️  SKIP"
            print(f"  {test_name:<20} {status}")
        print("-" * 60)


def main():
    """Main test function."""
    parser = argparse.ArgumentParser(
        description="Safe test script for NetworkManager WiFi Backend"
    )
    parser.add_argument(
        '--interface',
        default='wlan0',
        help='WiFi interface name (default: wlan0)'
    )
    parser.add_argument(
        '--safe-only',
        action='store_true',
        help='Run only safe read-only tests'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  NetworkManager WiFi Backend - Safe Test Script")
    print("=" * 60)
    print(f"\nInterface: {args.interface}")
    print(f"Mode: {'Safe-only (read-only)' if args.safe_only else 'Interactive'}")
    
    tester = SafeWiFiTester(interface=args.interface)
    
    try:
        if args.safe_only:
            results = tester.run_safe_tests()
        else:
            results = tester.run_interactive_tests()
        
        tester.print_summary(results)
        
        # Exit with appropriate code
        if any(v is False for v in results.values()):
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
