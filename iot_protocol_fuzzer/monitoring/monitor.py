"""
Monitor module for tracking and analyzing fuzzing campaign results.

Pluggable monitor architecture:
- BaseMonitor: unified interface and baseline metrics
- Protocol-specific monitors: CANMonitor, UARTMonitor, SPIMonitor
- MonitorRegistry & create_monitor: factory/registry for protocol selection

Backwards compatible: `Monitor` remains a generic implementation.
"""

import logging
from typing import Optional, Dict, Any, Callable
from ..harnesses.base import HarnessResult

logger = logging.getLogger("fuzzer.monitor")


class BaseMonitor:
    """Abstract baseline for monitors."""
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def process_case(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        raise NotImplementedError

    def start(self) -> None:
        """Optional: start active probing/monitoring."""
        return None

    def stop(self) -> None:
        """Optional: stop active probing/monitoring."""
        return None

    def reset(self) -> None:
        raise NotImplementedError

    def get_stats(self) -> Dict[str, Any]:
        raise NotImplementedError

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "passive_aggregation": True,
            "active_probe": False,
            "protocol_specific_metrics": False,
        }


class Monitor(BaseMonitor):
    """
    Monitor class that tracks and analyzes fuzzing campaign results.
    
    This class processes test cases and their results, potentially
    providing feedback for the fuzzing campaign.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
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


class CANMonitor(Monitor):
    """Protocol-specific monitor for CAN bus."""

    def process_case(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        super().process_case(idx, payload, result)
        # Additional CAN-specific logging can be toggled via config in future
        if result.crashed:
            try:
                # Keep the existing 8-byte frame split as CAN hinting
                frames = []
                for i in range(0, len(payload), 8):
                    frames.append(payload[i:i+8].hex())
                logger.warning(f"[Case {idx}] CAN frames ({len(frames)} total): {frames}")
            except Exception:
                pass

    def get_capabilities(self) -> Dict[str, bool]:
        caps = super().get_capabilities()
        caps["protocol_specific_metrics"] = True
        return caps


class UARTMonitor(Monitor):
    """Protocol-specific monitor for UART."""

    def process_case(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        super().process_case(idx, payload, result)
        # For UART, emphasize timeout diagnostics
        if result.timeout:
            logger.info(f"[Case {idx}] UART no response/timeout detected")

    def get_capabilities(self) -> Dict[str, bool]:
        caps = super().get_capabilities()
        # UART can optionally enable active probing in future via config
        caps["active_probe"] = bool(self.config.get("active_probe_enabled", False))
        return caps


class SPIMonitor(Monitor):
    """Protocol-specific monitor for SPI."""

    def process_case(self, idx: int, payload: bytes, result: HarnessResult) -> None:
        super().process_case(idx, payload, result)

    def get_capabilities(self) -> Dict[str, bool]:
        caps = super().get_capabilities()
        caps["protocol_specific_metrics"] = True
        return caps


class MonitorRegistry:
    """Registry for protocol-specific monitor creators."""

    _creators: Dict[str, Callable[[Optional[Dict[str, Any]]], BaseMonitor]] = {}

    @classmethod
    def register(cls, protocol: str, creator: Callable[[Optional[Dict[str, Any]]], BaseMonitor]) -> None:
        proto = (protocol or "").strip().lower()
        if not proto:
            return
        cls._creators[proto] = creator

    @classmethod
    def create_monitor(cls, protocol_type: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> BaseMonitor:
        proto = (protocol_type or "").strip().lower()
        creator = cls._creators.get(proto)
        if creator is not None:
            return creator(config)
        # Default to generic Monitor
        return Monitor(config)


def create_monitor(protocol_type: Optional[str] = None, config: Optional[Dict[str, Any]] = None) -> BaseMonitor:
    """Factory function backed by MonitorRegistry."""
    return MonitorRegistry.create_monitor(protocol_type, config)


# Default registrations
MonitorRegistry.register("can", lambda cfg: CANMonitor(cfg))
MonitorRegistry.register("uart", lambda cfg: UARTMonitor(cfg))
MonitorRegistry.register("spi", lambda cfg: SPIMonitor(cfg))