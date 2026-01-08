"""
Unified Fuzzing Engine Core for IoT Protocol Fuzzing

This module provides a comprehensive fuzzing engine that supports multiple fuzzing strategies
including bit-level and field-level fuzzing. The engine uses a strategy pattern to allow
pluggable fuzzing algorithms.

Author: IoT Security Testing Team
Date: 2024
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Type, Tuple, Union
import logging
import random
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FuzzingType(Enum):
    """Enumeration of fuzzing types supported by the engine."""
    BIT_LEVEL = "bit_level"
    FIELD_LEVEL = "field_level"
    HYBRID = "hybrid"


@dataclass
class FuzzTestCase:
    """
    Represents a test case with frame fields and fuzzing rules.
    
    This is a simplified representation that will be used by fuzzing strategies.
    The actual Django model data will be converted to this format.
    """
    id: str
    name: str
    protocol_type: str
    frame_data: bytes
    frame_fields: List[Dict[str, Any]]
    fuzzing_rules: List[Dict[str, Any]]
    target_bits: Optional[str] = None


@dataclass
class MutationResult:
    """
    Represents the result of a single mutation operation.
    """
    original_data: bytes
    mutated_data: bytes
    strategy_name: str
    mutation_info: Dict[str, Any]
    test_case_id: str
    iteration: int


class FuzzingStrategy(ABC):
    """
    Abstract base class for all fuzzing strategies.
    
    All fuzzing strategies must inherit from this class and implement
    the required abstract methods.
    """
    
    def __init__(self, name: str, fuzzing_type: FuzzingType):
        """
        Initialize the fuzzing strategy.
        
        Args:
            name: Human-readable name for the strategy
            fuzzing_type: Type of fuzzing this strategy performs
        """
        self.name = name
        self.fuzzing_type = fuzzing_type
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if this strategy can be applied to the given test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if strategy can be applied, False otherwise
        """
        pass
    
    @abstractmethod
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate mutations for the given test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Number of mutations to generate
            
        Returns:
            List of mutation results
        """
        pass
    
    @abstractmethod
    def get_strategy_info(self) -> Dict[str, Any]:
        """
        Get information about this strategy.
        
        Returns:
            Dictionary containing strategy metadata
        """
        pass
    
    def validate_test_case(self, test_case: FuzzTestCase) -> bool:
        """
        Validate that the test case is suitable for this strategy.
        
        Args:
            test_case: Test case to validate
            
        Returns:
            True if valid, False otherwise
        """
        if not test_case.frame_data:
            self.logger.warning(f"Test case {test_case.id} has no frame data")
            return False
        
        return True


class StrategyRegistry:
    """
    Registry for managing fuzzing strategies.
    
    This class maintains a registry of available fuzzing strategies and
    provides methods to register, retrieve, and manage them.
    """
    
    def __init__(self):
        """Initialize the strategy registry."""
        self._strategies: Dict[str, Type[FuzzingStrategy]] = {}
        self._instances: Dict[str, FuzzingStrategy] = {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    def register_strategy(self, strategy_class: Type[FuzzingStrategy]) -> None:
        """
        Register a new fuzzing strategy.
        
        Args:
            strategy_class: Class of the strategy to register
            
        Raises:
            ValueError: If strategy is invalid or name conflicts
        """
        if not issubclass(strategy_class, FuzzingStrategy):
            raise ValueError(f"Strategy class must inherit from FuzzingStrategy")
        
        # Create a temporary instance to get the name
        try:
            temp_instance = strategy_class()
            strategy_name = temp_instance.name
        except Exception as e:
            raise ValueError(f"Could not instantiate strategy class: {e}")
        
        if not strategy_name:
            raise ValueError(f"Strategy must have a non-empty name")
        
        if strategy_name in self._strategies:
            self.logger.warning(f"Overriding existing strategy: {strategy_name}")
        
        self._strategies[strategy_name] = strategy_class
        self.logger.info(f"Registered fuzzing strategy: {strategy_name}")
    
    def get_strategy(self, name: str) -> Optional[FuzzingStrategy]:
        """
        Get a strategy instance by name.
        
        Args:
            name: Name of the strategy
            
        Returns:
            Strategy instance or None if not found
        """
        if name not in self._strategies:
            self.logger.error(f"Strategy not found: {name}")
            return None
        
        # Create instance if not cached
        if name not in self._instances:
            strategy_class = self._strategies[name]
            # Create instance using the class's default constructor
            try:
                self._instances[name] = strategy_class()
            except Exception as e:
                self.logger.error(f"Error creating strategy instance for {name}: {e}")
                return None
        
        return self._instances[name]
    
    def list_strategies(self) -> List[str]:
        """
        List all registered strategy names.
        
        Returns:
            List of strategy names
        """
        return list(self._strategies.keys())
    
    def get_strategies_by_type(self, fuzzing_type: FuzzingType) -> List[str]:
        """
        Get strategies that support the specified fuzzing type.
        
        Args:
            fuzzing_type: Type of fuzzing
            
        Returns:
            List of strategy names that support the fuzzing type
        """
        matching_strategies = []
        
        for name in self._strategies:
            strategy = self.get_strategy(name)
            if strategy and strategy.fuzzing_type == fuzzing_type:
                matching_strategies.append(name)
        
        return matching_strategies
    
    def clear_registry(self) -> None:
        """Clear all registered strategies."""
        self._strategies.clear()
        self._instances.clear()
        self.logger.info("Cleared strategy registry")


class FuzzingEngine:
    """
    Main fuzzing engine that orchestrates different fuzzing strategies.
    
    This engine provides a unified interface for executing multiple fuzzing
    strategies on test cases, managing iterations, and collecting results.
    """
    
    def __init__(self, registry: Optional[StrategyRegistry] = None):
        """
        Initialize the fuzzing engine.
        
        Args:
            registry: Strategy registry to use (creates new one if None)
        """
        self.registry = registry or StrategyRegistry()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._load_default_strategies()
    
    def _load_default_strategies(self) -> None:
        """Load default fuzzing strategies."""
        self.logger.info("Loading default fuzzing strategies...")
        
        # Import and register strategies
        try:
            from .strategies.bit_strategies import (
                BitFlipStrategy, SequentialBitStrategy, RandomBitStrategy
            )
            from .strategies.field_strategies import (
                FieldMutationStrategy, BoundaryValueStrategy, InjectionStrategy
            )
            
            # Register bit-level strategies
            self.register_strategy(BitFlipStrategy)
            self.register_strategy(SequentialBitStrategy)
            self.register_strategy(RandomBitStrategy)
            
            # Register field-level strategies
            self.register_strategy(FieldMutationStrategy)
            self.register_strategy(BoundaryValueStrategy)
            self.register_strategy(InjectionStrategy)
            
            self.logger.info(f"Loaded {len(self.registry.list_strategies())} default strategies")
            
        except ImportError as e:
            self.logger.warning(f"Could not load some default strategies: {e}")
        except Exception as e:
            self.logger.error(f"Error loading default strategies: {e}")
    
    def register_strategy(self, strategy_class: Type[FuzzingStrategy]) -> None:
        """
        Register a new fuzzing strategy.
        
        Args:
            strategy_class: Strategy class to register
        """
        self.registry.register_strategy(strategy_class)
    
    def generate_mutations(self, test_cases: List[FuzzTestCase], iterations: int = 10, 
                          strategy_names: Optional[List[str]] = None) -> Dict[str, List[MutationResult]]:
        """
        Generate mutations for multiple test cases using selected strategies.
        
        Args:
            test_cases: List of test cases to mutate
            iterations: Number of mutations per strategy per test case
            strategy_names: List of strategy names to use (use all if None)
            
        Returns:
            Dictionary mapping strategy names to lists of mutation results
        """
        if not test_cases:
            self.logger.warning("No test cases provided for mutation")
            return {}
        
        # Use all strategies if none specified
        if strategy_names is None:
            strategy_names = self.registry.list_strategies()
        
        if not strategy_names:
            self.logger.warning("No strategies available for fuzzing")
            return {}
        
        results = {}
        
        for strategy_name in strategy_names:
            strategy = self.registry.get_strategy(strategy_name)
            if not strategy:
                self.logger.error(f"Strategy not found: {strategy_name}")
                continue
            
            strategy_results = []
            
            for test_case in test_cases:
                if not strategy.can_apply(test_case):
                    self.logger.debug(f"Strategy {strategy_name} cannot be applied to test case {test_case.id}")
                    continue
                
                try:
                    mutations = strategy.generate_mutations(test_case, iterations)
                    strategy_results.extend(mutations)
                    self.logger.info(f"Generated {len(mutations)} mutations for test case {test_case.id} using {strategy_name}")
                except Exception as e:
                    self.logger.error(f"Error generating mutations with {strategy_name} for test case {test_case.id}: {e}")
                    continue
            
            if strategy_results:
                results[strategy_name] = strategy_results
        
        total_mutations = sum(len(mutations) for mutations in results.values())
        self.logger.info(f"Generated {total_mutations} total mutations across {len(results)} strategies")
        
        return results
    
    def _apply_fuzzing_rules(self, test_case: FuzzTestCase) -> List[str]:
        """
        Determine which strategies to apply based on fuzzing rules in the test case.
        
        Args:
            test_case: Test case with fuzzing rules
            
        Returns:
            List of strategy names to apply
        """
        applicable_strategies = []
        
        # Check for bit-level fuzzing rules
        has_bit_rules = False
        has_field_rules = False
        
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['bit_flip', 'bit_mutation', 'bit_level']:
                has_bit_rules = True
            elif rule_type in ['field_mutation', 'boundary_test', 'injection']:
                has_field_rules = True
        
        # Also check for target_bits field
        if test_case.target_bits:
            has_bit_rules = True
        
        # Get strategies based on rules
        if has_bit_rules:
            bit_strategies = self.registry.get_strategies_by_type(FuzzingType.BIT_LEVEL)
            applicable_strategies.extend(bit_strategies)
        
        if has_field_rules:
            field_strategies = self.registry.get_strategies_by_type(FuzzingType.FIELD_LEVEL)
            applicable_strategies.extend(field_strategies)
        
        # If no specific rules, use all available strategies
        if not applicable_strategies:
            applicable_strategies = self.registry.list_strategies()
            self.logger.info(f"No specific fuzzing rules found for test case {test_case.id}, using all strategies")
        
        return list(set(applicable_strategies))  # Remove duplicates
    
    def analyze_test_cases(self, test_cases: List[FuzzTestCase]) -> Dict[str, Any]:
        """
        Analyze test cases to provide statistics about applicable strategies.
        
        Args:
            test_cases: List of test cases to analyze
            
        Returns:
            Dictionary containing analysis results
        """
        analysis = {
            'total_test_cases': len(test_cases),
            'bit_level_compatible': 0,
            'field_level_compatible': 0,
            'hybrid_compatible': 0,
            'strategy_distribution': {},
            'protocol_types': set(),
            'total_frame_data_size': 0
        }
        
        for test_case in test_cases:
            # Track protocol types
            analysis['protocol_types'].add(test_case.protocol_type)
            
            # Track frame data size
            analysis['total_frame_data_size'] += len(test_case.frame_data)
            
            # Determine applicable strategies
            applicable_strategies = self._apply_fuzzing_rules(test_case)
            
            # Count compatibility
            bit_compatible = any(self.registry.get_strategy(name) and 
                               self.registry.get_strategy(name).fuzzing_type == FuzzingType.BIT_LEVEL 
                               for name in applicable_strategies)
            field_compatible = any(self.registry.get_strategy(name) and 
                                 self.registry.get_strategy(name).fuzzing_type == FuzzingType.FIELD_LEVEL 
                                 for name in applicable_strategies)
            
            if bit_compatible:
                analysis['bit_level_compatible'] += 1
            if field_compatible:
                analysis['field_level_compatible'] += 1
            if bit_compatible and field_compatible:
                analysis['hybrid_compatible'] += 1
            
            # Track strategy distribution
            for strategy_name in applicable_strategies:
                if strategy_name not in analysis['strategy_distribution']:
                    analysis['strategy_distribution'][strategy_name] = 0
                analysis['strategy_distribution'][strategy_name] += 1
        
        # Convert set to list for JSON serialization
        analysis['protocol_types'] = list(analysis['protocol_types'])
        
        return analysis
    
    def get_engine_status(self) -> Dict[str, Any]:
        """
        Get current engine status and statistics.
        
        Returns:
            Dictionary containing engine status information
        """
        return {
            'registered_strategies': len(self.registry.list_strategies()),
            'strategy_names': self.registry.list_strategies(),
            'bit_level_strategies': self.registry.get_strategies_by_type(FuzzingType.BIT_LEVEL),
            'field_level_strategies': self.registry.get_strategies_by_type(FuzzingType.FIELD_LEVEL),
            'engine_version': '1.0.0'
        }


# Global registry instance
default_registry = StrategyRegistry()

# Global engine instance  
default_engine = FuzzingEngine(default_registry) 