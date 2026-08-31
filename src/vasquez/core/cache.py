"""Gestión de caché transparente para la librería compartida de inyección de VASQUEZ."""

from __future__ import annotations
import os
import hashlib
from pathlib import Path
from vasquez.core.injector_c import INJECTOR_C_SOURCE, compile_preload_library


def get_cached_injector_library() -> Path:
    """Obtiene la ruta de la librería compartida compilada, compilándola sólo si cambió el hash fuente."""
    cache_dir = Path.home() / ".cache" / "vasquez"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Calcular SHA256 del código C del inyector
    c_hash = hashlib.sha256(INJECTOR_C_SOURCE.encode("utf-8")).hexdigest()[:16]
    so_name = f"libvasquez_inject_{c_hash}.so"
    so_path = cache_dir / so_name

    if not so_path.exists() or so_path.stat().st_size == 0:
        compile_preload_library(so_path)

    return so_path
