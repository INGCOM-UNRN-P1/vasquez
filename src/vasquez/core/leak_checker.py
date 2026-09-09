"""Auditor de fugas de memoria (leak checker) en caminos de error para VASQUEZ."""

from __future__ import annotations
import re
from typing import List, Set, Tuple


def analyze_trace_for_leaks(trace_lines: List[str]) -> Tuple[bool, str]:
    """Analiza la traza de llamadas del inyector para verificar que todos los punteros obtenidos fueron liberados.
    
    Retorna: (leaks_detectados, mensaje_diagnostico)
    """
    allocated_ptrs: Set[str] = set()
    freed_ptrs: Set[str] = set()

    for line in trace_lines:
        # Match allocations: e.g. [VASQUEZ] malloc(...) -> 0x5555...
        alloc_match = re.search(r'(?:malloc|calloc|realloc|strdup|posix_memalign)\(.*?\)\s*->\s*(0x[0-9a-fA-F]+)', line)
        if alloc_match:
            ptr = alloc_match.group(1).lower()
            if ptr != "0x0" and ptr != "(nil)":
                allocated_ptrs.add(ptr)

        # Match deallocations: [VASQUEZ] free(0x5555...)
        free_match = re.search(r'free\((0x[0-9a-fA-F]+)\)', line)
        if free_match:
            ptr = free_match.group(1).lower()
            freed_ptrs.add(ptr)

    # Si hay traza pero el programa finalizó prematuramente por error
    unfreed = allocated_ptrs - freed_ptrs
    if len(unfreed) > 0 and len(trace_lines) > 2:
        msg = f"Se detectaron {len(unfreed)} reservas previas sin liberar en la rama de error antes de retornar."
        return True, msg

    return False, "No se detectaron fugas de memoria evidentes en la traza de ejecución."


def audit_free_null(trace_lines: List[str]) -> Tuple[int, int, str]:
    """Audita las llamadas a free(NULL) en las ramas de limpieza.
    
    Retorna: (free_null_count, total_free_count, mensaje_pedagogico)
    """
    free_null_count = 0
    total_free_count = 0

    for line in trace_lines:
        if "free(NULL)" in line or re.search(r'free\((?:0x0|\(nil\)|NULL)\)', line):
            free_null_count += 1
            total_free_count += 1
        elif re.search(r'free\((0x[0-9a-fA-F]+)\)', line):
            total_free_count += 1

    if free_null_count > 0:
        msg = (
            f"Se auditaron {free_null_count} llamada(s) a free(NULL) de un total de {total_free_count} liberaciones. "
            "En C estándar (ISO C99/C11 §7.22.3.4), invocar free(NULL) es una operación completamente segura y sin efecto (no-op), "
            "común en rutinas de limpieza defensivas."
        )
    else:
        msg = f"Se auditaron {total_free_count} llamada(s) a free() (ninguna invocó free(NULL))."

    return free_null_count, total_free_count, msg

