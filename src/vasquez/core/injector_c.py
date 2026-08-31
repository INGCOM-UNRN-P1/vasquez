"""Generación y compilación de la librería de intercepción LD_PRELOAD para inyección de fallos."""

from __future__ import annotations
import os
import sys
import subprocess
from pathlib import Path

INJECTOR_C_SOURCE = r"""
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
#include <stdint.h>
#include <stdarg.h>
#include <fcntl.h>

// Punteros a funciones reales de libc
static void *(*real_malloc)(size_t) = NULL;
static void *(*real_calloc)(size_t, size_t) = NULL;
static void *(*real_realloc)(void *, size_t) = NULL;
static char *(*real_strdup)(const char *) = NULL;
static int   (*real_posix_memalign)(void **, size_t, size_t) = NULL;
static FILE *(*real_fopen)(const char *, const char *) = NULL;
static size_t(*real_fwrite)(const void *, size_t, size_t, FILE *) = NULL;
static size_t(*real_fread)(void *, size_t, size_t, FILE *) = NULL;
static int   (*real_fclose)(FILE *) = NULL;

// Variables de configuración de fallos
static int malloc_call_count = 0;
static int malloc_fail_at = -1;
static double malloc_fail_prob = 0.0;

static int fopen_call_count = 0;
static int fopen_fail_at = -1;
static int fopen_errno = 13; // EACCES

static size_t bytes_written_total = 0;
static long   fail_write_after_bytes = -1;

static int trace_fd = -1;
static __thread int in_hook = 0;

static void log_trace(const char *fmt, ...) {
    if (trace_fd < 0) return;
    char buf[512];
    va_list args;
    va_start(args, fmt);
    int len = vsnprintf(buf, sizeof(buf) - 2, fmt, args);
    va_end(args);
    if (len > 0) {
        buf[len] = '\n';
        buf[len + 1] = '\0';
        ssize_t w = write(trace_fd, buf, len + 1);
        (void)w;
    }
}

static void resolve_symbols(void) {
    if (!real_malloc) {
        real_malloc = (void *(*)(size_t))dlsym(RTLD_NEXT, "malloc");
        real_calloc = (void *(*)(size_t, size_t))dlsym(RTLD_NEXT, "calloc");
        real_realloc = (void *(*)(void *, size_t))dlsym(RTLD_NEXT, "realloc");
        real_strdup = (char *(*)(const char *))dlsym(RTLD_NEXT, "strdup");
        real_posix_memalign = (int (*)(void **, size_t, size_t))dlsym(RTLD_NEXT, "posix_memalign");
        real_fopen = (FILE *(*)(const char *, const char *))dlsym(RTLD_NEXT, "fopen");
        real_fwrite = (size_t(*)(const void *, size_t, size_t, FILE *))dlsym(RTLD_NEXT, "fwrite");
        real_fread = (size_t(*)(void *, size_t, size_t, FILE *))dlsym(RTLD_NEXT, "fread");
        real_fclose = (int (*)(FILE *))dlsym(RTLD_NEXT, "fclose");
    }
}

__attribute__((constructor))
static void init_vasquez(void) {
    resolve_symbols();

    char *env_malloc = getenv("VASQUEZ_MALLOC_FAIL_AT");
    if (env_malloc) malloc_fail_at = atoi(env_malloc);

    char *env_prob = getenv("VASQUEZ_MALLOC_PROB");
    if (env_prob) malloc_fail_prob = atof(env_prob);

    char *env_fopen = getenv("VASQUEZ_FOPEN_FAIL_AT");
    if (env_fopen) fopen_fail_at = atoi(env_fopen);

    char *env_errno = getenv("VASQUEZ_ERRNO");
    if (env_errno) fopen_errno = atoi(env_errno);

    char *env_write_after = getenv("VASQUEZ_FAIL_WRITE_AFTER_BYTES");
    if (env_write_after) fail_write_after_bytes = atol(env_write_after);

    char *env_trace = getenv("VASQUEZ_TRACE_FILE");
    if (env_trace) {
        trace_fd = open(env_trace, O_WRONLY | O_CREAT | O_APPEND, 0644);
        if (trace_fd >= 0) {
            log_trace("[VASQUEZ] Trace inicializado. PID: %d", getpid());
        }
    }
}

static int should_fail_malloc(void) {
    if (malloc_fail_at > 0 && malloc_call_count == malloc_fail_at) {
        return 1;
    }
    if (malloc_fail_prob > 0.0) {
        double r = (double)rand() / (double)RAND_MAX;
        if (r < malloc_fail_prob) return 1;
    }
    return 0;
}

void *malloc(size_t size) {
    resolve_symbols();
    if (in_hook || !real_malloc) {
        return real_malloc ? real_malloc(size) : NULL;
    }
    in_hook = 1;
    malloc_call_count++;

    if (should_fail_malloc()) {
        errno = ENOMEM;
        log_trace("[VASQUEZ] malloc(%zu) -> NULL [FALLO FORZADO #%d]", size, malloc_call_count);
        in_hook = 0;
        return NULL;
    }
    void *ptr = real_malloc(size);
    log_trace("[VASQUEZ] malloc(%zu) -> %p [#%d]", size, ptr, malloc_call_count);
    in_hook = 0;
    return ptr;
}

void *calloc(size_t nmemb, size_t size) {
    resolve_symbols();
    if (in_hook || !real_calloc) {
        return real_calloc ? real_calloc(nmemb, size) : NULL;
    }
    in_hook = 1;
    malloc_call_count++;

    if (should_fail_malloc()) {
        errno = ENOMEM;
        log_trace("[VASQUEZ] calloc(%zu, %zu) -> NULL [FALLO FORZADO #%d]", nmemb, size, malloc_call_count);
        in_hook = 0;
        return NULL;
    }
    void *ptr = real_calloc(nmemb, size);
    log_trace("[VASQUEZ] calloc(%zu, %zu) -> %p [#%d]", nmemb, size, ptr, malloc_call_count);
    in_hook = 0;
    return ptr;
}

void *realloc(void *ptr, size_t size) {
    resolve_symbols();
    if (in_hook || !real_realloc) {
        return real_realloc ? real_realloc(ptr, size) : NULL;
    }
    in_hook = 1;
    malloc_call_count++;

    if (should_fail_malloc()) {
        errno = ENOMEM;
        log_trace("[VASQUEZ] realloc(%p, %zu) -> NULL [FALLO FORZADO #%d]", ptr, size, malloc_call_count);
        in_hook = 0;
        return NULL;
    }
    void *nptr = real_realloc(ptr, size);
    log_trace("[VASQUEZ] realloc(%p, %zu) -> %p [#%d]", ptr, size, nptr, malloc_call_count);
    in_hook = 0;
    return nptr;
}

char *strdup(const char *s) {
    resolve_symbols();
    if (in_hook || !real_strdup) {
        return real_strdup ? real_strdup(s) : NULL;
    }
    in_hook = 1;
    malloc_call_count++;

    if (should_fail_malloc()) {
        errno = ENOMEM;
        log_trace("[VASQUEZ] strdup(...) -> NULL [FALLO FORZADO #%d]", malloc_call_count);
        in_hook = 0;
        return NULL;
    }
    char *res = real_strdup(s);
    log_trace("[VASQUEZ] strdup(...) -> %p [#%d]", (void*)res, malloc_call_count);
    in_hook = 0;
    return res;
}

int posix_memalign(void **memptr, size_t alignment, size_t size) {
    resolve_symbols();
    if (in_hook || !real_posix_memalign) {
        return real_posix_memalign ? real_posix_memalign(memptr, alignment, size) : ENOMEM;
    }
    in_hook = 1;
    malloc_call_count++;

    if (should_fail_malloc()) {
        log_trace("[VASQUEZ] posix_memalign(...) -> ENOMEM [FALLO FORZADO #%d]", malloc_call_count);
        in_hook = 0;
        return ENOMEM;
    }
    int r = real_posix_memalign(memptr, alignment, size);
    in_hook = 0;
    return r;
}

FILE *fopen(const char *pathname, const char *mode) {
    resolve_symbols();
    if (in_hook || !real_fopen) {
        return real_fopen ? real_fopen(pathname, mode) : NULL;
    }
    in_hook = 1;
    fopen_call_count++;

    if (fopen_fail_at > 0 && fopen_call_count == fopen_fail_at) {
        errno = fopen_errno;
        log_trace("[VASQUEZ] fopen(\"%s\", \"%s\") -> NULL [FALLO FORZADO #%d, errno=%d]", pathname, mode, fopen_call_count, fopen_errno);
        in_hook = 0;
        return NULL;
    }
    FILE *f = real_fopen(pathname, mode);
    log_trace("[VASQUEZ] fopen(\"%s\", \"%s\") -> %p [#%d]", pathname, mode, (void*)f, fopen_call_count);
    in_hook = 0;
    return f;
}

size_t fwrite(const void *ptr, size_t size, size_t nmemb, FILE *stream) {
    resolve_symbols();
    if (in_hook || !real_fwrite) {
        return real_fwrite ? real_fwrite(ptr, size, nmemb, stream) : 0;
    }
    in_hook = 1;
    size_t total_bytes = size * nmemb;

    if (fail_write_after_bytes >= 0 && (bytes_written_total + total_bytes > (size_t)fail_write_after_bytes)) {
        errno = 28; // ENOSPC (No space left on device)
        log_trace("[VASQUEZ] fwrite(%zu bytes) -> 0 [FALLO DISCO LLENO ENOSPC]", total_bytes);
        in_hook = 0;
        return 0;
    }

    size_t written = real_fwrite(ptr, size, nmemb, stream);
    bytes_written_total += (written * size);
    log_trace("[VASQUEZ] fwrite(%zu bytes) -> %zu escrito [Total acumulado: %zu bytes]", total_bytes, written, bytes_written_total);
    in_hook = 0;
    return written;
}

size_t fread(void *ptr, size_t size, size_t nmemb, FILE *stream) {
    resolve_symbols();
    if (in_hook || !real_fread) {
        return real_fread ? real_fread(ptr, size, nmemb, stream) : 0;
    }
    in_hook = 1;
    size_t r = real_fread(ptr, size, nmemb, stream);
    log_trace("[VASQUEZ] fread(%zu bytes) -> %zu", size * nmemb, r);
    in_hook = 0;
    return r;
}

int fclose(FILE *stream) {
    resolve_symbols();
    if (in_hook || !real_fclose) {
        return real_fclose ? real_fclose(stream) : 0;
    }
    in_hook = 1;
    int res = real_fclose(stream);
    log_trace("[VASQUEZ] fclose(%p) -> %d", (void*)stream, res);
    in_hook = 0;
    return res;
}
"""


def compile_preload_library(output_path: Path) -> Path:
    """Compila la librería compartida .so / .dylib para inyección de fallos."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c_file = output_path.with_suffix(".c")
    c_file.write_text(INJECTOR_C_SOURCE, encoding="utf-8")

    compile_flags = ["gcc", "-shared", "-fPIC", "-O2", str(c_file), "-o", str(output_path)]
    if sys.platform == "darwin":
        compile_flags.extend(["-dynamiclib"])
    else:
        compile_flags.extend(["-ldl"])

    res = subprocess.run(
        compile_flags,
        capture_output=True,
        text=True,
        check=False
    )
    if res.returncode != 0:
        raise RuntimeError(f"Fallo al compilar libvasquez_preload: {res.stderr}")

    return output_path
