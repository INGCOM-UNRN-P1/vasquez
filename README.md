# VASQUEZ — Motor de Inyección de Fallos de Entorno en C (Fault Injection Engine)

**VASQUEZ** intercepta llamadas estándar a `malloc`, `calloc` y `fopen` mediante `LD_PRELOAD` para inyectar fallos deterministas en tiempo de ejecución (retornos `NULL` simulando falta de memoria o accesos denegados a disco), verificando si el estudiante implementó manejo defensivo de errores o si el programa sufre un `SIGSEGV`.

---

## 🎯 Alcance

### Qué cubre
- Inyección de fallos en tiempo de ejecución (Runtime Fault Injection) sin deadlocks para programas C.
- Intercepción transparente mediante biblioteca compartida `libvasquez_inject.so` precargada con `LD_PRELOAD`.
- Simulación de fallos controlados en memoria dinámica (`malloc`, `calloc`, `realloc`, `strdup` retornando `NULL` según contadores o patrones).
- Simulación de fallos de sistema de archivos (`fopen`, `fread`, `fwrite` retornando error o `ENOSPC`).
- Detección de fugas de recursos y omisión de manejo de errores en caminos de fallo.

### Qué no cubre (Límites y Delegación)
- Mocks estáticos en tiempo de compilación o enlazado (delegado a `holden`).
- Aislamiento en sandbox de llamadas al sistema mediante bwrap (delegado a `nostromo`).
- Análisis forense de core dumps (delegado a `hal`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Linux / POSIX compatible con `LD_PRELOAD`. Python >= 3.10.

### Dependencias Externas y Binarios
- `gcc` (para compilar la biblioteca interceptora nativa).

### Integración en el Ecosistema
- CLI `vasquez`. Plugin registrado en `ripley.plugins` (`fault_injection`).

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
