"""Errores de dominio de VASQUEZ (N-ECO-05, N-VASQUEZ-02).

Un programa que no compila o un entorno sin gcc son situaciones esperables:
la CLI las muestra como un mensaje con una pista y sale con 2, sin traceback.
Heredan de RuntimeError para no romper a quien ya las capturaba así.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional


class ErrorVasquez(RuntimeError):
    """Error de uso o de entorno que impide evaluar el programa."""


class ErrorDeCompilacion(ErrorVasquez):
    """El programa a evaluar no compila (o no enlaza) con los fuentes y flags indicados."""

    def __init__(self, fuentes: Iterable[Path], salida: str):
        self.fuentes = [Path(f) for f in fuentes]
        self.salida = salida.strip()
        nombres = ", ".join(f.name for f in self.fuentes)
        super().__init__(f"Error compilando {nombres}: {self.salida}")


def pista_de_compilacion(salida: str) -> Optional[str]:
    """Sugerencia para los errores de compilación más comunes en proyectos de varios archivos."""
    if "No such file or directory" in salida and ".h" in salida:
        return "Si los headers están en otra carpeta, indicála con -I (por ejemplo: -I include)."
    # En Windows (MinGW) el enlazador reclama WinMain en lugar de main.
    if re.search(r"undefined reference to [`'](?:_?main|w?WinMain(?:@\d+)?)'", salida):
        return "Falta el archivo con main: pasalo junto con los demás (por ejemplo: vasquez check src/main.c src/lista.c)."
    if "undefined reference" in salida:
        return "Si el programa tiene varios archivos .c, pasalos todos (por ejemplo: vasquez check src/main.c src/lista.c)."
    if "multiple definition" in salida:
        return "Hay una función definida en dos archivos: revisá que los .c no se incluyan entre sí."
    return None
