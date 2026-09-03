from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class PluginMeta:
    name: str
    module_path: str
    enabled: bool = True
    description: str = ""
    author: str = ""
    license: str = ""
    parameters: Optional[Dict[str, Any]] = None
    requirements: tuple[str, ...] = ()

