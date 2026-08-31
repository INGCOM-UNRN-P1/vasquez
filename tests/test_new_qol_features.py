"""Tests de las funcionalidades QoL y subcomandos de VASQUEZ."""

from pathlib import Path
from typer.testing import CliRunner
from vasquez.cli import app
from vasquez.core.models import FaultConfig, FaultType, RobustnessReport
from vasquez.core.fault_runner import evaluate_robustness
from vasquez.core.cache import get_cached_injector_library
from vasquez.core.crash_classifier import classify_execution
from vasquez.core.leak_checker import analyze_trace_for_leaks
from vasquez.core.doctor import ejecutar_diagnostico_doctor

runner = CliRunner()


def test_doctor_execution():
    rep = ejecutar_diagnostico_doctor()
    assert rep.all_ok is True
    assert any(c.name == "gcc" for c in rep.checks)

    res = runner.invoke(app, ["doctor", "--json"])
    assert res.exit_code == 0
    assert '"all_ok": true' in res.output


def test_cache_injector_compilation():
    so_path = get_cached_injector_library()
    assert so_path.exists()
    assert so_path.stat().st_size > 0
    # Segunda llamada usa caché
    so_path_2 = get_cached_injector_library()
    assert so_path == so_path_2


def test_crash_classifier():
    cfg = FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1)
    cat, diag, handled = classify_execution(139, "SIGSEGV", cfg)
    assert cat == "NULL_DEREFERENCE"
    assert handled is False
    assert "desreferenció un puntero" in diag

    cat_ok, diag_ok, handled_ok = classify_execution(1, None, cfg)
    assert cat_ok == "CLEAN_ERROR_EXIT"
    assert handled_ok is True

    cat_zero, _, handled_zero = classify_execution(0, None, cfg)
    assert cat_zero == "SUCCESS"
    assert handled_zero is True


def test_leak_checker():
    trace_clean = [
        "[VASQUEZ] malloc(100) -> 0x55555555 [#1]",
        "[VASQUEZ] free(0x55555555)",
    ]
    leaks, _ = analyze_trace_for_leaks(trace_clean)
    assert leaks is False

    trace_leaked = [
        "[VASQUEZ] malloc(100) -> 0x55551111 [#1]",
        "[VASQUEZ] malloc(200) -> NULL [FALLO FORZADO #2]",
        "[VASQUEZ] Trace finalizado",
    ]
    leaks_detected, diag = analyze_trace_for_leaks(trace_leaked)
    assert leaks_detected is True
    assert "reservas previas sin liberar" in diag


def test_calloc_and_realloc_interception(tmp_path):
    src = tmp_path / "alloc_test.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        int *arr = calloc(5, sizeof(int));
        if (arr == NULL) return 2;
        int *n_arr = realloc(arr, 10 * sizeof(int));
        if (n_arr == NULL) {
            free(arr);
            return 3;
        }
        free(n_arr);
        return 0;
    }
    """)
    # 1. Fallar en calloc
    rep1 = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.CALLOC_FAIL, fail_at_invocation=1)])
    assert rep1.passed is True
    assert rep1.results[0].exit_code == 2

    # 2. Fallar en realloc
    rep2 = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.REALLOC_FAIL, fail_at_invocation=2)])
    assert rep2.passed is True
    assert rep2.results[0].exit_code == 3


def test_fail_write_after_bytes(tmp_path):
    src = tmp_path / "write_test.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        FILE *f = fopen("test.tmp", "wb");
        if (!f) return 1;
        char buf[50] = "12345678901234567890123456789012345678901234567890";
        size_t written = fwrite(buf, 1, 50, f);
        fclose(f);
        if (written < 50) return 4;
        return 0;
    }
    """)
    # Simular que el disco solo acepta 10 bytes
    rep = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.FWRITE_FAIL, fail_after_bytes=10)])
    assert rep.passed is True
    assert rep.results[0].exit_code == 4


def test_probabilistic_stress_cli(tmp_path):
    src = tmp_path / "defensivo.c"
    src.write_text("""
    #include <stdlib.h>
    int main(void) {
        void *p = malloc(16);
        if (!p) return 1;
        free(p);
        return 0;
    }
    """)
    res = runner.invoke(app, ["stress", str(src), "--iterations", "3", "--prob", "0.5", "--json"])
    assert res.exit_code == 0
    assert '"passed": true' in res.output


def test_cli_inject_flags(tmp_path):
    src = tmp_path / "app.c"
    src.write_text("""
    #include <stdlib.h>
    int main(void) {
        void *p = malloc(10);
        if (!p) return 0;
        free(p);
        return 0;
    }
    """)
    res = runner.invoke(app, ["inject", str(src), "--fail-malloc-at", "1", "--trace", "--check-leaks", "--json"])
    assert res.exit_code == 0
    assert '"handled_gracefully": true' in res.output
