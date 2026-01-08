"""
IoT Protocol Fuzzer

A modular fuzzing framework for IoT communication protocols including CAN, UART, and SPI.
"""

__version__ = "0.1.0"
__author__ = "IoT Security Research"
__description__ = "Modular fuzzing framework for IoT protocols"

# Make common imports available at package level
from .core.orchestrator import Orchestrator, CampaignConfig
from .core.bit_manipulator import BitManipulator, flip_bit, set_bit, get_bit, parse_target_bits
from .core.fuzzing_engine import (
    FuzzingEngine, StrategyRegistry, FuzzingStrategy, FuzzingType,
    FuzzTestCase, MutationResult, default_engine, default_registry
)
from .generators.radamsa_generator import RadamsaGenerator
from .harnesses.can_harness import CANHarness
from .harnesses.uart_harness import UARTHarness
from .harnesses.spi_harness import SPIHarness

# Import strategies
try:
    from .core.strategies.bit_strategies import (
        BitFlipStrategy, SequentialBitStrategy, RandomBitStrategy
    )
    from .core.strategies.field_strategies import (
        FieldMutationStrategy, BoundaryValueStrategy, InjectionStrategy
    )
except ImportError:
    # Strategies may not be available in all environments
    pass

__all__ = [
    # Original components
    "Orchestrator",
    "CampaignConfig", 
    "BitManipulator",
    "flip_bit",
    "set_bit",
    "get_bit",
    "parse_target_bits",
    "RadamsaGenerator",
    "CANHarness",
    "UARTHarness",
    "SPIHarness",
    
    # Fuzzing engine components
    "FuzzingEngine",
    "StrategyRegistry", 
    "FuzzingStrategy",
    "FuzzingType",
    "FuzzTestCase",
    "MutationResult",
    "default_engine",
    "default_registry",
    
    # Fuzzing strategies
    "BitFlipStrategy",
    "SequentialBitStrategy", 
    "RandomBitStrategy",
    "FieldMutationStrategy",
    "BoundaryValueStrategy",
    "InjectionStrategy",
] 