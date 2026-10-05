"""Plan de fallos en YAML (QoL #1000): los escenarios de una actividad, fijos y reutilizables.

Con `--faults` el docente tiene que repetir la especificación en cada corrida; un
`vasquez.scenario.yaml` junto a la entrega la deja escrita una vez, y dredd la usa igual para
todo el curso (`vasquez inject main.c --plan vasquez.scenario.yaml`, o sin `--plan` si el archivo
está en el directorio del primer fuente y no se pidió ningún otro escenario):

    escenarios:
      - tipo: malloc
        llamada: 2              # falla la segunda reserva
      - tipo: fopen
        errno: EACCES           # permiso denegado
      - tipo: fwrite
        despues_de_bytes: 1024  # disco lleno después de 1 KiB
      - tipo: fread_corto
        elementos: 1            # cada fread lee de a un elemento
    opciones:
      fugas: true               # además, fugas en los caminos de error
      cascada: false
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from vasquez.core.constants import ERRNO_MAP
from vasquez.core.models import FaultConfig, FaultType

NOMBRE_POR_DEFECTO = "vasquez.scenario.yaml"

_TIPOS = {
    "malloc": FaultType.MALLOC_FAIL, "calloc": FaultType.CALLOC_FAIL, "realloc": FaultType.REALLOC_FAIL,
    "strdup": FaultType.STRDUP_FAIL, "posix_memalign": FaultType.POSIX_MEMALIGN_FAIL,
    "fopen": FaultType.FOPEN_FAIL, "fwrite": FaultType.FWRITE_FAIL, "fread": FaultType.FREAD_FAIL,
    "fclose": FaultType.FCLOSE_FAIL, "fread_corto": FaultType.FREAD_SHORT,
    "probabilistico": FaultType.PROBABILISTIC, "cascada": FaultType.CASCADE, "basura": FaultType.GARBAGE_MEMORY,
}
_ERRNO_POR_DEFECTO = {FaultType.FOPEN_FAIL: "EACCES", FaultType.FWRITE_FAIL: "ENOSPC", FaultType.FREAD_FAIL: "EIO",
                      FaultType.FCLOSE_FAIL: "EIO"}
_CLAVES = {"tipo", "llamada", "errno", "despues_de_bytes", "elementos", "probabilidad"}


class PlanInvalido(ValueError):
    """El YAML no describe un plan de fallos válido (el mensaje dice qué y dónde)."""


def _escenario(n: int, datos: Any, base: Dict[str, Any]) -> FaultConfig:
    if not isinstance(datos, dict) or "tipo" not in datos:
        raise PlanInvalido(f"escenario {n}: cada escenario es un mapa con al menos 'tipo'.")
    desconocidas = set(datos) - _CLAVES
    if desconocidas:
        raise PlanInvalido(f"escenario {n}: claves desconocidas {sorted(desconocidas)}; válidas: {sorted(_CLAVES)}.")
    tipo = _TIPOS.get(str(datos["tipo"]).lower())
    if tipo is None:
        raise PlanInvalido(f"escenario {n}: tipo '{datos['tipo']}' desconocido; válidos: {', '.join(_TIPOS)}.")
    nombre_errno = str(datos.get("errno") or _ERRNO_POR_DEFECTO.get(tipo, "ENOMEM")).upper()
    if nombre_errno not in ERRNO_MAP:
        raise PlanInvalido(f"escenario {n}: errno '{nombre_errno}' desconocido; válidos: {', '.join(sorted(ERRNO_MAP))}.")
    try:
        llamada = int(datos.get("llamada", 1))
        bytes_ = int(datos.get("despues_de_bytes", 0 if tipo == FaultType.FWRITE_FAIL else -1))
        elementos = int(datos.get("elementos", 1))
        probabilidad = float(datos.get("probabilidad", 0.2 if tipo == FaultType.PROBABILISTIC else 0.0))
    except (TypeError, ValueError) as exc:
        raise PlanInvalido(f"escenario {n}: un valor numérico no es un número ({exc}).") from None
    extra: Dict[str, Any] = {}
    if tipo == FaultType.CALLOC_FAIL:
        extra["fail_calloc_at"] = llamada
    elif tipo == FaultType.REALLOC_FAIL:
        extra["fail_realloc_at"] = llamada
    elif tipo == FaultType.POSIX_MEMALIGN_FAIL:
        extra["fail_posix_memalign_at"] = llamada
    elif tipo == FaultType.CASCADE:
        extra["cascade_failures"] = True
    elif tipo == FaultType.GARBAGE_MEMORY:
        extra["garbage_memory"] = True
        llamada = -1
    elif tipo == FaultType.FREAD_SHORT:
        llamada = -1
    return FaultConfig(fault_type=tipo, fail_at_invocation=llamada, fail_after_bytes=bytes_,
                       fail_probability=probabilidad, errno_value=ERRNO_MAP[nombre_errno],
                       short_read_items=elementos, **{**base, **extra})


def cargar_plan(ruta: Path) -> List[FaultConfig]:
    try:
        datos = yaml.safe_load(Path(ruta).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PlanInvalido(f"{Path(ruta).name} no es YAML válido: {exc}") from None
    if not isinstance(datos, dict) or not isinstance(datos.get("escenarios"), list) or not datos["escenarios"]:
        raise PlanInvalido(f"{Path(ruta).name}: falta la lista 'escenarios'.")
    opciones = datos.get("opciones") or {}
    if not isinstance(opciones, dict):
        raise PlanInvalido(f"{Path(ruta).name}: 'opciones' tiene que ser un mapa.")
    base = {
        "check_leaks": bool(opciones.get("fugas", False)),
        "cascade_failures": bool(opciones.get("cascada", False)),
        "enable_trace": bool(opciones.get("traza", False)) or bool(opciones.get("fugas", False)),
    }
    return [_escenario(n, e, base) for n, e in enumerate(datos["escenarios"], 1)]


def plan_junto_a(fuente: Path) -> Path | None:
    candidato = Path(fuente).resolve().parent / NOMBRE_POR_DEFECTO
    return candidato if candidato.is_file() else None
