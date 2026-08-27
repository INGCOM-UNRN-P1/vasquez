"""Generación y compilación de la librería de intercepción LD_PRELOAD para inyección de fallos."""

import os
import tempfile
import subprocess
from pathlib import Path

INJECTOR_C_SOURCE = r"""
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <errno.h>
#include <string.h>

static int (*real_malloc_fn)(size_t) = NULL;
static void *(*real_malloc)(size_t) = NULL;
static void *(*real_calloc)(size_t, size_t) = NULL;
static FILE *(*real_fopen)(const char *, const char *) = NULL;

static int malloc_call_count = 0;
static int malloc_fail_at = -1;

static int fopen_call_count = 0;
static int fopen_fail_at = -1;
static int fopen_errno = 13; // EACCES

__attribute__((constructor))
static void init_vasquez(void) {
    char *env_malloc = getenv("VASQUEZ_MALLOC_FAIL_AT");
    if (env_malloc) {
        malloc_fail_at = atoi(env_malloc);
    }
    char *env_fopen = getenv("VASQUEZ_FOPEN_FAIL_AT");
    if (env_fopen) {
        fopen_fail_at = atoi(env_fopen);
    }
    char *env_errno = getenv("VASQUEZ_ERRNO");
    if (env_errno) {
        fopen_errno = atoi(env_errno);
    }

    real_malloc = (void *(*)(size_t))dlsym(RTLD_NEXT, "malloc");
    real_calloc = (void *(*)(size_t, size_t))dlsym(RTLD_NEXT, "calloc");
    real_fopen = (FILE *(*)(const char *, const char *))dlsym(RTLD_NEXT, "fopen");
}

void *malloc(size_t size) {
    if (!real_malloc) {
        real_malloc = (void *(*)(size_t))dlsym(RTLD_NEXT, "malloc");
    }
    malloc_call_count++;
    if (malloc_fail_at > 0 && malloc_call_count == malloc_fail_at) {
        errno = ENOMEM;
        return NULL;
    }
    return real_malloc(size);
}

void *calloc(size_t nmemb, size_t size) {
    if (!real_calloc) {
        real_calloc = (void *(*)(size_t, size_t))dlsym(RTLD_NEXT, "calloc");
    }
    malloc_call_count++;
    if (malloc_fail_at > 0 && malloc_call_count == malloc_fail_at) {
        errno = ENOMEM;
        return NULL;
    }
    return real_calloc(nmemb, size);
}

FILE *fopen(const char *pathname, const char *mode) {
    if (!real_fopen) {
        real_fopen = (FILE *(*)(const char *, const char *))dlsym(RTLD_NEXT, "fopen");
    }
    fopen_call_count++;
    if (fopen_fail_at > 0 && fopen_call_count == fopen_fail_at) {
        errno = fopen_errno;
        return NULL;
    }
    return real_fopen(pathname, mode);
}
"""


def compile_preload_library(output_path: Path) -> Path:
    """Compila la librería compartida .so para inyección de fallos con LD_PRELOAD."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    c_file = output_path.with_suffix(".c")
    c_file.write_text(INJECTOR_C_SOURCE, encoding="utf-8")

    res = subprocess.run(
        ["gcc", "-shared", "-fPIC", "-O2", str(c_file), "-o", str(output_path), "-ldl"],
        capture_output=True,
        text=True,
        check=False
    )
    if res.returncode != 0:
        raise RuntimeError(f"Fallo al compilar libvasquez_preload: {res.stderr}")

    return output_path
