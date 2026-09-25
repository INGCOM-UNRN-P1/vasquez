# Manual de Uso y Referencia Técnica: vasquez

> **VASQUEZ** — Motor de inyección de fallos de entorno y hardware (Fault Injection Engine) en C vía LD_PRELOAD
> **Versión:** `0.1.0` · **CLI principal:** `vasquez` · **Plugin Ripley:** `fault_injection`

---

## 1. Arquitectura y Propósito Pedagógico

`vasquez` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Inyección de fallos en tiempo de ejecución (Runtime Fault Injection) sin deadlocks para programas C.
- Intercepción transparente mediante biblioteca compartida `libvasquez_inject.so` precargada con `LD_PRELOAD`.
- Simulación de fallos controlados en memoria dinámica (`malloc`, `calloc`, `realloc`, `strdup`, `posix_memalign` retornando `NULL` según contadores o patrones).
- Simulación de fallos de sistema de archivos (`fopen`, `fread`, `fwrite`, `fclose` retornando error o `ENOSPC`).
- Detección de fugas de recursos y omisión de manejo de errores en caminos de fallo.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- Mocks estáticos en tiempo de compilación o enlazado (delegado a `holden`).
- Aislamiento en sandbox de llamadas al sistema mediante bwrap (delegado a `nostromo`).
- Análisis forense de core dumps (delegado a `hal`).
- Orquestación masiva de entregas (delegado a `dredd`).

### Principios de Diseño
- **Enfoque Pedagógico:** Diagnósticos y mensajes en español rioplatense orientados a facilitar la comprensión de errores conceptuales.
- **Salida Estructurada Dual:** Soporte nativo para visualización enriquecida en terminal (Rich) y salida parseable para orquestadores (`--json`).
- **Integración Contractual:** Capacidad de emitir secciones de reporte para `dredd` (`dredd-section`) y actuar como satélite orquestado por `ripley`.
- **Idempotencia y Robustez:** Validación de precondiciones y comandos de autodiagnóstico (`doctor`) para verificación del entorno.

---

## 2. Instalación y Requisitos

### Requisitos del Sistema
- **Python:** `>= 3.10` (recomendado Python 3.11 o 3.12).
- **Gestor de paquetes:** [`uv`](https://github.com/astral-sh/uv) (entorno estándar de cátedra).
- **Toolchain C (si aplica):** GCC / Clang, Make, GDB y bibliotecas estándar de desarrollo.

### Instalación en el Entorno de Usuario
Para instalar la herramienta de forma global y aislada en el sistema mediante `uv tool`:
```bash
uv tool install --editable /home/mrtin/dev/tools/vasquez
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
vasquez doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`vasquez check`](#check) | Inyecta fallos controlados (malloc/calloc/realloc NULL, cascada, memoria basura) evaluando la resiliencia del código C. |
| [`vasquez inject`](#inject) | Inyecta fallos controlados (malloc/calloc/realloc NULL, cascada, memoria basura) evaluando la resiliencia del código C. |
| [`vasquez stress`](#stress) | Ejecuta una prueba de estrés repetitiva con fallos probabilísticos de asignación. |
| [`vasquez doctor`](#doctor) | Audita el entorno y verifica la disponibilidad del compilador y la librería de inyección. |
| [`vasquez report`](#report) | Genera directamente la sección de reporte Markdown de VASQUEZ para Dredd. |
| [`vasquez version`](#version) | Muestra la versión de VASQUEZ. |

### `vasquez check`

Inyecta fallos controlados (malloc/calloc/realloc NULL, cascada, memoria basura) evaluando la resiliencia del código C.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `target` | `Path` | Archivo .c o binario a evaluar bajo inyección de fallos |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--faults`, `-f` | `Optional[str]` | `None` | Especificación: 'malloc:1,malloc:2,fopen:1,fwrite:1024,write:ENOSPC' |
| `--fail-malloc-at` | `Optional[int]` | `None` | Fallar en la llamada N a malloc. |
| `--fail-malloc-prob` | `Optional[float]` | `None` | Probabilidad de fallo en malloc (0.0 a 1.0). |
| `--fail-realloc-at` | `Optional[int]` | `None` | Fallar en la llamada N a realloc devolviendo NULL (Mejora 11). |
| `--fail-calloc-at` | `Optional[int]` | `None` | Fallar en la llamada N a calloc devolviendo NULL (Mejora 16). |
| `--fail-posix-memalign-at` | `Optional[int]` | `None` | Fallar en la llamada N a posix_memalign con ENOMEM (Mejora 16). |
| `--cascade`, `--cascade-failures` | `bool` | `False` | Habilitar modo fallo en cascada (tras el primer error, todas las llamadas fallan) (Mejora 17). |
| `--audit-free-null` | `bool` | `False` | Auditar invocaciones inocuas a free(NULL) en ramas de limpieza (Mejora 20). |
| `--garbage-memory`, `--poison-memory` | `bool` | `False` | Rellenar bloques con patrón de memoria basura (0xA5) para detectar lecturas sin inicializar (Mejora 25). |
| `--poison-byte` | `int` | `165` | Valor byte para envenenamiento de memoria (por defecto 0xA5 / 165). |
| `--fail-write-after` | `Optional[int]` | `None` | Simular disco lleno tras N bytes escritos. |
| `--trace` | `bool` | `False` | Habilitar registro detallado de funciones interceptadas. |
| `--check-leaks` | `bool` | `False` | Verificar que no haya fugas de memoria en caminos de error. |
| `--input`, `-i` | `str` | `` | Entrada estándar (stdin) |
| `--json` | `bool` | `False` | Emitir salida en formato JSON estructurado |
| `--md`, `--output-md` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |

#### Ejemplo de Invocación
```bash
vasquez check <target>
```

### `vasquez inject`

Inyecta fallos controlados (malloc/calloc/realloc NULL, cascada, memoria basura) evaluando la resiliencia del código C.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `target` | `Path` | Archivo .c o binario a evaluar bajo inyección de fallos |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--faults`, `-f` | `Optional[str]` | `None` | Especificación: 'malloc:1,malloc:2,fopen:1,fwrite:1024,write:ENOSPC' |
| `--fail-malloc-at` | `Optional[int]` | `None` | Fallar en la llamada N a malloc. |
| `--fail-malloc-prob` | `Optional[float]` | `None` | Probabilidad de fallo en malloc (0.0 a 1.0). |
| `--fail-realloc-at` | `Optional[int]` | `None` | Fallar en la llamada N a realloc devolviendo NULL (Mejora 11). |
| `--fail-calloc-at` | `Optional[int]` | `None` | Fallar en la llamada N a calloc devolviendo NULL (Mejora 16). |
| `--fail-posix-memalign-at` | `Optional[int]` | `None` | Fallar en la llamada N a posix_memalign con ENOMEM (Mejora 16). |
| `--cascade`, `--cascade-failures` | `bool` | `False` | Habilitar modo fallo en cascada (tras el primer error, todas las llamadas fallan) (Mejora 17). |
| `--audit-free-null` | `bool` | `False` | Auditar invocaciones inocuas a free(NULL) en ramas de limpieza (Mejora 20). |
| `--garbage-memory`, `--poison-memory` | `bool` | `False` | Rellenar bloques con patrón de memoria basura (0xA5) para detectar lecturas sin inicializar (Mejora 25). |
| `--poison-byte` | `int` | `165` | Valor byte para envenenamiento de memoria (por defecto 0xA5 / 165). |
| `--fail-write-after` | `Optional[int]` | `None` | Simular disco lleno tras N bytes escritos. |
| `--trace` | `bool` | `False` | Habilitar registro detallado de funciones interceptadas. |
| `--check-leaks` | `bool` | `False` | Verificar que no haya fugas de memoria en caminos de error. |
| `--input`, `-i` | `str` | `` | Entrada estándar (stdin) |
| `--json` | `bool` | `False` | Emitir salida en formato JSON estructurado |
| `--md`, `--output-md` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |

#### Ejemplo de Invocación
```bash
vasquez inject <target>
```

### `vasquez stress`

Ejecuta una prueba de estrés repetitiva con fallos probabilísticos de asignación.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `target` | `Path` | Archivo .c o binario a evaluar bajo estrés probabilístico |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--iterations`, `-n` | `int` | `10` | Cantidad de corridas bajo inyección aleatoria. |
| `--prob`, `-p` | `float` | `0.25` | Probabilidad de fallo por llamada a malloc (0.0 a 1.0). |
| `--json` | `bool` | `False` | Emitir salida en formato JSON. |

#### Ejemplo de Invocación
```bash
vasquez stress <target>
```

### `vasquez doctor`

Audita el entorno y verifica la disponibilidad del compilador y la librería de inyección.

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Emitir diagnóstico en formato JSON. |
| `-v`, `--verbose` | `bool` | `False` | Mostrar detalle completo. |

#### Ejemplo de Invocación
```bash
vasquez doctor
```

### `vasquez report`

Genera directamente la sección de reporte Markdown de VASQUEZ para Dredd.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `target` | `Path` | Archivo .c o binario a evaluar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `Optional[Path]` | `None` | Ruta de destino del archivo Markdown. |
| `--faults`, `-f` | `Optional[str]` | `None` | Especificación de fallos (e.g. 'malloc:1,fopen:2,write:ENOSPC'). |
| `--input`, `-i` | `str` | `` | Entrada estándar. |

#### Ejemplo de Invocación
```bash
vasquez report <target>
```

### `vasquez version`

Muestra la versión de VASQUEZ.

#### Ejemplo de Invocación
```bash
vasquez version
```

---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
vasquez check --json
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: vasquez, tool=vasquez, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`vasquez` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

---

## 5. Diagnóstico y Códigos de Salida

### Códigos de Retorno (`exit code`)
| Código | Significado |
| :---: | :--- |
| `0` | Ejecución exitosa sin hallazgos críticos ni errores de sintaxis. |
| `1` | Hallazgos pedagógicos detectados, infracción de reglas o advertencias activas. |
| `2` | Error de sintaxis en argumentos CLI o archivo fuente no encontrado. |
| `>2` | Error no recuperable del sistema, fallo de memoria o excepción interna. |

### Diagnóstico del Entorno (`doctor`)
Ante comportamientos inesperados, verificá el estado operativo con:
```bash
vasquez doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.