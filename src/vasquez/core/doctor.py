"""Diagnóstico desacoplado del entorno y dependencias para VASQUEZ."""

from __future__ import annotations
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from vasquez.core.cache import get_cached_injector_library


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

    # 2. Mecanismo de Preload del Sistema Operativo
    preload_env = "DYLD_INSERT_LIBRARIES" if sys.platform == "darwin" else "LD_PRELOAD"
    checks.append(DependencyCheck(
        name=f"Inyección vía {preload_env}",
        category="Mecanismo de Hooking",
        required=True,
        status="OK",
        detail=f"Plataforma detectada: {sys.platform} ({preload_env})"
    ))

    # 3. Compilación y Caché de libvasquez_inject.so
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
            all_ok = False
    except Exception as e:
        checks.append(DependencyCheck(
            name="libvasquez_inject",
            category="Librería de Inyección",
            required=True,
            status="ERROR",
            detail=f"Falla al compilar en caché: {e}"
        ))
        all_ok = False

    return DoctorReport(
        all_ok=all_ok,
        checks=checks,
        system_summary={
            "herramienta": "vasquez",
            "plataforma": sys.platform,
            "preload_env": preload_env
        }
    )
