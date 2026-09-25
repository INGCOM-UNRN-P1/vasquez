"""Tests unitarios y de integración para VASQUEZ."""

from pathlib import Path
from typer.testing import CliRunner
from vasquez.cli import app
from vasquez.core.models import FaultConfig, FaultType
from vasquez.core.fault_runner import evaluate_robustness
from vasquez.plugins.ripley_plugin import VasquezPlugin

runner = CliRunner()


def test_evaluate_robustness_graceful(tmp_path):
    # Programa defensivo que chequea malloc != NULL
    src = tmp_path / "defensivo.c"
    src.write_text("""
    #include <stdio.h>
    #include <stdlib.h>
    int main(void) {
        int *p = malloc(sizeof(int));
        if (p == NULL) {
            fprintf(stderr, "Error de memoria controlado\\n");
            return 1;
        }
        *p = 42;
        free(p);
        return 0;
    }
    """)
    report = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1)])
    assert report.passed is True
    assert report.crashed_scenarios_count == 0


def test_evaluate_robustness_crashes_on_null(tmp_path):
    # Programa vulnerable que no chequea NULL
    src = tmp_path / "vulnerable.c"
    src.write_text("""
    #include <stdlib.h>
    int main(void) {
        int *p = malloc(sizeof(int));
        *p = 42; // Crashea si p == NULL
        free(p);
        return 0;
    }
    """)
    report = evaluate_robustness(src, [FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=1)])
    assert report.passed is False
    assert report.crashed_scenarios_count == 1
    assert "SIGSEGV" in report.results[0].signal_name or report.results[0].exit_code != 0


def test_cli_inject_json(tmp_path):
    src = tmp_path / "app.c"
    src.write_text("int main(void) { return 0; }")
    res = runner.invoke(app, ["inject", str(src), "--json"])
    assert res.exit_code == 0
    assert '"passed": true' in res.output


def test_cli_version():
    res = runner.invoke(app, ["version"])
    assert res.exit_code == 0
    assert "VASQUEZ" in res.output


def test_ripley_plugin(tmp_path):
    src = tmp_path / "main.c"
    src.write_text("int main(void) { return 0; }")
    plugin = VasquezPlugin()
    res = plugin.run({"source_dir": str(tmp_path)})
    assert res["passed"] is True


def test_cli_faults_write_enospc_no_crash(tmp_path):
    # D0301 / D0801: write:ENOSPC no debe crashear con ValueError
    src = tmp_path / "writer.c"
    src.write_text("""
    #include <stdio.h>
    int main(void) {
        FILE *f = fopen("out.tmp", "wb");
        if (!f) return 1;
        char data[] = "hola mundo";
        size_t w = fwrite(data, 1, sizeof(data), f);
        fclose(f);
        return (w < sizeof(data)) ? 2 : 0;
    }
    """)
    res = runner.invoke(app, ["inject", str(src), "--faults", "write:ENOSPC", "--json"])
    assert res.exit_code == 0
    assert '"passed": true' in res.output


def test_cli_faults_unknown_token_raises_exit_2(tmp_path):
    # D0302: Tokens desconocidos deben fallar de inmediato con código de salida 2
    src = tmp_path / "dummy.c"
    src.write_text("int main(void) { return 0; }")
    res = runner.invoke(app, ["inject", str(src), "--faults", "read:5"])
    assert res.exit_code == 2
    assert "Fallo no reconocido" in res.output or "Error" in res.output


def test_fread_and_fclose_fault_injection(tmp_path):
    # D0303: Inyección de fallo en fread y fclose
    src_fread = tmp_path / "test_fread.c"
    src_fread.write_text("""
    #include <stdio.h>
    int main(void) {
        FILE *f = fopen("test.in", "wb");
        fputs("12345", f);
        fclose(f);

        f = fopen("test.in", "rb");
        if (!f) return 1;
        char buf[10];
        size_t r = fread(buf, 1, 5, f);
        fclose(f);
        if (r == 0) return 5; // Manejó error de lectura (3 es el código de abort() en Windows)
        return 0;
    }
    """)
    rep_fread = evaluate_robustness(src_fread, [FaultConfig(fault_type=FaultType.FREAD_FAIL, fail_fread_at=1)])
    assert rep_fread.passed is True
    assert rep_fread.results[0].exit_code == 5

    src_fclose = tmp_path / "test_fclose.c"
    src_fclose.write_text("""
    #include <stdio.h>
    int main(void) {
        FILE *f = fopen("test.in", "wb");
        if (!f) return 1;
        int err = fclose(f);
        if (err != 0) return 4; // Manejó error de cierre
        return 0;
    }
    """)
    rep_fclose = evaluate_robustness(src_fclose, [FaultConfig(fault_type=FaultType.FCLOSE_FAIL, fail_fclose_at=1)])
    assert rep_fclose.passed is True
    assert rep_fclose.results[0].exit_code == 4


def test_cli_report_unified_faults_and_exit_code(tmp_path):
    # D0401 y D0402: report acepta todos los fallos y sale con exit 1 si el test falla
    src_vulnerable = tmp_path / "vuln.c"
    src_vulnerable.write_text("""
    #include <stdlib.h>
    int main(void) {
        int *p = malloc(sizeof(int));
        *p = 10;
        free(p);
        return 0;
    }
    """)
    # Con malloc:1 debe crashear / no manejar y terminar con exit code 1
    res_fail = runner.invoke(app, ["report", str(src_vulnerable), "--faults", "calloc:1,malloc:1"])
    assert res_fail.exit_code == 1
    assert "dredd-section: vasquez" in res_fail.output

    src_safe = tmp_path / "safe.c"
    src_safe.write_text("""
    #include <stdlib.h>
    int main(void) {
        int *p = malloc(sizeof(int));
        if (!p) return 1;
        *p = 10;
        free(p);
        return 0;
    }
    """)
    res_ok = runner.invoke(app, ["report", str(src_safe), "--faults", "malloc:1"])
    assert res_ok.exit_code == 0
    assert "dredd-section: vasquez" in res_ok.output

