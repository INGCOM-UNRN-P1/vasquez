"""Tests de las funcionalidades QoL y subcomandos de VASQUEZ."""

import sys
import pytest
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


@pytest.mark.skipif(sys.platform == "win32", reason="LD_PRELOAD no existe en Windows nativo")
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
            return 5; // 3 se reserva: en Windows es el código de abort()
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
    assert rep2.results[0].exit_code == 5


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


def test_realloc_null_injection_qol11(tmp_path):
    src = tmp_path / "realloc_null.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        int *p = malloc(sizeof(int) * 4);
        if (!p) return 1;
        int *np = realloc(p, sizeof(int) * 8);
        if (np == NULL) {
            // Manejo correcto: liberar el puntero previo preservado por el SO
            free(p);
            return 5;
        }
        free(np);
        return 0;
    }
    """)
    rep = evaluate_robustness(src, [FaultConfig(
        fault_type=FaultType.REALLOC_FAIL,
        fail_realloc_at=1,
        enable_trace=True,
        check_leaks=True
    )])
    assert rep.passed is True
    assert rep.results[0].exit_code == 5
    assert rep.results[0].handled_gracefully is True
    assert rep.results[0].leaks_detected is False


def test_posix_memalign_and_calloc_qol16(tmp_path):
    src = tmp_path / "memalign.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    #include <errno.h>
    int main(void) {
        void *ptr = NULL;
        int ret = posix_memalign(&ptr, 64, 128);
        if (ret == ENOMEM || ret != 0) {
            return 6;
        }
        free(ptr);
        return 0;
    }
    """)
    rep = evaluate_robustness(src, [FaultConfig(
        fault_type=FaultType.POSIX_MEMALIGN_FAIL,
        fail_posix_memalign_at=1,
        enable_trace=True
    )])
    assert rep.passed is True
    assert rep.results[0].exit_code == 6


def test_cascade_failure_mode_qol17(tmp_path):
    src = tmp_path / "cascade.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        void *p1 = malloc(16);
        void *p2 = malloc(32);
        void *p3 = calloc(4, 4);
        // En cascada, p1 falla y activa la cascada, haciendo que p2 y p3 también fallen
        if (p1 == NULL && p2 == NULL && p3 == NULL) {
            return 7;
        }
        if (p1) free(p1);
        if (p2) free(p2);
        if (p3) free(p3);
        return 0;
    }
    """)
    rep = evaluate_robustness(src, [FaultConfig(
        fault_type=FaultType.MALLOC_FAIL,
        fail_at_invocation=1,
        cascade_failures=True,
        enable_trace=True
    )])
    assert rep.passed is True
    assert rep.results[0].exit_code == 7
    assert rep.results[0].cascade_triggered is True


def test_audit_free_null_qol20(tmp_path):
    src = tmp_path / "cleanup.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        void *a = malloc(10);
        void *b = NULL; // No llegó a asignarse
        // Rutina de limpieza defensiva
        free(a);
        free(b); // Invocación inocua de free(NULL)
        free(NULL); // Otra invocación explícita
        return 0;
    }
    """)
    rep = evaluate_robustness(src, [FaultConfig(
        fault_type=FaultType.AUDIT_FREE_NULL,
        audit_free_null=True,
        enable_trace=True
    )])
    assert rep.passed is True
    assert rep.results[0].free_null_calls >= 2
    assert "free(NULL)" in rep.results[0].diagnosis


def test_garbage_memory_poisoning_qol25(tmp_path):
    src = tmp_path / "garbage.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        unsigned char *buf = malloc(16);
        if (!buf) return 1;
        // Si la memoria fue envenenada con 0xCD, el primer byte será 0xCD
        int es_basura = (buf[0] == 0xCD && buf[15] == 0xCD);
        free(buf);
        return es_basura ? 8 : 0;
    }
    """)
    rep = evaluate_robustness(src, [FaultConfig(
        fault_type=FaultType.GARBAGE_MEMORY,
        fail_at_invocation=-1,
        garbage_memory=True,
        poison_byte=0xCD,
        enable_trace=True
    )])
    assert rep.passed is True
    assert rep.results[0].exit_code == 8
    assert rep.results[0].garbage_memory_injected is True


def test_cli_qol_options(tmp_path):
    src = tmp_path / "app_qol.c"
    src.write_text("""
    #include <stdlib.h>
    int main(void) {
        void *p = malloc(16);
        free(p);
        free(NULL);
        return 0;
    }
    """)
    res = runner.invoke(app, [
        "inject", str(src),
        "--fail-realloc-at", "1",
        "--cascade",
        "--audit-free-null",
        "--garbage-memory",
        "--poison-byte", "170",
        "--json"
    ])
    assert res.exit_code == 0
    assert '"free_null_calls": 1' in res.output



def test_salida_redirigida_en_windows_usa_utf8(monkeypatch):
    import io
    from vasquez.cli import _forzar_utf8

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "platform", "win32")
    _forzar_utf8(stream)
    stream.write("\u2713 Diagnóstico \u274c")
    stream.flush()
    assert stream.buffer.getvalue().decode("utf-8") == "\u2713 Diagnóstico \u274c"


def test_salida_fuera_de_windows_no_se_modifica(monkeypatch):
    import io
    from vasquez.cli import _forzar_utf8

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "platform", "linux")
    _forzar_utf8(stream)
    assert stream.encoding == "cp1252"
