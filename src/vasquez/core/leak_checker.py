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
        alloc_match = re.search(r'(?:malloc|calloc|realloc|strdup)\(.*?\)\s*->\s*(0x[0-9a-fA-F]+)', line)
        if alloc_match:
            ptr = alloc_match.group(1).lower()
            if ptr != "0x0" and ptr != "(nil)":
                allocated_ptrs.add(ptr)

        # Match deallocations: [VASQUEZ] fclose / free
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
