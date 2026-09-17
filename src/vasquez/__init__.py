"""Vasquez - Motor de Inyección de Fallos en Tiempo de Ejecución."""

from vasquez.core.constants import (
    ENV_MALLOC_FAIL_AT,
    ENV_CALLOC_FAIL_AT,
    ENV_REALLOC_FAIL_AT,
    ENV_POSIX_MEMALIGN_FAIL_AT,
    ENV_MALLOC_PROB,
    ENV_CASCADE_FAILS,
    ENV_GARBAGE_MEMORY,
    ENV_POISON_BYTE,
    ENV_FOPEN_FAIL_AT,
    ENV_ERRNO,
    ENV_FAIL_WRITE_AFTER_BYTES,
    ENV_FREAD_FAIL_AT,
    ENV_FCLOSE_FAIL_AT,
    ENV_TRACE,
    ENV_TRACE_FILE,
)

__version__ = "0.1.0"

