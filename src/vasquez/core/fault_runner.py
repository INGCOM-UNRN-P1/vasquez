"""Ejecutor de escenarios de inyección de fallos con LD_PRELOAD."""

import os
import signal
import tempfile
import subprocess
from pathlib import Path
from typing import List, Optional
from vasquez.core.models import FaultConfig, FaultType, FaultRunResult, RobustnessReport
from vasquez.core.injector_c import compile_preload_library


def run_single_fault_scenario(
    binary_path: Path,
    fault: FaultConfig,
    so_path: Path,
    input_data: str = "",
    timeout: float = 3.0
) -> FaultRunResult:
    """Ejecuta el binario inyectando un fallo determinado y analiza la respuesta."""
    env = os.environ.copy()
    env["LD_PRELOAD"] = str(so_path.resolve())

    if fault.fault_type in (FaultType.MALLOC_FAIL, FaultType.CALLOC_FAIL, FaultType.REALLOC_FAIL):
        env["VASQUEZ_MALLOC_FAIL_AT"] = str(fault.fail_at_invocation)
    elif fault.fault_type == FaultType.FOPEN_FAIL:
        env["VASQUEZ_FOPEN_FAIL_AT"] = str(fault.fail_at_invocation)
        env["VASQUEZ_ERRNO"] = str(fault.errno_value)

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

        # Si crasheó con SIGSEGV, SIGABRT, SIGBUS -> NO fue manejado de forma defensiva
        crashed = signal_name in ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGFPE")
        handled = not crashed

        diag = ""
        if crashed:
            diag = f"El programa crasheó con {signal_name} al fallar {fault.fault_type.value} en la llamada #{fault.fail_at_invocation}. Faltó validar 'if (ptr == NULL)'."
        elif exit_code != 0:
            diag = f"El programa detectó el fallo y finalizó ordenadamente con código de error {exit_code}."
        else:
            diag = "El programa manejó el fallo exitosamente sin crashear."

        return FaultRunResult(
            fault_config=fault,
            exit_code=exit_code,
            signal_name=signal_name,
            handled_gracefully=handled,
            stdout=res.stdout,
            stderr=res.stderr,
            diagnosis=diag
        )

    except subprocess.TimeoutExpired:
        return FaultRunResult(
            fault_config=fault,
            exit_code=124,
            signal_name="TIMEOUT",
            handled_gracefully=False,
            diagnosis=f"Timeout al inyectar fallo en {fault.fault_type.value} (posible bucle infinito en manejo de error)."
        )


def evaluate_robustness(
    source_or_binary: Path,
    scenarios: Optional[List[FaultConfig]] = None,
    input_data: str = ""
) -> RobustnessReport:
    """Evalúa la robustez del programa ante una batería de fallos de entorno."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        so_path = tmp_path / "libvasquez_inject.so"
        compile_preload_library(so_path)

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
            # Batería estándar: malloc en 1ra llamada, malloc en 2da llamada, fopen en 1ra llamada
            scenarios = [
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1),
                FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=2),
                FaultConfig(fault_type=FaultType.FOPEN_FAIL, fail_at_invocation=1, errno_value=13),
            ]

        results = []
        crashed_count = 0
        passed_count = 0

        for sc in scenarios:
            res = run_single_fault_scenario(target_bin, sc, so_path, input_data=input_data)
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
