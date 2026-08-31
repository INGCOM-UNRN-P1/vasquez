---
title: "Guía de Extensión y Creación de Plugins: vasquez"
subtitle: "Manual de integración, desarrollo de extensiones y uso de la API Python de vasquez"
author: "Cátedra de Algoritmos y Programación"
date: "2026-08-31"
---

(manual-vasquez-plugins)=
# Guía de Extensión y Plugins: vasquez

````{abstract}
Esta guía técnica detalla cómo desarrollar extensiones, crear nuevos plugins e integrar programáticamente **`vasquez`** en herramientas de evaluación, entornos de integración continua (CI/CD) o scripts docentes.
````

---

(manual-vasquez-plugins-arquitectura)=
## 1. Arquitectura de Extensión

`vasquez` provee una arquitectura modular desacoplada basada en puntos de entrada (Entry Points) estándar de Python (`[project.entry-points]`) o interfaces de inyección funcional:

- **Mecanismo de Extensión Principal**: `Interceptores de Inyección en Runtime (LD_PRELOAD)`.
- **Punto de Entrada Oficial**: `vasquez.interceptors`.
- **Formato de Comunicación**: Estructuras de datos serializables JSON / Pydantic models.

---

(manual-vasquez-plugins-tutorial)=
## 2. Desarrollo Paso a Paso de un Plugin

### Paso 1: Definir la Clase del Plugin

Creá un archivo Python (por ejemplo `mi_plugin.py`) e implementá la interfaz requerida:

````{code-block} python
:linenos:
from vasquez.core.models import FaultConfig, FaultType

class InterceptorSocket:
    """Simula desconexión de red o fallo en socket()."""
    name = "socket_failure"

    def generate_c_wrapper(self) -> str:
        return """
        int socket(int domain, int type, int protocol) {
            if (should_fail("socket")) {
                errno = ECONNREFUSED;
                return -1;
            }
            return real_socket(domain, type, protocol);
        }
        """
````

### Paso 2: Registrar el Plugin en `pyproject.toml`

Para que `vasquez` descubra y cargue automáticamente tu plugin, agregalo en tu `pyproject.toml`:

````{code-block} toml
[project.entry-points."vasquez.interceptors"]
mi_plugin = "mi_paquete.modulo:MiPlugin"
````

### Paso 3: Instalar y Verificar el Plugin

Instalá tu extensión en modo editable y comprobá que `vasquez` la reconozca:

````{code-block} bash
# Instalación local
pip install -e .

# Verificación de plugins registrados
vasquez plugins list
````

---

(manual-vasquez-plugins-sdk)=
## 3. Conexión Programática mediante la API Python

Podés importar y ejecutar `vasquez` directamente desde scripts de Python sin invocar subprocesos:

````{code-block} python
:linenos:
from pathlib import Path
import vasquez

# Ejecución programática
resultado = vasquez.ejecutar_analisis(
    target=Path("src/main.c"),
    verbose=False
)

print(f"Estado: {resultado.passed}")
for item in resultado.items:
    print(f"- [{item.categoria}] {item.mensaje}")
````

---

(manual-vasquez-plugins-ci)=
## 4. Integración en Pipelines de CI/CD (GitHub Actions / GitLab CI)

Podés integrar `vasquez` en tus flujos automatizados de Git para bloquear entregas que no cumplan los requisitos de cátedra:

````{code-block} yaml
# .github/workflows/evaluacion.yml
name: Auditoría de Código Cátedra
on: [push, pull_request]

jobs:
  auditoria:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Instalar dependencias nativas
        run: sudo apt-get update && sudo apt-get install -y gcc clang-format valgrind
        
      - name: Configurar Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          
      - name: Instalar vasquez
        run: pip install -e ./vasquez
        
      - name: Ejecutar Auditoría
        run: vasquez check src/ include/ --json > reporte.json
````

---

(manual-vasquez-plugins-ejercicios)=
## 5. Ejercicios de Extensión Práctica

````{exercise} Ejercicio 1: Creación de un Filtro Personalizado
Crear una regla o filtro que detecte cuando una función supere las 40 líneas de código y emita una advertencia pedagógica.

**Pasos sugeridos:**
1. Crear la clase `ContadorLineasPlugin`.
2. Inspeccionar la cantidad de saltos de línea dentro del cuerpo de cada función.
3. Retornar un diagnóstico con severidad de advertencia.
````

````{solution} Ejercicio 1
```python
class ContadorLineasPlugin:
    name = "max_lineas_funcion"
    
    def analyze(self, ast, source_code: str):
        # Lógica de inspección de longitud
        pass
```
````

````{exercise} Ejercicio 2: Conexión con un Exportador de Base de Datos
Implementar un hook que guarde el resultado de la auditoría en una base de datos SQLite local para seguimiento histórico de la evolución del alumno.

**Pasos sugeridos:**
1. Conectar con `sqlite3.connect("historial.db")`.
2. Crear la tabla `auditorias` si no existe.
3. Insertar timestamp, legajo, total de violaciones y estado de aprobación.
````

````{solution} Ejercicio 2
```python
import sqlite3
from datetime import datetime

def guardar_historico(legajo: str, aprobado: bool, total_fallas: int):
    with sqlite3.connect("historial.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS auditorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT,
                legajo TEXT,
                aprobado INTEGER,
                fallas INTEGER
            )
        """)
        conn.execute(
            "INSERT INTO auditorias (fecha, legajo, aprobado, fallas) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(), legajo, int(aprobado), total_fallas)
        )
```
````
