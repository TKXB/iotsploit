# Core package for IoT Protocol Fuzzer 

from .bit_manipulator import (
    BitManipulator,
    flip_bit,
    set_bit,
    get_bit,
    parse_target_bits,
    validate_bit_positions
)

from .fuzzing_engine import (
    FuzzingEngine,
    StrategyRegistry,
    FuzzingStrategy,
    FuzzingType,
    FuzzTestCase,
    MutationResult,
    default_registry,
    default_engine
)

# Import strategies
try:
    from .strategies.bit_strategies import (
        BitFlipStrategy,
        SequentialBitStrategy,
        RandomBitStrategy
    )
    from .strategies.field_strategies import (
        FieldMutationStrategy,
        BoundaryValueStrategy,
        InjectionStrategy
    )
except ImportError:
    # Strategies may not be available in all environments
    pass

__all__ = [
    # Bit manipulation utilities
    'BitManipulator',
    'flip_bit',
    'set_bit',
    'get_bit',
    'parse_target_bits',
    'validate_bit_positions',
    
    # Fuzzing engine core
    'FuzzingEngine',
    'StrategyRegistry',
    'FuzzingStrategy',
    'FuzzingType',
    'FuzzTestCase',
    'MutationResult',
    'default_registry',
    'default_engine',
    
    # Bit-level strategies
    'BitFlipStrategy',
    'SequentialBitStrategy',
    'RandomBitStrategy',
    
    # Field-level strategies
    'FieldMutationStrategy',
    'BoundaryValueStrategy',
    'InjectionStrategy'
] 