"""Proyectos de varios archivos y errores de compilación sin traceback (N-VASQUEZ-02, N-ECO-05).

Los escenarios de integración se re-ejecutan en test_enlace.py bajo la vía de enlace.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vasquez.cli import app
from vasquez.core.errores import ErrorDeCompilacion, ErrorVasquez, pista_de_compilacion
from vasquez.core.fault_runner import evaluate_robustness
from vasquez.core.models import FaultConfig, FaultType
from vasquez.plugins.ripley_plugin import VasquezPlugin

runner = CliRunner()

LISTA_H = "#ifndef LISTA_H\n#define LISTA_H\nint *crear(int n);\n#endif\n"
LISTA_C = '#include <stdlib.h>\n#include "lista.h"\nint *crear(int n) { return malloc(n * sizeof(int)); }\n'
MAIN_C = """#include <stdio.h>
#include <stdlib.h>
#include "lista.h"
int main(void) {
    int *v = crear(4);
    if (v == NULL) {
        fprintf(stderr, "sin memoria\\n");
        return 1;
    }
    v[0] = 1;
    free(v);
    return 0;
}
"""


def _actividad(tmp_path: Path) -> Path:
    """Estructura de las actividades del curso: src/ con los .c e include/ con los headers."""
    (tmp_path / "include").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "include" / "lista.h").write_text(LISTA_H)
    (tmp_path / "src" / "lista.c").write_text(LISTA_C)
    (tmp_path / "src" / "main.c").write_text(MAIN_C)
    return tmp_path


def test_cli_evalua_un_proyecto_de_varios_archivos(tmp_path):
    raiz = _actividad(tmp_path)
    res = runner.invoke(app, ["check", str(raiz / "src/main.c"), str(raiz / "src/lista.c"),
                              "-I", str(raiz / "include"), "--faults", "malloc:1", "--json"])
    assert res.exit_code == 0, res.output
    assert '"passed": true' in res.output


def test_cli_cflags_se_pasan_a_gcc(tmp_path):
    raiz = _actividad(tmp_path)
    res = runner.invoke(app, ["check", str(raiz / "src/main.c"), str(raiz / "src/lista.c"),
                              "--cflags", f"-I{raiz / 'include'} -std=c11", "--faults", "malloc:1", "--json"])
    assert res.exit_code == 0, res.output


def test_cli_header_en_otra_carpeta_explica_como_seguir(tmp_path):
    raiz = _actividad(tmp_path)
    res = runner.invoke(app, ["check", str(raiz / "src/main.c"), str(raiz / "src/lista.c")])
    assert res.exit_code == 2
    assert "no compila" in res.output
    assert "-I" in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit)


def test_cli_modulo_sin_main_explica_como_seguir(tmp_path):
    raiz = _actividad(tmp_path)
    res = runner.invoke(app, ["report", str(raiz / "src/lista.c"), "-I", str(raiz / "include")])
    assert res.exit_code == 2
    assert "Falta el archivo con main" in res.output


def test_cli_cflags_mal_formado_es_error_de_uso(tmp_path):
    raiz = _actividad(tmp_path)
    res = runner.invoke(app, ["check", str(raiz / "src/main.c"), "--cflags", '"-DX'])
    assert res.exit_code == 2
    assert "--cflags" in res.output


def test_cli_rechaza_un_directorio(tmp_path):
    res = runner.invoke(app, ["check", str(_actividad(tmp_path) / "src")])
    assert res.exit_code == 2
    assert res.exception is None or isinstance(res.exception, SystemExit)


def test_error_de_compilacion_conserva_la_salida_de_gcc(tmp_path):
    raiz = _actividad(tmp_path)
    with pytest.raises(ErrorDeCompilacion) as error:
        evaluate_robustness(raiz / "src/main.c", [FaultConfig(fault_type=FaultType.MALLOC_FAIL)])
    assert "lista.h" in error.value.salida
    assert isinstance(error.value, RuntimeError)


def test_fuentes_extra_con_un_binario_es_error(tmp_path):
    binario = tmp_path / "programa"
    binario.write_bytes(b"\x7fELF")
    with pytest.raises(ErrorVasquez, match="no es un fuente .c"):
        evaluate_robustness(binario, fuentes_extra=[tmp_path / "otro.c"])


def test_plugin_ripley_con_proyecto_de_varios_archivos(tmp_path):
    raiz = _actividad(tmp_path)
    res = VasquezPlugin().run({"source_dir": str(raiz / "src")})
    assert "error" not in res, res
    assert res["passed"] is True


@pytest.mark.parametrize("salida, esperado", [
    ("main.c:3:10: fatal error: lista.h: No such file or directory", "-I"),
    ("undefined reference to `main'", "Falta el archivo con main"),
    ("main.c:(.text+0x9): undefined reference to `crear'", "pasalos todos"),
    ("multiple definition of `crear'", "definida en dos archivos"),
    ("error: expected ';' before '}' token", None),
])
def test_pista_de_compilacion(salida, esperado):
    pista = pista_de_compilacion(salida)
    if esperado is None:
        assert pista is None
    else:
        assert esperado in pista
