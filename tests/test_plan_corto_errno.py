"""Plan de fallos en YAML (QoL #1000), lecturas parciales (#991) y errno elegido (#994), corriendo
los programas de verdad bajo el inyector."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vasquez.cli import app, parse_fault_spec
from vasquez.core.fault_runner import evaluate_robustness
from vasquez.core.models import FaultConfig, FaultType
from vasquez.core.plan import PlanInvalido, cargar_plan

runner = CliRunner()
necesita_gcc = pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")

# Lee 4 enteros de un archivo con UN fread: con lecturas parciales recibe menos y lo informa.
LECTOR = r"""
#include <errno.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    int v[4] = {1, 2, 3, 4}, w[4];
    FILE *f = fopen("datos.bin", "wb");
    if (f == NULL) { printf("fopen:%d\n", errno); return 3; }
    fwrite(v, sizeof(int), 4, f);
    fclose(f);
    f = fopen("datos.bin", "rb");
    if (f == NULL) { printf("fopen:%d\n", errno); return 3; }
    size_t n = fread(w, sizeof(int), 4, f);
    fclose(f);
    printf("leidos:%zu\n", n);
    return n == 4 ? 0 : 4;
}
"""


def _fuente(tmp_path: Path) -> Path:
    f = tmp_path / "lector.c"
    f.write_text(LECTOR, encoding="utf-8")
    return f


@necesita_gcc
def test_lectura_parcial(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    escenario = FaultConfig(fault_type=FaultType.FREAD_SHORT, fail_at_invocation=-1, short_read_items=1)
    (resultado,) = evaluate_robustness(_fuente(tmp_path), scenarios=[escenario]).results
    assert "leidos:1" in resultado.stdout and resultado.exit_code == 4


@necesita_gcc
def test_errno_elegido_en_fopen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (escenario,) = parse_fault_spec("fopen:1:EMFILE")
    (resultado,) = evaluate_robustness(_fuente(tmp_path), scenarios=[escenario]).results
    assert "fopen:24" in resultado.stdout


def test_spec_con_corto_y_errno():
    corto, fread = parse_fault_spec("fread_corto:2,fread:1:EINTR")
    assert corto.fault_type == FaultType.FREAD_SHORT and corto.short_read_items == 2
    assert fread.errno_value == 4


def test_plan_yaml(tmp_path):
    plan = tmp_path / "vasquez.scenario.yaml"
    plan.write_text(
        "escenarios:\n"
        "  - tipo: malloc\n    llamada: 2\n"
        "  - tipo: fopen\n    errno: EACCES\n"
        "  - tipo: fwrite\n    despues_de_bytes: 1024\n"
        "  - tipo: fread_corto\n    elementos: 1\n"
        "opciones:\n  fugas: true\n", encoding="utf-8")
    malloc, fopen, fwrite, corto = cargar_plan(plan)
    assert (malloc.fault_type, malloc.fail_at_invocation, malloc.check_leaks) == (FaultType.MALLOC_FAIL, 2, True)
    assert fopen.errno_value == 13 and fwrite.fail_after_bytes == 1024 and corto.short_read_items == 1


@pytest.mark.parametrize("contenido, mensaje", [
    ("escenarios: []\n", "falta la lista"),
    ("escenarios:\n  - tipo: printf\n", "tipo 'printf' desconocido"),
    ("escenarios:\n  - tipo: fopen\n    errno: EPERRO\n", "errno 'EPERRO'"),
    ("escenarios:\n  - tipo: malloc\n    llamadas: 2\n", "claves desconocidas"),
])
def test_plan_invalido(tmp_path, contenido, mensaje):
    plan = tmp_path / "p.yaml"
    plan.write_text(contenido, encoding="utf-8")
    with pytest.raises(PlanInvalido, match=mensaje):
        cargar_plan(plan)


@necesita_gcc
def test_cli_usa_el_plan_junto_al_fuente(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fuente = _fuente(tmp_path)
    (tmp_path / "vasquez.scenario.yaml").write_text("escenarios:\n  - tipo: fread_corto\n", encoding="utf-8")
    res = runner.invoke(app, ["inject", str(fuente), "--json"])
    datos = json.loads(res.stdout)
    assert [r["fault_config"]["fault_type"] for r in datos["results"]] == ["fread_corto"]
