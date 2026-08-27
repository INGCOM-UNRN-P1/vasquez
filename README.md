# VASQUEZ — Motor de Inyección de Fallos de Entorno en C (Fault Injection Engine)

**VASQUEZ** intercepta llamadas estándar a `malloc`, `calloc` y `fopen` mediante `LD_PRELOAD` para inyectar fallos deterministas en tiempo de ejecución (retornos `NULL` simulando falta de memoria o accesos denegados a disco), verificando si el estudiante implementó manejo defensivo de errores o si el programa sufre un `SIGSEGV`.

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
