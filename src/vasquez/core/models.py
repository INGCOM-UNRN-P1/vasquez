"""Modelos de datos para la inyección de fallos en VASQUEZ."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FaultType(str, Enum):
    MALLOC_FAIL = "malloc"
    CALLOC_FAIL = "calloc"
    REALLOC_FAIL = "realloc"
    FOPEN_FAIL = "fopen"
    FWRITE_FAIL = "fwrite"


class FaultConfig(BaseModel):
    fault_type: FaultType
    fail_at_invocation: int = 1  # 1 = fallar en la 1ra llamada, 2 = fallar en la 2da, etc.
    errno_value: int = 12  # ENOMEM=12, EACCES=13, ENOENT=2


class FaultRunResult(BaseModel):
    fault_config: FaultConfig
    exit_code: int
    signal_name: Optional[str] = None  # "SIGSEGV", "SIGABRT", etc.
    handled_gracefully: bool  # True si no crasheó con señal fatal y manejó el error
    stdout: str = ""
    stderr: str = ""
    diagnosis: str = ""


class RobustnessReport(BaseModel):
    target_binary: str
    total_scenarios_tested: int = 0
    passed_scenarios_count: int = 0
    crashed_scenarios_count: int = 0
    results: List[FaultRunResult] = Field(default_factory=list)
    passed: bool = True
