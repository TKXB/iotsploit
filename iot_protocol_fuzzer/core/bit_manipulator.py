"""
Bit-Level Manipulation Utilities for IoT Fuzzing

This module provides comprehensive bit manipulation capabilities for IoT protocol fuzzing,
including single bit operations, range operations, and target bits parsing.

Author: IoT Security Testing Team
Date: 2024
"""

from typing import List, Union, Tuple
import re
import logging

logger = logging.getLogger(__name__)


class BitManipulator:
    """
    A comprehensive utility class for bit-level operations on byte data.
    
    This class provides methods for:
    - Single bit manipulation (flip, set, get)
    - Range bit operations
    - Target bits string parsing
    - Validation of bit positions
    
    Bit numbering convention: LSB (Least Significant Bit) = bit 0
    For multi-byte data, bit numbering is continuous across bytes.
    Example: 0x02 0x10 -> bits 0-7 in first byte, 8-15 in second byte
    """
    
    @staticmethod
    def flip_bit(data: bytes, bit_position: int) -> bytes:
        """
        Flip a single bit at the specified position.
        
        Args:
            data: Input byte data
            bit_position: Bit position to flip (0-based, LSB first)
            
        Returns:
            New bytes object with the bit flipped
            
        Raises:
            ValueError: If bit_position is out of range
            
        Example:
            flip_bit(b'\x02', 0) -> b'\x03'  # 00000010 -> 00000011
            flip_bit(b'\x02', 7) -> b'\x82'  # 00000010 -> 10000010
        """
        if not data:
            raise ValueError("Data cannot be empty")
            
        max_bits = len(data) * 8
        if bit_position < 0 or bit_position >= max_bits:
            raise ValueError(f"Bit position {bit_position} out of range [0, {max_bits-1}]")
        
        # Convert to mutable bytearray
        result = bytearray(data)
        
        # Calculate byte index and bit offset within that byte
        byte_index = bit_position // 8
        bit_offset = bit_position % 8
        
        # Flip the bit using XOR
        result[byte_index] ^= (1 << bit_offset)
        
        return bytes(result)
    
    @staticmethod
    def set_bit(data: bytes, bit_position: int, value: bool) -> bytes:
        """
        Set a single bit to the specified value (0 or 1).
        
        Args:
            data: Input byte data
            bit_position: Bit position to set (0-based, LSB first)
            value: True to set bit to 1, False to set bit to 0
            
        Returns:
            New bytes object with the bit set
            
        Raises:
            ValueError: If bit_position is out of range
            
        Example:
            set_bit(b'\x02', 0, True) -> b'\x03'   # Set bit 0 to 1
            set_bit(b'\x02', 0, False) -> b'\x02'  # Set bit 0 to 0 (no change)
            set_bit(b'\x02', 7, True) -> b'\x82'   # Set bit 7 to 1
        """
        if not data:
            raise ValueError("Data cannot be empty")
            
        max_bits = len(data) * 8
        if bit_position < 0 or bit_position >= max_bits:
            raise ValueError(f"Bit position {bit_position} out of range [0, {max_bits-1}]")
        
        # Convert to mutable bytearray
        result = bytearray(data)
        
        # Calculate byte index and bit offset within that byte
        byte_index = bit_position // 8
        bit_offset = bit_position % 8
        
        if value:
            # Set bit to 1 using OR
            result[byte_index] |= (1 << bit_offset)
        else:
            # Set bit to 0 using AND with inverted mask
            result[byte_index] &= ~(1 << bit_offset)
        
        return bytes(result)
    
    @staticmethod
    def get_bit(data: bytes, bit_position: int) -> bool:
        """
        Get the value of a single bit at the specified position.
        
        Args:
            data: Input byte data
            bit_position: Bit position to read (0-based, LSB first)
            
        Returns:
            True if bit is 1, False if bit is 0
            
        Raises:
            ValueError: If bit_position is out of range
            
        Example:
            get_bit(b'\x02', 1) -> True   # 00000010, bit 1 is 1
            get_bit(b'\x02', 0) -> False  # 00000010, bit 0 is 0
        """
        if not data:
            raise ValueError("Data cannot be empty")
            
        max_bits = len(data) * 8
        if bit_position < 0 or bit_position >= max_bits:
            raise ValueError(f"Bit position {bit_position} out of range [0, {max_bits-1}]")
        
        # Calculate byte index and bit offset within that byte
        byte_index = bit_position // 8
        bit_offset = bit_position % 8
        
        # Extract the bit using AND and right shift
        return bool(data[byte_index] & (1 << bit_offset))
    
    @staticmethod
    def flip_bits_range(data: bytes, start_bit: int, end_bit: int) -> bytes:
        """
        Flip all bits in the specified range (inclusive).
        
        Args:
            data: Input byte data
            start_bit: Starting bit position (inclusive)
            end_bit: Ending bit position (inclusive)
            
        Returns:
            New bytes object with all bits in range flipped
            
        Raises:
            ValueError: If bit positions are out of range or invalid
            
        Example:
            flip_bits_range(b'\x00', 0, 2) -> b'\x07'  # 00000000 -> 00000111
            flip_bits_range(b'\xFF', 0, 2) -> b'\xF8'  # 11111111 -> 11111000
        """
        if not data:
            raise ValueError("Data cannot be empty")
            
        max_bits = len(data) * 8
        if start_bit < 0 or start_bit >= max_bits:
            raise ValueError(f"Start bit {start_bit} out of range [0, {max_bits-1}]")
        if end_bit < 0 or end_bit >= max_bits:
            raise ValueError(f"End bit {end_bit} out of range [0, {max_bits-1}]")
        if start_bit > end_bit:
            raise ValueError(f"Start bit {start_bit} cannot be greater than end bit {end_bit}")
        
        result = bytearray(data)
        
        # Flip each bit in the range
        for bit_pos in range(start_bit, end_bit + 1):
            byte_index = bit_pos // 8
            bit_offset = bit_pos % 8
            result[byte_index] ^= (1 << bit_offset)
        
        return bytes(result)
    
    @staticmethod
    def parse_target_bits(target_bits_str: str) -> List[int]:
        """
        Parse target_bits string into a list of bit positions.
        
        Supports multiple formats:
        - Single bit: "5" -> [5]
        - Comma-separated: "0,1,7" -> [0,1,7]
        - Range: "0-7" -> [0,1,2,3,4,5,6,7]
        - Mixed: "0-7,16,17" -> [0,1,2,3,4,5,6,7,16,17]
        
        Args:
            target_bits_str: String representation of target bits
            
        Returns:
            List of unique bit positions, sorted in ascending order
            
        Raises:
            ValueError: If string format is invalid or contains invalid numbers
            
        Example:
            parse_target_bits("0,1,7") -> [0, 1, 7]
            parse_target_bits("0-7") -> [0, 1, 2, 3, 4, 5, 6, 7]
            parse_target_bits("0-7,16,17") -> [0, 1, 2, 3, 4, 5, 6, 7, 16, 17]
        """
        if not target_bits_str or not target_bits_str.strip():
            raise ValueError("Target bits string cannot be empty")
        
        target_bits_str = target_bits_str.strip()
        bit_positions = set()  # Use set to avoid duplicates
        
        # Split by comma and process each part
        parts = [part.strip() for part in target_bits_str.split(',')]
        
        for part in parts:
            if not part:
                continue
                
            # Check if it's a range (contains '-')
            if '-' in part:
                range_match = re.match(r'^(\d+)-(\d+)$', part)
                if not range_match:
                    raise ValueError(f"Invalid range format: '{part}'. Expected format: 'start-end'")
                
                start_bit = int(range_match.group(1))
                end_bit = int(range_match.group(2))
                
                if start_bit > end_bit:
                    raise ValueError(f"Invalid range: start bit {start_bit} > end bit {end_bit}")
                
                # Add all bits in range
                bit_positions.update(range(start_bit, end_bit + 1))
            else:
                # Single bit
                if not re.match(r'^\d+$', part):
                    raise ValueError(f"Invalid bit position: '{part}'. Must be a non-negative integer")
                
                bit_position = int(part)
                bit_positions.add(bit_position)
        
        # Convert to sorted list
        result = sorted(list(bit_positions))
        
        if not result:
            raise ValueError("No valid bit positions found in target_bits string")
        
        return result
    
    @staticmethod
    def validate_bit_positions(positions: List[int], max_bits: int) -> bool:
        """
        Validate that all bit positions are within the valid range.
        
        Args:
            positions: List of bit positions to validate
            max_bits: Maximum number of bits (exclusive upper bound)
            
        Returns:
            True if all positions are valid, False otherwise
            
        Example:
            validate_bit_positions([0, 1, 7], 8) -> True
            validate_bit_positions([0, 1, 8], 8) -> False  # bit 8 is out of range
        """
        if not positions:
            return False
        
        if max_bits <= 0:
            return False
        
        for pos in positions:
            if pos < 0 or pos >= max_bits:
                logger.warning(f"Bit position {pos} out of range [0, {max_bits-1}]")
                return False
        
        return True
    
    @staticmethod
    def get_max_bits_for_data(data: bytes) -> int:
        """
        Get the maximum number of bits for the given data.
        
        Args:
            data: Input byte data
            
        Returns:
            Maximum number of bits (length * 8)
        """
        return len(data) * 8
    
    @staticmethod
    def create_bit_mask(bit_positions: List[int], data_length: int) -> bytes:
        """
        Create a bit mask for the specified bit positions.
        
        Args:
            bit_positions: List of bit positions to set in mask
            data_length: Length of data in bytes
            
        Returns:
            Byte mask with specified bits set to 1
            
        Example:
            create_bit_mask([0, 1, 7], 1) -> b'\x83'  # 10000011
        """
        if data_length <= 0:
            raise ValueError("Data length must be positive")
        
        mask = bytearray(data_length)
        max_bits = data_length * 8
        
        for bit_pos in bit_positions:
            if 0 <= bit_pos < max_bits:
                byte_index = bit_pos // 8
                bit_offset = bit_pos % 8
                mask[byte_index] |= (1 << bit_offset)
        
        return bytes(mask)
    
    @staticmethod
    def apply_bit_mask(data: bytes, mask: bytes, operation: str = 'flip') -> bytes:
        """
        Apply a bit mask to data using the specified operation.
        
        Args:
            data: Input byte data
            mask: Bit mask to apply
            operation: 'flip' (XOR), 'set' (OR), or 'clear' (AND NOT)
            
        Returns:
            Result of mask operation
            
        Raises:
            ValueError: If operation is invalid or data/mask lengths don't match
        """
        if len(data) != len(mask):
            raise ValueError("Data and mask must have the same length")
        
        result = bytearray(data)
        
        if operation == 'flip':
            for i in range(len(result)):
                result[i] ^= mask[i]
        elif operation == 'set':
            for i in range(len(result)):
                result[i] |= mask[i]
        elif operation == 'clear':
            for i in range(len(result)):
                result[i] &= ~mask[i]
        else:
            raise ValueError(f"Invalid operation: {operation}. Must be 'flip', 'set', or 'clear'")
        
        return bytes(result)


# Convenience functions for common operations
def flip_bit(data: bytes, bit_position: int) -> bytes:
    """Convenience function for BitManipulator.flip_bit()"""
    return BitManipulator.flip_bit(data, bit_position)


def set_bit(data: bytes, bit_position: int, value: bool) -> bytes:
    """Convenience function for BitManipulator.set_bit()"""
    return BitManipulator.set_bit(data, bit_position, value)


def get_bit(data: bytes, bit_position: int) -> bool:
    """Convenience function for BitManipulator.get_bit()"""
    return BitManipulator.get_bit(data, bit_position)


def parse_target_bits(target_bits_str: str) -> List[int]:
    """Convenience function for BitManipulator.parse_target_bits()"""
    return BitManipulator.parse_target_bits(target_bits_str)


def validate_bit_positions(positions: List[int], max_bits: int) -> bool:
    """Convenience function for BitManipulator.validate_bit_positions()"""
    return BitManipulator.validate_bit_positions(positions, max_bits) 