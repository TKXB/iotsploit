"""
IoT Protocol Fuzzer

A modular fuzzing framework for IoT communication protocols including CAN, UART, and SPI.
"""

__version__ = "0.1.0"
__author__ = "IoT Security Research"
__description__ = "Modular fuzzing framework for IoT protocols"

# Make common imports available at package level
from .core.orchestrator import Orchestrator, CampaignConfig
from .generators.radamsa_generator import RadamsaGenerator
from .harnesses.can_harness import CANHarness
from .harnesses.uart_harness import UARTHarness
from .harnesses.spi_harness import SPIHarness

__all__ = [
    "Orchestrator",
    "CampaignConfig", 
    "RadamsaGenerator",
    "CANHarness",
    "UARTHarness",
    "SPIHarness",
] 