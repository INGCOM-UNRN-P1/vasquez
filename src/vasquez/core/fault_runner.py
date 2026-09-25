"""Ejecutor de escenarios de inyección de fallos con LD_PRELOAD / DYLD_INSERT_LIBRARIES."""

from __future__ import annotations
import os
import sys
import signal
import tempfile
import subprocess
from pathlib import Path
from typing import List, Optional
from vasquez.core.models import FaultConfig, FaultType, FaultRunResult, RobustnessReport
from vasquez.core.cache import get_cached_injector_library, get_cached_link_object
from vasquez.core.crash_classifier import classify_execution, senal_desde_codigo_windows
from vasquez.core.injector_c import preload_soportado
from vasquez.core.injector_link import MECANISMO_PRELOAD, MECANISMO_ENLACE, build_instrumented_binary
from vasquez.core.leak_checker import analyze_trace_for_leaks, audit_free_null
from vasquez.core.constants import (
    ENV_MALLOC_FAIL_AT,
    ENV_CALLOC_FAIL_AT,
    ENV_REALLOC_FAIL_AT,
    ENV_POSIX_MEMALIGN_FAIL_AT,
    ENV_MALLOC_PROB,
    ENV_CASCADE_FAILS,
    ENV_GARBAGE_MEMORY,
    ENV_POISON_BYTE,
    ENV_FOPEN_FAIL_AT,
    ENV_ERRNO,
    ENV_FAIL_WRITE_AFTER_BYTES,
    ENV_FREAD_FAIL_AT,
    ENV_FCLOSE_FAIL_AT,
    ENV_TRACE_FILE,
)


def mecanismo_por_defecto() -> str:
    """Mecanismo de inyección de la plataforma: precarga donde exista, enlace en Windows nativo."""
    return MECANISMO_PRELOAD if preload_soportado() else MECANISMO_ENLACE


def run_single_fault_scenario(
    binary_path: Path,
    fault: FaultConfig,
    so_path: Optional[Path] = None,
    input_data: str = "",
    timeout: float = 3.0,
    mecanismo: Optional[str] = None
) -> FaultRunResult:
    """Ejecuta el binario inyectando un fallo determinado y analiza la respuesta.

    Con el mecanismo de enlace, ``binary_path`` debe haber sido construido con
    ``build_instrumented_binary``: los ganchos ya están enlazados y sólo se configuran por entorno.
    """
    mecanismo = mecanismo or mecanismo_por_defecto()
    env = os.environ.copy()

    if mecanismo == MECANISMO_PRELOAD:
        if not so_path or not so_path.exists():
            so_path = get_cached_injector_library()

        preload_key = "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"
        env[preload_key] = str(so_path.resolve())

    # Configuración de fallos de memoria específicos (Mejoras 11 y 16) y generales
    if fault.fail_realloc_at is not None and fault.fail_realloc_at > 0:
        env[ENV_REALLOC_FAIL_AT] = str(fault.fail_realloc_at)
    elif fault.fault_type == FaultType.REALLOC_FAIL and fault.fail_at_invocation > 0:
        env[ENV_MALLOC_FAIL_AT] = str(fault.fail_at_invocation)

    if fault.fail_calloc_at is not None and fault.fail_calloc_at > 0:
        env[ENV_CALLOC_FAIL_AT] = str(fault.fail_calloc_at)
    elif fault.fault_type == FaultType.CALLOC_FAIL and fault.fail_at_invocation > 0:
        env[ENV_MALLOC_FAIL_AT] = str(fault.fail_at_invocation)

    if fault.fail_posix_memalign_at is not None and fault.fail_posix_memalign_at > 0:
        env[ENV_POSIX_MEMALIGN_FAIL_AT] = str(fault.fail_posix_memalign_at)
    elif fault.fault_type == FaultType.POSIX_MEMALIGN_FAIL and fault.fail_at_invocation > 0:
        env[ENV_MALLOC_FAIL_AT] = str(fault.fail_at_invocation)

    if fault.fault_type in (FaultType.MALLOC_FAIL, FaultType.STRDUP_FAIL):
        if fault.fail_at_invocation > 0:
            env[ENV_MALLOC_FAIL_AT] = str(fault.fail_at_invocation)
        if fault.fail_probability > 0.0:
            env[ENV_MALLOC_PROB] = str(fault.fail_probability)

    elif fault.fault_type == FaultType.PROBABILISTIC:
        env[ENV_MALLOC_PROB] = str(fault.fail_probability or 0.20)

    # Modo Cascada (Mejora 17)
    if fault.cascade_failures or fault.fault_type == FaultType.CASCADE:
        env[ENV_CASCADE_FAILS] = "1"

    # Memoria Basura / Envenenamiento (Mejora 25)
    if fault.garbage_memory or fault.fault_type == FaultType.GARBAGE_MEMORY:
        env[ENV_GARBAGE_MEMORY] = "1"
        env[ENV_POISON_BYTE] = str(fault.poison_byte)

    # Configuración de fallos de archivos
    if fault.fault_type == FaultType.FOPEN_FAIL:
        env[ENV_FOPEN_FAIL_AT] = str(fault.fail_at_invocation)
        env[ENV_ERRNO] = str(fault.errno_value)

    elif fault.fault_type == FaultType.FWRITE_FAIL:
        env[ENV_FAIL_WRITE_AFTER_BYTES] = str(fault.fail_after_bytes if fault.fail_after_bytes >= 0 else 0)

    elif fault.fault_type == FaultType.FREAD_FAIL:
        env[ENV_FREAD_FAIL_AT] = str(fault.fail_at_invocation)

    elif fault.fault_type == FaultType.FCLOSE_FAIL:
        env[ENV_FCLOSE_FAIL_AT] = str(fault.fail_at_invocation)

    trace_file_path = None
    if fault.enable_trace or fault.check_leaks or fault.audit_free_null or fault.fault_type == FaultType.AUDIT_FREE_NULL:
        trace_file_path = binary_path.parent / f"vasquez_trace_{os.getpid()}_{fault.fail_at_invocation}.log"
        env[ENV_TRACE_FILE] = str(trace_file_path.resolve())

    try:
        res = subprocess.run(
            [str(binary_path.resolve())],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False
        )

        exit_code = res.returncode
        signal_name = None

        if exit_code < 0:
            sig_num = -exit_code
            try:
                signal_name = signal.Signals(sig_num).name
            except Exception:
                signal_name = f"SIG_{sig_num}"
        elif sys.platform == "win32":
            signal_name = senal_desde_codigo_windows(exit_code)

        category, diag, handled = classify_execution(exit_code, signal_name, fault)

        trace_lines: List[str] = []
        leaks_detected = False
        free_null_count = 0
        total_free_count = 0
        cascade_triggered = False
        garbage_injected = False

        if trace_file_path and trace_file_path.exists():
            try:
                trace_lines = trace_file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                cascade_triggered = any("CASCADA" in line for line in trace_lines)
                garbage_injected = any("MEMORIA BASURA ENVENENADA" in line for line in trace_lines)

                if fault.check_leaks:
                    leaks_detected, leak_diag = analyze_trace_for_leaks(trace_lines)
                    if leaks_detected:
                        diag += f" Advertencia: {leak_diag}"

                if fault.audit_free_null or fault.fault_type == FaultType.AUDIT_FREE_NULL or fault.enable_trace:
                    free_null_count, total_free_count, fn_diag = audit_free_null(trace_lines)
                    if fault.audit_free_null or fault.fault_type == FaultType.AUDIT_FREE_NULL:
                        diag += f" [{fn_diag}]"

                trace_file_path.unlink(missing_ok=True)
            except Exception:
                pass

        return FaultRunResult(
            fault_config=fault,
            exit_code=exit_code,
            signal_name=signal_name,
            handled_gracefully=handled,
            stdout=res.stdout,
            stderr=res.stderr,
            diagnosis=diag,
            crash_category=category,
            leaks_detected=leaks_detected,
            free_null_calls=free_null_count,
            total_free_calls=total_free_count,
            cascade_triggered=cascade_triggered,
            garbage_memory_injected=garbage_injected,
            trace_log=trace_lines
        )

    except subprocess.TimeoutExpired:
        if trace_file_path:
            trace_file_path.unlink(missing_ok=True)
        return FaultRunResult(
            fault_config=fault,
            exit_code=124,
            signal_name="TIMEOUT",
            handled_gracefully=False,
            crash_category="INFINITE_LOOP",
            diagnosis=f"Timeout superado al inyectar fallo en {fault.fault_type.value} (posible lazo infinito)."
        )


def evaluate_robustness(
    source_or_binary: Path,
    scenarios: Optional[List[FaultConfig]] = None,
    input_data: str = "",
    mecanismo: Optional[str] = None
) -> RobustnessReport:
    """Evalúa la robustez del programa ante una batería de fallos de entorno.

    ``mecanismo`` fuerza la vía de inyección (``"preload"`` o ``"enlace"``); por defecto se
    usa la de la plataforma. La vía de enlace sólo admite fuentes ``.c``.
    """
    mecanismo = mecanismo or mecanismo_por_defecto()
    if mecanismo == MECANISMO_ENLACE:
        return _evaluate_robustness_enlace(source_or_binary, scenarios, input_data)

    so_path = get_cached_injector_library()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        if source_or_binary.suffix == ".c":
            bin_path = tmp_path / "target_app"
            comp = subprocess.run(
                ["gcc", "-O0", "-g", "-fno-builtin-free", str(source_or_binary), "-o", str(bin_path)],
                capture_output=True,
                check=False
            )
            if comp.returncode != 0:
                raise RuntimeError(f"Error compilando {source_or_binary}: {comp.stderr.decode('utf-8', errors='replace')}")
            target_bin = bin_path
        else:
            target_bin = source_or_binary

        if not scenarios:
            # Batería estándar por defecto: malloc en 1ra y 2da llamada, fopen en 1ra llamada
            scenarios = [
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1, enable_trace=True),
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=2, enable_trace=True),
                FaultConfig(fault_type=FaultType.FOPEN_FAIL, fail_at_invocation=1, errno_value=13),
            ]

        results = []
        crashed_count = 0
        passed_count = 0

        for sc in scenarios:
            res = run_single_fault_scenario(target_bin, sc, so_path=so_path, input_data=input_data, mecanismo=MECANISMO_PRELOAD)
            results.append(res)
            if res.handled_gracefully:
                passed_count += 1
            else:
                crashed_count += 1

        all_passed = (crashed_count == 0)

        return RobustnessReport(
            target_binary=str(source_or_binary),
            total_scenarios_tested=len(results),
            passed_scenarios_count=passed_count,
            crashed_scenarios_count=crashed_count,
            results=results,
            passed=all_passed
        )


def _evaluate_robustness_enlace(
    source: Path,
    scenarios: Optional[List[FaultConfig]],
    input_data: str
) -> RobustnessReport:
    """Vía de enlace: compila el fuente con los ganchos del inyector y ejecuta la batería."""
    if source.suffix != ".c":
        raise RuntimeError(
            f"{source.name}: en esta plataforma la inyección se hace al enlazar y requiere el fuente .c; "
            "los binarios ya compilados no pueden instrumentarse."
        )

    injector_obj = get_cached_link_object()

    with tempfile.TemporaryDirectory() as tmp_dir:
        target_bin = build_instrumented_binary(source, Path(tmp_dir), injector_obj)

        if not scenarios:
            # Misma batería estándar que la vía LD_PRELOAD
            scenarios = [
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1, enable_trace=True),
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=2, enable_trace=True),
                FaultConfig(fault_type=FaultType.FOPEN_FAIL, fail_at_invocation=1, errno_value=13),
            ]

        results = [
            run_single_fault_scenario(target_bin, sc, input_data=input_data, mecanismo=MECANISMO_ENLACE)
            for sc in scenarios
        ]
        passed_count = sum(1 for r in results if r.handled_gracefully)
        crashed_count = len(results) - passed_count

        return RobustnessReport(
            target_binary=str(source),
            total_scenarios_tested=len(results),
            passed_scenarios_count=passed_count,
            crashed_scenarios_count=crashed_count,
            results=results,
            passed=(crashed_count == 0)
        )
