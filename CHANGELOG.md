# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
versiones según [SemVer](https://semver.org/lang/es/).

## [0.2.0] - 2026-09-28

Primera versión con registro de cambios; lo anterior está en el historial de git.

### Agregado

- **check**: evaluar proyectos de varios archivos y explicar los errores de compilación (N-VASQUEZ-02, N-ECO-05) (`c6058a0`)
- **cli**: cumplir el contrato de línea de comandos de LINEAMIENTOS §3.2 (N-ECO-04) (`888309f`)
- **core**: soportar Windows nativo mediante interceptación en enlace (`b3290e8`)

### Corregido

- **check**: rechazar con un mensaje los archivos que no son fuente ni ejecutable (N-ECO-05) (`27731ec`)
- **cli**: forzar UTF-8 en la salida redirigida bajo Windows (`061d0c9`)

### Documentación

- agregar el texto de la licencia GPL-3.0-or-later que declara pyproject (N-ECO-06) (`d85d248`)
- incorporar manual de uso integral y referencia tecnica (vasquez) (`ad8ef5c`)

### Mantenimiento

- **calidad**: verificar errores de Python y dependencias vulnerables (N-ECO-08, N-ECO-13) (`e111b2a`)
- **deps**: mover las dependencias de desarrollo a dependency-groups (N-ECO-07) (`b73fce6`)
- actualizar uv.lock con extra dev (`a145e31`)
- omitir en Windows el escenario de posix_memalign (`4adf46d`)
- **core**: corregir comentario duplicado en crash_classifier (`91b9256`)
- agregar job Windows con GCC UCRT64 de MSYS2 para la vía de enlace (vasquez) (`3df9f2a`)
