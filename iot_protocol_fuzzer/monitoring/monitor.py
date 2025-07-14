"""
Monitor module for tracking and analyzing fuzzing campaign results.
"""

import logging
from typing import Optional, Dict, Any
from ..harnesses.base import HarnessResult

logger = logging.getLogger("fuzzer.monitor")


class Monitor:
    """
    Monitor class that tracks and analyzes fuzzing campaign results.
    
    This class processes test cases and their results, potentially
    providing feedback for the fuzzing campaign.
    """
    
    def __init__(self):
        self.crash_count = 0
        self.timeout_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_cases = 0
        
    def process_case(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        """
        Process a single test case result.
        
        Args:
            idx: Test case index
            payload: The test data that was sent
            result: The result from the harness execution
        """
        self.total_cases += 1
        
        if result.crashed:
            self.crash_count += 1
            logger.warning(f"[Case {idx}] CRASH detected with payload length {len(payload)}")
            
            # Print detailed hex data for crash analysis
            hex_data = payload.hex()
            logger.warning(f"[Case {idx}] Malformed CAN data (hex): {hex_data}")
            
            # Show how data would be split into CAN frames (8 bytes each)
            frames = []
            for i in range(0, len(payload), 8):
                chunk = payload[i:i+8]
                frames.append(chunk.hex())
            
            logger.warning(f"[Case {idx}] CAN frames ({len(frames)} total):")
            for frame_idx, frame_hex in enumerate(frames):
                logger.warning(f"  Frame {frame_idx}: {frame_hex} ({len(payload[frame_idx*8:frame_idx*8+8])} bytes)")
            
            # Show printable characters if any
            try:
                printable = ''.join(chr(b) if 32 <= b <= 126 else '.' for b in payload)
                logger.warning(f"[Case {idx}] Printable chars: {printable}")
            except:
                logger.warning(f"[Case {idx}] No printable characters")
                
        elif result.timeout:
            self.timeout_count += 1
            logger.debug(f"[Case {idx}] Timeout occurred")
            
        elif result.error:
            self.error_count += 1
            logger.debug(f"[Case {idx}] Error occurred: {result.error}")
            
        else:
            self.success_count += 1
            logger.debug(f"[Case {idx}] Success")
            
    def get_stats(self) -> Dict[str, Any]:
        """
        Get current statistics about the fuzzing campaign.
        
        Returns:
            Dictionary containing campaign statistics
        """
        return {
            "total_cases": self.total_cases,
            "crashes": self.crash_count,
            "timeouts": self.timeout_count,
            "errors": self.error_count,
            "successes": self.success_count,
            "crash_rate": self.crash_count / self.total_cases if self.total_cases > 0 else 0,
        }
        
    def reset(self) -> None:
        """Reset all counters."""
        self.crash_count = 0
        self.timeout_count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_cases = 0 