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
