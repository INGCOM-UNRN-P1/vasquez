"""Clasificador pedagógico de caídas y manejo defensivo para VASQUEZ."""

from __future__ import annotations
from typing import Optional, Tuple
from vasquez.core.models import FaultConfig, FaultType

# Códigos de salida con que Windows termina un proceso ante una excepción no manejada (NTSTATUS)
# o un abort() del UCRT, traducidos a la señal POSIX equivalente para reutilizar la
# clasificación pedagógica.
NTSTATUS_A_SENAL = {
    0xC0000005: "SIGSEGV",  # STATUS_ACCESS_VIOLATION
    0xC00000FD: "SIGSEGV",  # STATUS_STACK_OVERFLOW
    0xC0000374: "SIGABRT",  # STATUS_HEAP_CORRUPTION (p. ej. double free)
    0xC0000409: "SIGABRT",  # STATUS_STACK_BUFFER_OVERRUN / __fastfail (abort del UCRT)
    3: "SIGABRT",           # _exit(3) de abort()/assert() del UCRT cuando no usa __fastfail
    0x80000002: "SIGBUS",   # STATUS_DATATYPE_MISALIGNMENT
    0xC0000094: "SIGFPE",   # STATUS_INTEGER_DIVIDE_BY_ZERO
    0xC000008E: "SIGFPE",   # STATUS_FLOAT_DIVIDE_BY_ZERO
    0xC000001D: "SIGILL",   # STATUS_ILLEGAL_INSTRUCTION
}


def senal_desde_codigo_windows(exit_code: int) -> Optional[str]:
    """Traduce el código de salida de un proceso Windows a la señal POSIX equivalente, si la hay."""
    return NTSTATUS_A_SENAL.get(exit_code & 0xFFFFFFFF)


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
