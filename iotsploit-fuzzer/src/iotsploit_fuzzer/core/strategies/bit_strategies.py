"""
Bit-Level Fuzzing Strategies

This module contains fuzzing strategies that manipulate data at the bit level.
These strategies use the BitManipulator utility to perform precise bit operations
based on target_bits specifications in test cases.

Author: IoT Security Testing Team
Date: 2024
"""

from typing import List, Dict, Any
import random
import itertools
from ..fuzzing_engine import FuzzingStrategy, FuzzingType, FuzzTestCase, MutationResult
from ..bit_manipulator import BitManipulator


class BitFlipStrategy(FuzzingStrategy):
    """
    Bit flip fuzzing strategy that flips individual bits and combinations.
    
    This strategy systematically flips bits at positions specified in target_bits,
    including single bit flips and multi-bit combinations.
    
    Example:
        target_bits="0,1,7" → Test flipping each individually and in combinations:
        - Flip bit 0 only
        - Flip bit 1 only  
        - Flip bit 7 only
        - Flip bits 0,1
        - Flip bits 0,7
        - Flip bits 1,7
        - Flip bits 0,1,7
    """
    
    def __init__(self):
        """Initialize the bit flip strategy."""
        super().__init__("bit_flip", FuzzingType.BIT_LEVEL)
        self.max_combination_size = 4  # Limit combination explosion
    
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if bit flip strategy can be applied to the test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if test case has target_bits or bit-level fuzzing rules
        """
        if not self.validate_test_case(test_case):
            return False
        
        # Check for target_bits field
        if test_case.target_bits:
            return True
        
        # Check for bit-level fuzzing rules
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['bit_flip', 'bit_mutation', 'bit_level']:
                return True
        
        return False
    
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate bit flip mutations for the test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Maximum number of mutations to generate
            
        Returns:
            List of mutation results
        """
        mutations = []
        
        # Parse target bits
        target_bits = self._get_target_bits(test_case)
        if not target_bits:
            self.logger.warning(f"No target bits found for test case {test_case.id}")
            return mutations
        
        # Validate bit positions
        max_bits = BitManipulator.get_max_bits_for_data(test_case.frame_data)
        if not BitManipulator.validate_bit_positions(target_bits, max_bits):
            self.logger.error(f"Invalid bit positions for test case {test_case.id}")
            return mutations
        
        iteration_count = 0
        
        # Generate single bit flips
        for bit_pos in target_bits:
            if iteration_count >= iterations:
                break
            
            try:
                mutated_data = BitManipulator.flip_bit(test_case.frame_data, bit_pos)
                
                mutation_result = MutationResult(
                    original_data=test_case.frame_data,
                    mutated_data=mutated_data,
                    strategy_name=self.name,
                    mutation_info={
                        'operation': 'single_bit_flip',
                        'bit_position': bit_pos,
                        'flipped_bits': [bit_pos]
                    },
                    test_case_id=test_case.id,
                    iteration=iteration_count
                )
                
                mutations.append(mutation_result)
                iteration_count += 1
                
            except Exception as e:
                self.logger.error(f"Error flipping bit {bit_pos} in test case {test_case.id}: {e}")
                continue
        
        # Generate multi-bit combinations if we have remaining iterations
        if iteration_count < iterations and len(target_bits) > 1:
            combinations = self._generate_bit_combinations(target_bits)
            
            for combo in combinations:
                if iteration_count >= iterations:
                    break
                
                try:
                    # Apply multiple bit flips
                    mutated_data = test_case.frame_data
                    for bit_pos in combo:
                        mutated_data = BitManipulator.flip_bit(mutated_data, bit_pos)
                    
                    mutation_result = MutationResult(
                        original_data=test_case.frame_data,
                        mutated_data=mutated_data,
                        strategy_name=self.name,
                        mutation_info={
                            'operation': 'multi_bit_flip',
                            'combination_size': len(combo),
                            'flipped_bits': list(combo)
                        },
                        test_case_id=test_case.id,
                        iteration=iteration_count
                    )
                    
                    mutations.append(mutation_result)
                    iteration_count += 1
                    
                except Exception as e:
                    self.logger.error(f"Error flipping bit combination {combo} in test case {test_case.id}: {e}")
                    continue
        
        self.logger.info(f"Generated {len(mutations)} bit flip mutations for test case {test_case.id}")
        return mutations
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the bit flip strategy."""
        return {
            'name': self.name,
            'type': self.fuzzing_type.value,
            'description': 'Flips individual bits and bit combinations at target positions',
            'parameters': {
                'max_combination_size': self.max_combination_size
            },
            'requirements': ['target_bits or bit-level fuzzing rules']
        }
    
    def _get_target_bits(self, test_case: FuzzTestCase) -> List[int]:
        """Extract target bits from test case."""
        # Try target_bits field first
        if test_case.target_bits:
            try:
                return BitManipulator.parse_target_bits(test_case.target_bits)
            except Exception as e:
                self.logger.error(f"Error parsing target_bits '{test_case.target_bits}': {e}")
        
        # Try fuzzing rules
        for rule in test_case.fuzzing_rules:
            if rule.get('type', '').lower() in ['bit_flip', 'bit_mutation', 'bit_level']:
                target_bits_str = rule.get('target_bits', '')
                if target_bits_str:
                    try:
                        return BitManipulator.parse_target_bits(target_bits_str)
                    except Exception as e:
                        self.logger.error(f"Error parsing rule target_bits '{target_bits_str}': {e}")
        
        return []
    
    def _generate_bit_combinations(self, target_bits: List[int]) -> List[tuple]:
        """Generate bit combinations for multi-bit flips."""
        combinations = []
        
        # Generate combinations of size 2 to max_combination_size
        for size in range(2, min(len(target_bits) + 1, self.max_combination_size + 1)):
            for combo in itertools.combinations(target_bits, size):
                combinations.append(combo)
        
        # Limit total combinations to prevent explosion
        max_combinations = 50
        if len(combinations) > max_combinations:
            combinations = random.sample(combinations, max_combinations)
        
        return combinations


class SequentialBitStrategy(FuzzingStrategy):
    """
    Sequential bit testing strategy that systematically tests each bit as 0 and 1.
    
    This strategy walks through all positions in target_bits sequentially,
    setting each bit to 0 and then to 1, regardless of its current value.
    """
    
    def __init__(self):
        """Initialize the sequential bit strategy."""
        super().__init__("sequential_bit", FuzzingType.BIT_LEVEL)
    
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if sequential bit strategy can be applied to the test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if test case has target_bits or bit-level fuzzing rules
        """
        if not self.validate_test_case(test_case):
            return False
        
        # Check for target_bits field
        if test_case.target_bits:
            return True
        
        # Check for bit-level fuzzing rules
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['sequential_bit', 'bit_walk', 'bit_level']:
                return True
        
        return False
    
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate sequential bit mutations for the test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Maximum number of mutations to generate
            
        Returns:
            List of mutation results
        """
        mutations = []
        
        # Parse target bits
        target_bits = self._get_target_bits(test_case)
        if not target_bits:
            self.logger.warning(f"No target bits found for test case {test_case.id}")
            return mutations
        
        # Validate bit positions
        max_bits = BitManipulator.get_max_bits_for_data(test_case.frame_data)
        if not BitManipulator.validate_bit_positions(target_bits, max_bits):
            self.logger.error(f"Invalid bit positions for test case {test_case.id}")
            return mutations
        
        iteration_count = 0
        
        # For each target bit, test setting it to 0 and 1
        for bit_pos in target_bits:
            if iteration_count >= iterations:
                break
            
            # Test setting bit to 0
            try:
                mutated_data = BitManipulator.set_bit(test_case.frame_data, bit_pos, False)
                
                mutation_result = MutationResult(
                    original_data=test_case.frame_data,
                    mutated_data=mutated_data,
                    strategy_name=self.name,
                    mutation_info={
                        'operation': 'set_bit_to_0',
                        'bit_position': bit_pos,
                        'bit_value': 0
                    },
                    test_case_id=test_case.id,
                    iteration=iteration_count
                )
                
                mutations.append(mutation_result)
                iteration_count += 1
                
            except Exception as e:
                self.logger.error(f"Error setting bit {bit_pos} to 0 in test case {test_case.id}: {e}")
            
            if iteration_count >= iterations:
                break
            
            # Test setting bit to 1
            try:
                mutated_data = BitManipulator.set_bit(test_case.frame_data, bit_pos, True)
                
                mutation_result = MutationResult(
                    original_data=test_case.frame_data,
                    mutated_data=mutated_data,
                    strategy_name=self.name,
                    mutation_info={
                        'operation': 'set_bit_to_1',
                        'bit_position': bit_pos,
                        'bit_value': 1
                    },
                    test_case_id=test_case.id,
                    iteration=iteration_count
                )
                
                mutations.append(mutation_result)
                iteration_count += 1
                
            except Exception as e:
                self.logger.error(f"Error setting bit {bit_pos} to 1 in test case {test_case.id}: {e}")
        
        self.logger.info(f"Generated {len(mutations)} sequential bit mutations for test case {test_case.id}")
        return mutations
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the sequential bit strategy."""
        return {
            'name': self.name,
            'type': self.fuzzing_type.value,
            'description': 'Systematically tests each target bit as 0 and 1',
            'parameters': {},
            'requirements': ['target_bits or bit-level fuzzing rules']
        }
    
    def _get_target_bits(self, test_case: FuzzTestCase) -> List[int]:
        """Extract target bits from test case."""
        # Try target_bits field first
        if test_case.target_bits:
            try:
                return BitManipulator.parse_target_bits(test_case.target_bits)
            except Exception as e:
                self.logger.error(f"Error parsing target_bits '{test_case.target_bits}': {e}")
        
        # Try fuzzing rules
        for rule in test_case.fuzzing_rules:
            if rule.get('type', '').lower() in ['sequential_bit', 'bit_walk', 'bit_level']:
                target_bits_str = rule.get('target_bits', '')
                if target_bits_str:
                    try:
                        return BitManipulator.parse_target_bits(target_bits_str)
                    except Exception as e:
                        self.logger.error(f"Error parsing rule target_bits '{target_bits_str}': {e}")
        
        return []


class RandomBitStrategy(FuzzingStrategy):
    """
    Random bit manipulation strategy that randomly modifies bits at target positions.
    
    This strategy performs random bit operations within the specified target_bits
    positions, with configurable mutation probability per bit.
    """
    
    def __init__(self, mutation_probability: float = 0.5):
        """
        Initialize the random bit strategy.
        
        Args:
            mutation_probability: Probability of mutating each target bit (0.0 to 1.0)
        """
        super().__init__("random_bit", FuzzingType.BIT_LEVEL)
        self.mutation_probability = max(0.0, min(1.0, mutation_probability))
    
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if random bit strategy can be applied to the test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if test case has target_bits or bit-level fuzzing rules
        """
        if not self.validate_test_case(test_case):
            return False
        
        # Check for target_bits field
        if test_case.target_bits:
            return True
        
        # Check for bit-level fuzzing rules
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['random_bit', 'random_mutation', 'bit_level']:
                return True
        
        return False
    
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate random bit mutations for the test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Number of mutations to generate
            
        Returns:
            List of mutation results
        """
        mutations = []
        
        # Parse target bits
        target_bits = self._get_target_bits(test_case)
        if not target_bits:
            self.logger.warning(f"No target bits found for test case {test_case.id}")
            return mutations
        
        # Validate bit positions
        max_bits = BitManipulator.get_max_bits_for_data(test_case.frame_data)
        if not BitManipulator.validate_bit_positions(target_bits, max_bits):
            self.logger.error(f"Invalid bit positions for test case {test_case.id}")
            return mutations
        
        # Generate random mutations
        for iteration in range(iterations):
            try:
                # Start with original data
                mutated_data = test_case.frame_data
                mutated_bits = []
                
                # Randomly decide which bits to mutate
                for bit_pos in target_bits:
                    if random.random() < self.mutation_probability:
                        # Randomly flip or set the bit
                        operation = random.choice(['flip', 'set_0', 'set_1'])
                        
                        if operation == 'flip':
                            mutated_data = BitManipulator.flip_bit(mutated_data, bit_pos)
                            mutated_bits.append({'position': bit_pos, 'operation': 'flip'})
                        elif operation == 'set_0':
                            mutated_data = BitManipulator.set_bit(mutated_data, bit_pos, False)
                            mutated_bits.append({'position': bit_pos, 'operation': 'set_0'})
                        else:  # set_1
                            mutated_data = BitManipulator.set_bit(mutated_data, bit_pos, True)
                            mutated_bits.append({'position': bit_pos, 'operation': 'set_1'})
                
                # Only create mutation if something was actually changed
                if mutated_bits:
                    mutation_result = MutationResult(
                        original_data=test_case.frame_data,
                        mutated_data=mutated_data,
                        strategy_name=self.name,
                        mutation_info={
                            'operation': 'random_bit_mutations',
                            'mutation_probability': self.mutation_probability,
                            'mutated_bits': mutated_bits,
                            'total_mutations': len(mutated_bits)
                        },
                        test_case_id=test_case.id,
                        iteration=iteration
                    )
                    
                    mutations.append(mutation_result)
                
            except Exception as e:
                self.logger.error(f"Error generating random bit mutation {iteration} for test case {test_case.id}: {e}")
                continue
        
        self.logger.info(f"Generated {len(mutations)} random bit mutations for test case {test_case.id}")
        return mutations
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the random bit strategy."""
        return {
            'name': self.name,
            'type': self.fuzzing_type.value,
            'description': 'Randomly manipulates bits at target positions with configurable probability',
            'parameters': {
                'mutation_probability': self.mutation_probability
            },
            'requirements': ['target_bits or bit-level fuzzing rules']
        }
    
    def _get_target_bits(self, test_case: FuzzTestCase) -> List[int]:
        """Extract target bits from test case."""
        # Try target_bits field first
        if test_case.target_bits:
            try:
                return BitManipulator.parse_target_bits(test_case.target_bits)
            except Exception as e:
                self.logger.error(f"Error parsing target_bits '{test_case.target_bits}': {e}")
        
        # Try fuzzing rules
        for rule in test_case.fuzzing_rules:
            if rule.get('type', '').lower() in ['random_bit', 'random_mutation', 'bit_level']:
                target_bits_str = rule.get('target_bits', '')
                if target_bits_str:
                    try:
                        return BitManipulator.parse_target_bits(target_bits_str)
                    except Exception as e:
                        self.logger.error(f"Error parsing rule target_bits '{target_bits_str}': {e}")
        
        return [] 