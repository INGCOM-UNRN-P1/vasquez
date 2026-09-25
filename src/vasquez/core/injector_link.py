"""Inyección de fallos por interceptación en tiempo de enlace (plataformas sin LD_PRELOAD).

En Windows nativo (GCC MinGW-w64 UCRT64) no existe precarga de librerías: los ejecutables PE
resuelven sus importaciones al cargarse y no hay <dlfcn.h>. Como alternativa, el programa del
alumno se compila a objeto y se renombran con ``objcopy --redefine-sym`` sus referencias a
``malloc``, ``fopen``, etc. hacia los ganchos ``vasquez_hook_*`` definidos en un objeto
inyector que se enlaza junto a él. El renombrado afecta solo al objeto del alumno: el código
de arranque del runtime y el propio inyector siguen llamando a las funciones reales, por lo
que el conteo de invocaciones coincide con el de la vía LD_PRELOAD.

Limitación: requiere el fuente ``.c``; un binario ya compilado no puede instrumentarse.
"""

from __future__ import annotations
import sys
import shutil
import subprocess
from pathlib import Path
from typing import List

HOOK_PREFIX = "vasquez_hook_"

MECANISMO_PRELOAD = "preload"
MECANISMO_ENLACE = "enlace"

# Símbolos interceptados en todas las plataformas.
_SIMBOLOS_COMUNES = ["malloc", "calloc", "realloc", "strdup", "free", "fopen", "fwrite", "fread", "fclose"]


def simbolos_interceptados(plataforma: str | None = None) -> List[str]:
    """Símbolos de libc que se redirigen a los ganchos del inyector en la plataforma dada."""
    plataforma = plataforma or sys.platform
    if plataforma == "win32":
        # UCRT no tiene posix_memalign; strdup puede llegar también como _strdup.
        return _SIMBOLOS_COMUNES + ["_strdup"]
    return _SIMBOLOS_COMUNES + ["posix_memalign"]


INJECTOR_LINK_C_SOURCE = r"""
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <stdint.h>
#include <stdarg.h>
#ifdef _WIN32
#include <process.h>
#define VASQUEZ_GETPID() _getpid()
#else
#include <unistd.h>
#define VASQUEZ_GETPID() getpid()
#endif

/*
 * Ganchos vasquez_hook_*: el objeto del alumno llama a estos símbolos tras el renombrado con
 * objcopy. Dentro de este archivo malloc, fopen, etc. son las funciones reales de la libc,
 * por lo que no hay recursión posible ni se necesita dlsym.
 */

// Variables de configuración de fallos de memoria general
static int malloc_call_count = 0;
static int malloc_fail_at = -1;
static double malloc_fail_prob = 0.0;

// Específicos para realloc (Mejora 11)
static int realloc_call_count = 0;
static int realloc_fail_at = -1;
static double realloc_fail_prob = 0.0;

// Específicos para calloc y posix_memalign (Mejora 16)
static int calloc_call_count = 0;
static int calloc_fail_at = -1;
#ifndef _WIN32
static int posix_memalign_call_count = 0;
#endif
static int posix_memalign_fail_at = -1;

// Modo Cascada (Mejora 17)
static int cascade_enabled = 0;
static int cascade_active = 0;

// Auditoría free(NULL) (Mejora 20)
static int free_call_count = 0;
static int free_null_count = 0;

// Envenenamiento de memoria basura (Mejora 25)
static int garbage_memory_enabled = 0;
static unsigned char poison_byte = 0xA5;

// Variables de fallos de I/O de archivos
static int fopen_call_count = 0;
static int fopen_fail_at = -1;
static int fopen_errno = 13; // EACCES

static size_t bytes_written_total = 0;
static long   fail_write_after_bytes = -1;

static int fread_call_count = 0;
static int fread_fail_at = -1;

static int fclose_call_count = 0;
static int fclose_fail_at = -1;

static FILE *trace_fp = NULL;
static int initialized = 0;

// Formato de puntero estable entre plataformas (el %p de MinGW omite el prefijo 0x).
#define PTR(p) ((unsigned long long)(uintptr_t)(p))

static void log_trace(const char *fmt, ...) {
    if (!trace_fp) return;
    va_list args;
    va_start(args, fmt);
    vfprintf(trace_fp, fmt, args);
    va_end(args);
    fputc('\n', trace_fp);
    // Volcado inmediato: la traza debe sobrevivir a una caída del programa.
    fflush(trace_fp);
}

static void trigger_cascade(void) {
    if (cascade_enabled) {
        cascade_active = 1;
    }
}

static void init_vasquez(void) {
    if (initialized) return;
    initialized = 1;

    char *env_malloc = getenv("VASQUEZ_MALLOC_FAIL_AT");
    if (env_malloc) malloc_fail_at = atoi(env_malloc);

    char *env_prob = getenv("VASQUEZ_MALLOC_PROB");
    if (env_prob) malloc_fail_prob = atof(env_prob);

    char *env_realloc = getenv("VASQUEZ_REALLOC_FAIL_AT");
    if (env_realloc) realloc_fail_at = atoi(env_realloc);

    char *env_realloc_prob = getenv("VASQUEZ_REALLOC_PROB");
    if (env_realloc_prob) realloc_fail_prob = atof(env_realloc_prob);

    char *env_calloc = getenv("VASQUEZ_CALLOC_FAIL_AT");
    if (env_calloc) calloc_fail_at = atoi(env_calloc);

    char *env_posix = getenv("VASQUEZ_POSIX_MEMALIGN_FAIL_AT");
    if (env_posix) posix_memalign_fail_at = atoi(env_posix);

    char *env_cascade = getenv("VASQUEZ_CASCADE_FAILS");
    if (env_cascade && atoi(env_cascade) > 0) cascade_enabled = 1;

    char *env_garbage = getenv("VASQUEZ_GARBAGE_MEMORY");
    if (env_garbage && atoi(env_garbage) > 0) garbage_memory_enabled = 1;

    char *env_poison = getenv("VASQUEZ_POISON_BYTE");
    if (env_poison) poison_byte = (unsigned char)strtol(env_poison, NULL, 0);

    char *env_fopen = getenv("VASQUEZ_FOPEN_FAIL_AT");
    if (env_fopen) fopen_fail_at = atoi(env_fopen);

    char *env_errno = getenv("VASQUEZ_ERRNO");
    if (env_errno) fopen_errno = atoi(env_errno);

    char *env_write_after = getenv("VASQUEZ_FAIL_WRITE_AFTER_BYTES");
    if (env_write_after) fail_write_after_bytes = atol(env_write_after);

    char *env_fread = getenv("VASQUEZ_FREAD_FAIL_AT");
    if (env_fread) fread_fail_at = atoi(env_fread);

    char *env_fclose = getenv("VASQUEZ_FCLOSE_FAIL_AT");
    if (env_fclose) fclose_fail_at = atoi(env_fclose);

    char *env_trace = getenv("VASQUEZ_TRACE_FILE");
    if (env_trace) {
        trace_fp = fopen(env_trace, "a");
        if (trace_fp) {
            log_trace("[VASQUEZ] Trace inicializado. PID: %d", (int)VASQUEZ_GETPID());
        }
    } else {
        char *env_trace_stderr = getenv("VASQUEZ_TRACE");
        if (env_trace_stderr && atoi(env_trace_stderr) > 0) {
            trace_fp = stderr;
            log_trace("[VASQUEZ] Trace a stderr inicializado. PID: %d", (int)VASQUEZ_GETPID());
        }
    }
}

static int should_fail_malloc(void) {
    if (cascade_active) return 1;
    if (malloc_fail_at > 0 && malloc_call_count == malloc_fail_at) {
        return 1;
    }
    if (malloc_fail_prob > 0.0) {
        double r = (double)rand() / (double)RAND_MAX;
        if (r < malloc_fail_prob) return 1;
    }
    return 0;
}

static int should_fail_realloc(void) {
    if (cascade_active) return 1;
    if (realloc_fail_at > 0 && realloc_call_count == realloc_fail_at) return 1;
    if (realloc_fail_prob > 0.0) {
        double r = (double)rand() / (double)RAND_MAX;
        if (r < realloc_fail_prob) return 1;
    }
    if (realloc_fail_at < 0 && should_fail_malloc()) return 1;
    return 0;
}

static int should_fail_calloc(void) {
    if (cascade_active) return 1;
    if (calloc_fail_at > 0 && calloc_call_count == calloc_fail_at) return 1;
    if (calloc_fail_at < 0 && should_fail_malloc()) return 1;
    return 0;
}

void *vasquez_hook_malloc(size_t size) {
    init_vasquez();
    malloc_call_count++;

    if (should_fail_malloc()) {
        errno = ENOMEM;
        trigger_cascade();
        log_trace("[VASQUEZ] malloc(%llu) -> NULL [FALLO FORZADO #%d%s]", (unsigned long long)size, malloc_call_count, cascade_active ? " - CASCADA" : "");
        return NULL;
    }
    void *ptr = malloc(size);
    if (ptr && garbage_memory_enabled && size > 0) {
        memset(ptr, poison_byte, size);
        log_trace("[VASQUEZ] malloc(%llu) -> 0x%llx [MEMORIA BASURA ENVENENADA 0x%02X] [#%d]", (unsigned long long)size, PTR(ptr), poison_byte, malloc_call_count);
    } else {
        log_trace("[VASQUEZ] malloc(%llu) -> 0x%llx [#%d]", (unsigned long long)size, PTR(ptr), malloc_call_count);
    }
    return ptr;
}

void *vasquez_hook_calloc(size_t nmemb, size_t size) {
    init_vasquez();
    malloc_call_count++;
    calloc_call_count++;

    if (should_fail_calloc()) {
        errno = ENOMEM;
        trigger_cascade();
        log_trace("[VASQUEZ] calloc(%llu, %llu) -> NULL [FALLO FORZADO CALLOC #%d%s]", (unsigned long long)nmemb, (unsigned long long)size, calloc_call_count, cascade_active ? " - CASCADA" : "");
        return NULL;
    }
    void *ptr = calloc(nmemb, size);
    log_trace("[VASQUEZ] calloc(%llu, %llu) -> 0x%llx [#%d]", (unsigned long long)nmemb, (unsigned long long)size, PTR(ptr), calloc_call_count);
    return ptr;
}

void *vasquez_hook_realloc(void *ptr, size_t size) {
    init_vasquez();
    malloc_call_count++;
    realloc_call_count++;

    if (should_fail_realloc()) {
        errno = ENOMEM;
        trigger_cascade();
        log_trace("[VASQUEZ] realloc(0x%llx, %llu) -> NULL [FALLO FORZADO REALLOC #%d%s] (puntero previo 0x%llx preservado por SO)", PTR(ptr), (unsigned long long)size, realloc_call_count, cascade_active ? " - CASCADA" : "", PTR(ptr));
        return NULL;
    }
    unsigned long long previo = PTR(ptr);
    void *nptr = realloc(ptr, size);
    if (nptr && garbage_memory_enabled && size > 0) {
        log_trace("[VASQUEZ] realloc(0x%llx, %llu) -> 0x%llx [REALLOC EXITOSO] [#%d]", previo, (unsigned long long)size, PTR(nptr), realloc_call_count);
    } else {
        log_trace("[VASQUEZ] realloc(0x%llx, %llu) -> 0x%llx [#%d]", previo, (unsigned long long)size, PTR(nptr), realloc_call_count);
    }
    return nptr;
}

static char *hook_strdup_comun(const char *s, char *(*real)(const char *)) {
    init_vasquez();
    malloc_call_count++;

    if (should_fail_malloc()) {
        errno = ENOMEM;
        trigger_cascade();
        log_trace("[VASQUEZ] strdup(...) -> NULL [FALLO FORZADO #%d%s]", malloc_call_count, cascade_active ? " - CASCADA" : "");
        return NULL;
    }
    char *res = real(s);
    log_trace("[VASQUEZ] strdup(...) -> 0x%llx [#%d]", PTR(res), malloc_call_count);
    return res;
}

char *vasquez_hook_strdup(const char *s) {
    return hook_strdup_comun(s, strdup);
}

#ifdef _WIN32
char *vasquez_hook__strdup(const char *s) {
    return hook_strdup_comun(s, _strdup);
}
#else
static int should_fail_posix_memalign(void) {
    if (cascade_active) return 1;
    if (posix_memalign_fail_at > 0 && posix_memalign_call_count == posix_memalign_fail_at) return 1;
    if (posix_memalign_fail_at < 0 && should_fail_malloc()) return 1;
    return 0;
}

int vasquez_hook_posix_memalign(void **memptr, size_t alignment, size_t size) {
    init_vasquez();
    malloc_call_count++;
    posix_memalign_call_count++;

    if (should_fail_posix_memalign()) {
        trigger_cascade();
        log_trace("[VASQUEZ] posix_memalign(...) -> ENOMEM [FALLO FORZADO POSIX_MEMALIGN #%d%s]", posix_memalign_call_count, cascade_active ? " - CASCADA" : "");
        return ENOMEM;
    }
    int r = posix_memalign(memptr, alignment, size);
    if (r == 0 && *memptr && garbage_memory_enabled && size > 0) {
        memset(*memptr, poison_byte, size);
        log_trace("[VASQUEZ] posix_memalign(...) -> 0x%llx [MEMORIA BASURA ENVENENADA 0x%02X]", PTR(*memptr), poison_byte);
    }
    return r;
}
#endif

void vasquez_hook_free(void *ptr) {
    init_vasquez();
    free_call_count++;
    if (ptr == NULL) {
        free_null_count++;
        log_trace("[VASQUEZ] free(NULL) [AUDITORIA LIMPIEZA #%d] (free(NULL) inocuo invocado)", free_null_count);
    } else {
        log_trace("[VASQUEZ] free(0x%llx) [#%d]", PTR(ptr), free_call_count);
    }
    free(ptr);
}

FILE *vasquez_hook_fopen(const char *pathname, const char *mode) {
    init_vasquez();
    fopen_call_count++;

    if (cascade_active || (fopen_fail_at > 0 && fopen_call_count == fopen_fail_at)) {
        errno = fopen_errno;
        trigger_cascade();
        log_trace("[VASQUEZ] fopen(\"%s\", \"%s\") -> NULL [FALLO FORZADO #%d, errno=%d%s]", pathname, mode, fopen_call_count, fopen_errno, cascade_active ? " - CASCADA" : "");
        return NULL;
    }
    FILE *f = fopen(pathname, mode);
    log_trace("[VASQUEZ] fopen(\"%s\", \"%s\") -> 0x%llx [#%d]", pathname, mode, PTR(f), fopen_call_count);
    return f;
}

size_t vasquez_hook_fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream) {
    init_vasquez();
    size_t total_bytes = size * nmemb;

    if (cascade_active || (fail_write_after_bytes >= 0 && (bytes_written_total + total_bytes > (size_t)fail_write_after_bytes))) {
        errno = 28; // ENOSPC (No space left on device)
        trigger_cascade();
        log_trace("[VASQUEZ] fwrite(%llu bytes) -> 0 [FALLO DISCO LLENO ENOSPC%s]", (unsigned long long)total_bytes, cascade_active ? " - CASCADA" : "");
        return 0;
    }

    size_t written = fwrite(ptr, size, nmemb, stream);
    bytes_written_total += (written * size);
    log_trace("[VASQUEZ] fwrite(%llu bytes) -> %llu escrito [Total acumulado: %llu bytes]", (unsigned long long)total_bytes, (unsigned long long)written, (unsigned long long)bytes_written_total);
    return written;
}

size_t vasquez_hook_fread(void *ptr, size_t size, size_t nmemb, FILE *stream) {
    init_vasquez();
    fread_call_count++;
    if (cascade_active || (fread_fail_at > 0 && fread_call_count >= fread_fail_at)) {
        log_trace("[VASQUEZ] fread llamada #%d -> 0 [FALLO FORZADO I/O%s]", fread_call_count, cascade_active ? " - CASCADA" : "");
        trigger_cascade();
        return 0;
    }
    size_t r = fread(ptr, size, nmemb, stream);
    log_trace("[VASQUEZ] fread(%llu bytes) -> %llu", (unsigned long long)(size * nmemb), (unsigned long long)r);
    return r;
}

int vasquez_hook_fclose(FILE *stream) {
    init_vasquez();
    fclose_call_count++;
    if (cascade_active || (fclose_fail_at > 0 && fclose_call_count >= fclose_fail_at)) {
        errno = 5; // EIO
        log_trace("[VASQUEZ] fclose llamada #%d -> EOF [FALLO FORZADO I/O%s]", fclose_call_count, cascade_active ? " - CASCADA" : "");
        trigger_cascade();
        fclose(stream);
        return EOF;
    }
    unsigned long long stream_id = PTR(stream);
    int res = fclose(stream);
    log_trace("[VASQUEZ] fclose(0x%llx) -> %d", stream_id, res);
    return res;
}

#ifdef _WIN32
/*
 * Si los encabezados del runtime declaran una función con __declspec(dllimport), el objeto del
 * alumno la invoca indirectamente vía __imp_<símbolo>. objcopy renombra también esas referencias
 * a __imp_vasquez_hook_<símbolo>, que aquí apuntan a los ganchos.
 */
void *__imp_vasquez_hook_malloc = (void *)vasquez_hook_malloc;
void *__imp_vasquez_hook_calloc = (void *)vasquez_hook_calloc;
void *__imp_vasquez_hook_realloc = (void *)vasquez_hook_realloc;
void *__imp_vasquez_hook_strdup = (void *)vasquez_hook_strdup;
void *__imp_vasquez_hook__strdup = (void *)vasquez_hook__strdup;
void *__imp_vasquez_hook_free = (void *)vasquez_hook_free;
void *__imp_vasquez_hook_fopen = (void *)vasquez_hook_fopen;
void *__imp_vasquez_hook_fwrite = (void *)vasquez_hook_fwrite;
void *__imp_vasquez_hook_fread = (void *)vasquez_hook_fread;
void *__imp_vasquez_hook_fclose = (void *)vasquez_hook_fclose;
#endif
"""


def buscar_objcopy() -> str | None:
    """Ubica objcopy (binutils), necesario para redirigir los símbolos del objeto del alumno."""
    return shutil.which("objcopy")


def compile_link_object(output_path: Path) -> Path:
    """Compila el objeto inyector (.o) que provee los ganchos vasquez_hook_*."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c_file = output_path.with_suffix(".c")
    c_file.write_text(INJECTOR_LINK_C_SOURCE, encoding="utf-8")

    res = subprocess.run(
        ["gcc", "-c", "-O2", str(c_file), "-o", str(output_path)],
        capture_output=True,
        text=True,
        check=False
    )
    if res.returncode != 0:
        raise RuntimeError(f"Fallo al compilar el objeto inyector de enlace: {res.stderr}")

    return output_path


def argumentos_redefinicion(plataforma: str | None = None) -> List[str]:
    """Argumentos --redefine-sym de objcopy para redirigir llamadas directas e importadas."""
    args: List[str] = []
    for sym in simbolos_interceptados(plataforma):
        args += ["--redefine-sym", f"{sym}={HOOK_PREFIX}{sym}"]
        if (plataforma or sys.platform) == "win32":
            args += ["--redefine-sym", f"__imp_{sym}=__imp_{HOOK_PREFIX}{sym}"]
    return args


def build_instrumented_binary(source: Path, work_dir: Path, injector_obj: Path) -> Path:
    """Compila el fuente del alumno enlazándolo con los ganchos del inyector.

    Usa los mismos flags de compilación que la vía LD_PRELOAD para que el comportamiento
    observado sea comparable.
    """
    objcopy = buscar_objcopy()
    if not objcopy:
        raise RuntimeError("No se encontró 'objcopy' (binutils) en el PATH; es necesario para la interceptación en enlace.")

    obj = work_dir / "target_app.o"
    comp = subprocess.run(
        ["gcc", "-O0", "-g", "-fno-builtin-free", "-c", str(source), "-o", str(obj)],
        capture_output=True,
        check=False
    )
    if comp.returncode != 0:
        raise RuntimeError(f"Error compilando {source}: {comp.stderr.decode('utf-8', errors='replace')}")

    redef = subprocess.run(
        [objcopy, *argumentos_redefinicion(), str(obj)],
        capture_output=True,
        check=False
    )
    if redef.returncode != 0:
        raise RuntimeError(f"Error redirigiendo símbolos con objcopy: {redef.stderr.decode('utf-8', errors='replace')}")

    bin_path = work_dir / ("target_app.exe" if sys.platform == "win32" else "target_app")
    link = subprocess.run(
        ["gcc", str(obj), str(injector_obj), "-o", str(bin_path)],
        capture_output=True,
        check=False
    )
    if link.returncode != 0:
        raise RuntimeError(f"Error enlazando {source} con el inyector: {link.stderr.decode('utf-8', errors='replace')}")

    return bin_path
