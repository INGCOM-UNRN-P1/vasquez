"""Diagnóstico desacoplado del entorno y dependencias para VASQUEZ."""

from __future__ import annotations
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from vasquez.core.cache import get_cached_injector_library, get_cached_link_object
from vasquez.core.injector_c import preload_soportado
from vasquez.core.injector_link import buscar_objcopy


class DependencyCheck(BaseModel):
    name: str
    category: str
    required: bool
    status: str
    version: str = ""
    detail: str = ""


class DoctorReport(BaseModel):
    all_ok: bool
    checks: List[DependencyCheck] = Field(default_factory=list)
    system_summary: Dict[str, Any] = Field(default_factory=dict)


def _verificar_libreria_inyeccion(checks: List[DependencyCheck]) -> bool:
    """Compila (o reutiliza de caché) libvasquez_inject y registra el resultado en checks."""
    try:
        so_path = get_cached_injector_library()
        if so_path.exists() and so_path.stat().st_size > 0:
            checks.append(DependencyCheck(
                name="libvasquez_inject",
                category="Librería de Inyección",
                required=True,
                status="OK",
                detail=f"Caché compilada lista en: {so_path}"
            ))
        else:
            checks.append(DependencyCheck(
                name="libvasquez_inject",
                category="Librería de Inyección",
                required=True,
                status="ERROR",
                detail="No se pudo verificar el archivo de librería compilado."
            ))
            return False
    except Exception as e:
        checks.append(DependencyCheck(
            name="libvasquez_inject",
            category="Librería de Inyección",
            required=True,
            status="ERROR",
            detail=f"Falla al compilar en caché: {e}"
        ))
        return False
    return True


def _verificar_objeto_enlace(checks: List[DependencyCheck]) -> bool:
    """Compila (o reutiliza de caché) el objeto inyector de enlace y registra el resultado en checks."""
    try:
        obj_path = get_cached_link_object()
    except Exception as e:
        checks.append(DependencyCheck(
            name="libvasquez_link",
            category="Librería de Inyección",
            required=True,
            status="ERROR",
            detail=f"Falla al compilar en caché: {e}"
        ))
        return False
    checks.append(DependencyCheck(
        name="libvasquez_link",
        category="Librería de Inyección",
        required=True,
        status="OK",
        detail=f"Objeto inyector listo en: {obj_path}"
    ))
    return True


def ejecutar_diagnostico_doctor() -> DoctorReport:
    """Ejecuta una auditoría completa de los binarios y capacidades de inyección requeridas por VASQUEZ."""
    checks: List[DependencyCheck] = []
    all_ok = True

    # 1. GCC
    gcc_path = shutil.which("gcc")
    if gcc_path:
        try:
            res = subprocess.run(["gcc", "--version"], capture_output=True, text=True, check=False)
            ver = res.stdout.splitlines()[0] if res.stdout else "Detectado"
            checks.append(DependencyCheck(
                name="gcc",
                category="Compilador C",
                required=True,
                status="OK",
                version=ver,
                detail=f"Ubicación: {gcc_path}"
            ))
        except Exception as e:
            checks.append(DependencyCheck(
                name="gcc",
                category="Compilador C",
                required=True,
                status="ERROR",
                detail=f"Falla al ejecutar: {e}"
            ))
            all_ok = False
    else:
        checks.append(DependencyCheck(
            name="gcc",
            category="Compilador C",
            required=True,
            status="FALTA",
            detail="GCC no se encuentra en el PATH del sistema."
        ))
        all_ok = False

    # 2. Mecanismo de inyección del Sistema Operativo
    if preload_soportado():
        preload_env = "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"
        checks.append(DependencyCheck(
            name=f"Inyección vía {preload_env}",
            category="Mecanismo de Hooking",
            required=True,
            status="OK",
            detail=f"Plataforma detectada: {sys.platform} ({preload_env})"
        ))
        all_ok = _verificar_libreria_inyeccion(checks) and all_ok
    else:
        # Windows nativo (GCC MinGW-w64 UCRT64): sin LD_PRELOAD ni <dlfcn.h>, los ganchos se
        # enlazan en el ejecutable redirigiendo símbolos con objcopy.
        preload_env = "enlace"
        objcopy_path = buscar_objcopy()
        checks.append(DependencyCheck(
            name="Inyección en enlace (objcopy)",
            category="Mecanismo de Hooking",
            required=True,
            status="OK" if objcopy_path else "FALTA",
            detail=(
                f"Plataforma detectada: {sys.platform} (sin LD_PRELOAD). Se redirigen símbolos con "
                f"{objcopy_path}; sólo se admiten fuentes .c, no binarios precompilados."
                if objcopy_path else
                "objcopy (binutils) no se encuentra en el PATH; es necesario para interceptar en enlace."
            )
        ))
        if not objcopy_path:
            all_ok = False
        all_ok = _verificar_objeto_enlace(checks) and all_ok

    return DoctorReport(
        all_ok=all_ok,
        checks=checks,
        system_summary={
            "herramienta": "vasquez",
            "plataforma": sys.platform,
            "preload_env": preload_env
        }
    )
