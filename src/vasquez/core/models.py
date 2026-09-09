"""Modelos de datos para la inyección de fallos en VASQUEZ."""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FaultType(str, Enum):
    MALLOC_FAIL = "malloc"
    CALLOC_FAIL = "calloc"
    REALLOC_FAIL = "realloc"
    STRDUP_FAIL = "strdup"
    POSIX_MEMALIGN_FAIL = "posix_memalign"
    FOPEN_FAIL = "fopen"
    FWRITE_FAIL = "fwrite"
    FREAD_FAIL = "fread"
    FCLOSE_FAIL = "fclose"
    PROBABILISTIC = "probabilistic"
    CASCADE = "cascade"
    GARBAGE_MEMORY = "garbage_memory"
    AUDIT_FREE_NULL = "audit_free_null"


class FaultConfig(BaseModel):
    fault_type: FaultType
    fail_at_invocation: int = 1  # 1 = fallar en la 1ra llamada, 2 = 2da, etc. (-1 para deshabilitar)
    fail_probability: float = 0.0  # Probabilidad de fallo (0.0 a 1.0)
    fail_after_bytes: int = -1  # Para fwrite/write (simulación de disco lleno)
    fail_realloc_at: Optional[int] = None  # Mejora 11: llamada específica a realloc para fallar
    fail_calloc_at: Optional[int] = None  # Mejora 16: llamada específica a calloc para fallar
    fail_posix_memalign_at: Optional[int] = None  # Mejora 16: llamada específica a posix_memalign
    cascade_failures: bool = False  # Mejora 17: fallo en cascada tras el primer error
    audit_free_null: bool = False  # Mejora 20: auditar invocaciones de free(NULL)
    garbage_memory: bool = False  # Mejora 25: rellenar memoria asignada con patrón basura
    poison_byte: int = 0xA5  # Byte de envenenamiento (por defecto 0xA5)
    errno_value: int = 12  # ENOMEM=12, EACCES=13, ENOENT=2, ENOSPC=28
    enable_trace: bool = False
    check_leaks: bool = False


class FaultRunResult(BaseModel):
    fault_config: FaultConfig
    exit_code: int
    signal_name: Optional[str] = None  # "SIGSEGV", "SIGABRT", "SIGBUS", etc.
    handled_gracefully: bool  # True si no crasheó con señal fatal y manejó el error
    stdout: str = ""
    stderr: str = ""
    diagnosis: str = ""
    crash_category: Optional[str] = None  # "NULL_DEREFERENCE", "DOUBLE_FREE", "CLEAN_ERROR_EXIT", "SUCCESS"
    leaks_detected: bool = False
    free_null_calls: int = 0
    total_free_calls: int = 0
    cascade_triggered: bool = False
    garbage_memory_injected: bool = False
    trace_log: List[str] = Field(default_factory=list)


class RobustnessReport(BaseModel):
    target_binary: str
    total_scenarios_tested: int = 0
    passed_scenarios_count: int = 0
    crashed_scenarios_count: int = 0
    results: List[FaultRunResult] = Field(default_factory=list)
    passed: bool = True
