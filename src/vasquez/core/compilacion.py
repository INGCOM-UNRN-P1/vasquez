"""Compilación del programa a evaluar (N-VASQUEZ-02).

Admite proyectos de varios archivos: el fuente principal más fuentes
adicionales, y flags extra para gcc (`-I include`, `-std=c11`, `-DDEBUG`).
Las dos vías de inyección (precarga y enlace) usan los mismos flags base para
que el comportamiento observado sea comparable.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Sequence

from vasquez.core.errores import ErrorDeCompilacion, ErrorVasquez

FLAGS_BASE = ["-O0", "-g", "-fno-builtin-free"]


def compilar(fuentes: Sequence[Path], destino: Path, cflags: Sequence[str] = (), solo_objeto: bool = False) -> Path:
    """Compila `fuentes` en `destino` (ejecutable, u objeto con `solo_objeto`)."""
    comando = ["gcc", *FLAGS_BASE, *cflags, *(["-c"] if solo_objeto else []), *map(str, fuentes), "-o", str(destino)]
    try:
        comp = subprocess.run(comando, capture_output=True, check=False)
    except FileNotFoundError:
        raise ErrorVasquez("No se encontró gcc en el PATH; ejecutá `vasquez doctor` para ver cómo instalarlo.") from None
    if comp.returncode != 0:
        raise ErrorDeCompilacion(fuentes, comp.stderr.decode("utf-8", errors="replace"))
    return destino
