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
from vasquez.core.cache import get_cached_injector_library
from vasquez.core.crash_classifier import classify_execution
from vasquez.core.leak_checker import analyze_trace_for_leaks


def run_single_fault_scenario(
    binary_path: Path,
    fault: FaultConfig,
    so_path: Optional[Path] = None,
    input_data: str = "",
    timeout: float = 3.0
) -> FaultRunResult:
    """Ejecuta el binario inyectando un fallo determinado y analiza la respuesta."""
    if not so_path or not so_path.exists():
        so_path = get_cached_injector_library()

    env = os.environ.copy()
    preload_key = "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"
    env[preload_key] = str(so_path.resolve())

    # Configuración de fallos de memoria
    if fault.fault_type in (FaultType.MALLOC_FAIL, FaultType.CALLOC_FAIL, FaultType.REALLOC_FAIL, FaultType.STRDUP_FAIL, FaultType.POSIX_MEMALIGN_FAIL):
        if fault.fail_at_invocation > 0:
            env["VASQUEZ_MALLOC_FAIL_AT"] = str(fault.fail_at_invocation)
        if fault.fail_probability > 0.0:
            env["VASQUEZ_MALLOC_PROB"] = str(fault.fail_probability)

    elif fault.fault_type == FaultType.PROBABILISTIC:
        env["VASQUEZ_MALLOC_PROB"] = str(fault.fail_probability or 0.20)

    # Configuración de fallos de archivos
    elif fault.fault_type == FaultType.FOPEN_FAIL:
        env["VASQUEZ_FOPEN_FAIL_AT"] = str(fault.fail_at_invocation)
        env["VASQUEZ_ERRNO"] = str(fault.errno_value)

    elif fault.fault_type == FaultType.FWRITE_FAIL:
        env["VASQUEZ_FAIL_WRITE_AFTER_BYTES"] = str(fault.fail_after_bytes if fault.fail_after_bytes >= 0 else 0)

    trace_file_path = None
    if fault.enable_trace or fault.check_leaks:
        trace_file_path = binary_path.parent / f"vasquez_trace_{os.getpid()}_{fault.fail_at_invocation}.log"
        env["VASQUEZ_TRACE_FILE"] = str(trace_file_path.resolve())

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

        category, diag, handled = classify_execution(exit_code, signal_name, fault)

        trace_lines: List[str] = []
        leaks_detected = False
        if trace_file_path and trace_file_path.exists():
            try:
                trace_lines = trace_file_path.read_text(encoding="utf-8", errors="replace").splitlines()
                if fault.check_leaks:
                    leaks_detected, leak_diag = analyze_trace_for_leaks(trace_lines)
                    if leaks_detected:
                        diag += f" Advertencia: {leak_diag}"
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
    input_data: str = ""
) -> RobustnessReport:
    """Evalúa la robustez del programa ante una batería de fallos de entorno."""
    so_path = get_cached_injector_library()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        if source_or_binary.suffix == ".c":
            bin_path = tmp_path / "target_app"
            comp = subprocess.run(
                ["gcc", "-O0", "-g", str(source_or_binary), "-o", str(bin_path)],
                capture_output=True,
                check=False
            )
            if comp.returncode != 0:
                raise RuntimeError(f"Error compilando {source_or_binary}: {comp.stderr.decode('utf-8', errors='replace')}")
            target_bin = bin_path
        else:
            target_bin = source_or_binary

        if not scenarios:
            # Batería estándar completa: malloc en 1ra y 2da llamada, fopen en 1ra llamada, fwrite disco lleno
            scenarios = [
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1, enable_trace=True),
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=2, enable_trace=True),
                FaultConfig(fault_type=FaultType.FOPEN_FAIL, fail_at_invocation=1, errno_value=13),
            ]

        results = []
        crashed_count = 0
        passed_count = 0

        for sc in scenarios:
            res = run_single_fault_scenario(target_bin, sc, so_path=so_path, input_data=input_data)
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
