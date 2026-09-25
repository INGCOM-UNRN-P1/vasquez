# VASQUEZ — Motor de Inyección de Fallos de Entorno en C (Fault Injection Engine)

> 📖 **Manual de Usuario:** Para una guía exhaustiva de comandos, banderas, arquitectura y ejemplos, consultá el [Manual de Uso](MANUAL.md).

**VASQUEZ** intercepta llamadas estándar a la biblioteca de C (`malloc`, `calloc`, `realloc`, `strdup`, `fopen`, `fwrite`, `fread`, `fclose`) mediante `LD_PRELOAD` para inyectar fallos deterministas en tiempo de ejecución (retornos `NULL` o códigos de error simulando falta de memoria o accesos denegados a disco), verificando si el estudiante implementó manejo defensivo de errores o si el programa sufre un `SIGSEGV`.

---

## 🎯 Alcance

### Qué cubre
- Inyección de fallos en tiempo de ejecución (Runtime Fault Injection) sin deadlocks para programas C.
- Intercepción transparente mediante biblioteca compartida `libvasquez_inject.so` precargada con `LD_PRELOAD`.
- Simulación de fallos controlados en memoria dinámica (`malloc`, `calloc`, `realloc`, `strdup`, `posix_memalign` retornando `NULL` según contadores o patrones).
- Simulación de fallos de sistema de archivos (`fopen`, `fread`, `fwrite`, `fclose` retornando error o `ENOSPC`).
- Detección de fugas de recursos y omisión de manejo de errores en caminos de fallo.

### Qué no cubre (Límites y Delegación)
- Mocks estáticos en tiempo de compilación o enlazado (delegado a `holden`).
- Aislamiento en sandbox de llamadas al sistema mediante bwrap (delegado a `nostromo`).
- Análisis forense de core dumps (delegado a `hal`).
- Orquestación masiva de entregas (delegado a `dredd`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Linux / POSIX compatible con `LD_PRELOAD`. Python >= 3.11.
- Windows nativo (GCC MinGW-w64 UCRT64 de MSYS2): soportado mediante interceptación en enlace; ver [Windows nativo](#windows-nativo-interceptación-en-enlace).

### Dependencias Externas y Binarios
- `gcc` (para compilar la biblioteca interceptora nativa).
- `objcopy` (binutils; sólo en Windows nativo, se instala junto con `gcc` en UCRT64).

### Integración en el Ecosistema
- CLI `vasquez`.
- Plugin registrado en `ripley.plugins` (`fault_injection`).
- Integración con `hal` para inyección runtime (`hal --inject-vasquez`).
- Generación de secciones de informe Markdown para `dredd` (`vasquez report`).

---

## 🚀 Uso Rápido

```bash
# Inyectar fallos por defecto (malloc y fopen) sobre código fuente o binario
vasquez inject solucion_alumno.c

# Especificar fallos exactos (fallar en el 2do malloc y 1er fopen)
vasquez inject app --faults "malloc:2,fopen:1"

# Salida estructurada JSON
vasquez inject solucion_alumno.c --json
```

## Windows nativo (interceptación en enlace)

Windows no tiene `LD_PRELOAD` ni `<dlfcn.h>`, y los ejecutables PE no admiten precarga de librerías. En esa plataforma VASQUEZ elige automáticamente otra vía:

1. Compila el `.c` del alumno a objeto con los mismos flags que en Linux (`-O0 -g -fno-builtin-free`).
2. Con `objcopy --redefine-sym` redirige en ese objeto las referencias a `malloc`, `calloc`, `realloc`, `strdup`/`_strdup`, `free`, `fopen`, `fwrite`, `fread` y `fclose` hacia los ganchos `vasquez_hook_*`.
3. Enlaza el resultado con el objeto inyector (`~/.cache/vasquez/libvasquez_link_<hash>.o`), que lee las mismas variables `VASQUEZ_*` que la librería de Linux.

Diferencias respecto de la vía `LD_PRELOAD`:

- **Requiere el fuente `.c`**: un binario ya compilado no puede instrumentarse y se rechaza con un error.
- **Sólo cuenta las llamadas del código del alumno.** En Linux, `LD_PRELOAD` ve también las reservas internas de glibc (por ejemplo, el buffer de `stdout` que reserva el primer `printf`), así que `malloc:1` puede caer en esa reserva. En Windows, `malloc:1` es siempre el primer `malloc` escrito por el alumno.
- `posix_memalign` no existe en UCRT, así que no se intercepta.
- Las caídas se detectan por el código de salida: `0xC0000005` (violación de acceso) se informa como `SIGSEGV`; `0xC0000374` (heap corrupto, p. ej. double free), `0xC0000409` (`__fastfail`) y `3` (`abort()`/`assert()` del UCRT) como `SIGABRT`, entre otros. Como consecuencia, un programa que termina con `return 3` o `exit(3)` se clasifica como abort, no como salida controlada: conviene que los ejercicios usen otros códigos de error.

`vasquez doctor` informa qué vía está activa y verifica `objcopy` y la compilación del objeto inyector.

## Intercepción Avanzada y Sintaxis de Fallos

La opción `--faults` (disponible en `vasquez inject` y `vasquez report`) admite combinaciones separadas por comas de:
- `malloc:<N>`: Falla la N-ésima invocación de `malloc`.
- `calloc:<N>`: Falla la N-ésima invocación de `calloc`.
- `realloc:<N>`: Falla la N-ésima invocación de `realloc`.
- `strdup:<N>`: Falla la N-ésima invocación de `strdup`.
- `posix_memalign:<N>`: Falla la N-ésima invocación de `posix_memalign`.
- `fopen:<N>`: Falla la N-ésima invocación de `fopen` (fija `errno = EACCES` por defecto).
- `fread:<N>`: Falla la N-ésima lectura `fread` retornando 0 y fijando `errno = EIO`.
- `fwrite:<bytes>` / `write:<bytes>` / `write:ENOSPC`: Falla la escritura luego de `<bytes>` o simula disco lleno (`ENOSPC`).
- `fclose:<N>`: Falla la N-ésima invocación de `fclose` retornando `EOF` y fijando `errno = EIO`.

```bash
# Inyectar fallo en realloc en la 1ra ocurrencia
vasquez inject app --faults "realloc:1"

# Simular disco lleno (ENOSPC) en escrituras
vasquez inject app --faults "write:ENOSPC"

# Auditoría estricta de fugas de memoria en caminos de error
vasquez inject app --faults "malloc:1" --check-leaks

# Auditoría del entorno y compilador de interceptor
vasquez doctor
```

