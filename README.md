# VASQUEZ — Motor de Inyección de Fallos de Entorno en C (Fault Injection Engine)

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

### Dependencias Externas y Binarios
- `gcc` (para compilar la biblioteca interceptora nativa).

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

