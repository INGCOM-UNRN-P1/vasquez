"""Tests de la vía de interceptación en enlace (usada en Windows nativo, sin LD_PRELOAD).

La vía es portable, así que se ejercita también en Linux forzando el mecanismo: los escenarios
de integración existentes se re-ejecutan íntegros contra ella para verificar paridad de
comportamiento con la vía LD_PRELOAD.
"""

import sys
import pytest
from typer.testing import CliRunner

import vasquez.core.doctor as doctor_mod
import vasquez.core.fault_runner as fault_runner
from vasquez.cli import app
from vasquez.core.cache import get_cached_link_object
from vasquez.core.crash_classifier import senal_desde_codigo_windows
from vasquez.core.doctor import ejecutar_diagnostico_doctor
from vasquez.core.fault_runner import evaluate_robustness
from vasquez.core.injector_link import MECANISMO_ENLACE, MECANISMO_PRELOAD, argumentos_redefinicion
from vasquez.core.models import FaultConfig, FaultType

# Escenarios de integración existentes, recolectados de nuevo en este módulo para correr bajo
# la vía de enlace (el fixture autouse de abajo aplica a ellos).
from test_vasquez import (  # noqa: F401
    test_evaluate_robustness_graceful,
    test_evaluate_robustness_crashes_on_null,
    test_cli_inject_json,
    test_ripley_plugin,
    test_cli_faults_write_enospc_no_crash,
    test_fread_and_fclose_fault_injection,
    test_cli_report_unified_faults_and_exit_code,
)
from test_new_qol_features import (  # noqa: F401
    test_calloc_and_realloc_interception,
    test_fail_write_after_bytes,
    test_probabilistic_stress_cli,
    test_cli_inject_flags,
    test_realloc_null_injection_qol11,
    test_posix_memalign_and_calloc_qol16,
    test_cascade_failure_mode_qol17,
    test_audit_free_null_qol20,
    test_garbage_memory_poisoning_qol25,
    test_cli_qol_options,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def forzar_enlace(monkeypatch):
    monkeypatch.setattr(fault_runner, "mecanismo_por_defecto", lambda: MECANISMO_ENLACE)


def test_objeto_enlace_en_cache():
    obj = get_cached_link_object()
    assert obj.exists() and obj.stat().st_size > 0
    assert get_cached_link_object() == obj


def test_enlace_rechaza_binarios(tmp_path):
    binario = tmp_path / "app"
    binario.write_bytes(b"\x7fELF")
    with pytest.raises(RuntimeError, match="requiere el fuente .c"):
        evaluate_robustness(binario)


def test_enlace_cuenta_solo_llamadas_del_alumno(tmp_path):
    # A diferencia de LD_PRELOAD (que también ve el malloc interno de glibc para el buffer de
    # stdout), en enlace sólo se interceptan las llamadas escritas en el código del alumno.
    src = tmp_path / "conteo.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        printf("inicio\\n");
        char *a = malloc(8);
        char *b = malloc(8);
        if (!a || !b) { free(a); free(b); return 7; }
        free(a); free(b);
        return 0;
    }
    """)
    escenarios = [FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=n, enable_trace=True) for n in (1, 2, 3)]
    rep = evaluate_robustness(src, escenarios)
    assert [r.exit_code for r in rep.results] == [7, 7, 0]
    assert all("malloc(8)" in r.trace_log[1] for r in rep.results)


@pytest.mark.skipif(sys.platform == "win32", reason="LD_PRELOAD no existe en Windows nativo")
def test_mecanismo_explicito_ignora_el_de_plataforma(tmp_path):
    # Con la plataforma forzada a enlace, pedir preload debe seguir inyectando por LD_PRELOAD.
    src = tmp_path / "vulnerable.c"
    src.write_text("""
    #include <stdlib.h>
    int main(void) { int *p = malloc(sizeof(int)); *p = 1; free(p); return 0; }
    """)
    rep = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1)], mecanismo=MECANISMO_PRELOAD)
    assert rep.results[0].signal_name == "SIGSEGV"


def test_traza_enlace_compatible_con_leak_checker(tmp_path):
    src = tmp_path / "fuga.c"
    src.write_text("""
    #include <stdlib.h>
    int main(void) {
        char *a = malloc(8);
        char *b = malloc(8);
        if (!b) return 1; // fuga de 'a'
        free(a); free(b);
        return 0;
    }
    """)
    rep = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=2, check_leaks=True)])
    assert rep.results[0].leaks_detected is True
    assert any("malloc(8) -> 0x" in l for l in rep.results[0].trace_log)


def test_redefinicion_windows_cubre_importaciones():
    args = argumentos_redefinicion("win32")
    assert "malloc=vasquez_hook_malloc" in args
    assert "__imp_malloc=__imp_vasquez_hook_malloc" in args
    assert "_strdup=vasquez_hook__strdup" in args
    assert not any("posix_memalign" in a for a in args)
    assert not any("__imp_" in a for a in argumentos_redefinicion("linux"))


def test_senal_desde_codigo_windows():
    assert senal_desde_codigo_windows(0xC0000005) == "SIGSEGV"
    assert senal_desde_codigo_windows(-1073741819) == "SIGSEGV"  # mismo código como int con signo
    assert senal_desde_codigo_windows(0xC0000374) == "SIGABRT"
    assert senal_desde_codigo_windows(3) == "SIGABRT"  # abort()/assert() del UCRT sin __fastfail
    assert senal_desde_codigo_windows(1) is None


def test_doctor_windows_usa_enlace(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(doctor_mod, "buscar_objcopy", lambda: "/usr/bin/objcopy")
    monkeypatch.setattr(sys, "platform", "win32")
    rep = ejecutar_diagnostico_doctor()
    estados = {c.name: c.status for c in rep.checks}
    assert estados["Inyección en enlace (objcopy)"] == "OK"
    assert estados["libvasquez_link"] == "OK"
    assert "libvasquez_inject" not in estados
    assert rep.system_summary["preload_env"] == "enlace"


def test_doctor_windows_sin_objcopy(monkeypatch):
    monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(doctor_mod, "buscar_objcopy", lambda: None)
    monkeypatch.setattr(sys, "platform", "win32")
    rep = ejecutar_diagnostico_doctor()
    assert rep.all_ok is False
    assert {c.name: c.status for c in rep.checks}["Inyección en enlace (objcopy)"] == "FALTA"
