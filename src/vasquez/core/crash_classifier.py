"""Clasificador pedagógico de caídas y manejo defensivo para VASQUEZ."""

from __future__ import annotations
from typing import Optional, Tuple
from vasquez.core.models import FaultConfig, FaultType


def classify_execution(
    exit_code: int,
    signal_name: Optional[str],
    fault: FaultConfig
) -> Tuple[str, str, bool]:
    """Clasifica el resultado de la ejecución bajo inyección de fallos.
    
    Retorna: (categoria, diagnostico_es, handled_gracefully)
    """
    if signal_name == "SIGSEGV":
        diag = (
            f"El programa sufrió un fallo de segmentación (SIGSEGV) al fallar {fault.fault_type.value} en la llamada #{fault.fail_at_invocation}. "
            "Causa raíz: Se desreferenció un puntero retornado como NULL ('ptr->campo' o '*ptr') sin haber verificado previamente 'if (ptr == NULL)'."
        )
        return "NULL_DEREFERENCE", diag, False

    if signal_name == "SIGABRT":
        diag = (
            f"El programa abortó con SIGABRT durante el manejo del fallo en {fault.fault_type.value}. "
            "Causa raíz: Posible doble liberación de memoria (double free) o assert() no controlado al intentar limpiar recursos."
        )
        return "DOUBLE_FREE", diag, False

    if signal_name == "SIGBUS":
        diag = (
            f"El programa cayó con SIGBUS al fallar {fault.fault_type.value}. "
            "Causa raíz: Acceso a memoria no alineada o intento de escritura en mapeo inválido."
        )
        return "MISALIGNED_ACCESS", diag, False

    if signal_name == "TIMEOUT":
        diag = (
            f"Timeout superado durante la inyección de {fault.fault_type.value}. "
            "Causa raíz: El programa entró en un lazo infinito al intentar reintentar la operación fallida."
        )
        return "INFINITE_LOOP", diag, False

    if exit_code != 0:
        diag = (
            f"El programa detectó el fallo de {fault.fault_type.value} (#{fault.fail_at_invocation}) y finalizó "
            f"ordenadamente con código de error {exit_code} sin corromper memoria."
        )
        return "CLEAN_ERROR_EXIT", diag, True

    diag = (
        f"El programa manejó el fallo de {fault.fault_type.value} (#{fault.fail_at_invocation}) de manera elegante "
        "y completó su ejecución con código de salida 0."
    )
    return "SUCCESS", diag, True
