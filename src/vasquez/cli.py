"""CLI principal de VASQUEZ."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from vasquez import __version__
from vasquez.core.models import RobustnessReport, FaultConfig, FaultType, FaultRunResult
from vasquez.core.fault_runner import evaluate_robustness, run_single_fault_scenario
from vasquez.core.doctor import ejecutar_diagnostico_doctor

app = typer.Typer(
    name="vasquez",
    help="Motor de inyección de fallos de entorno y hardware en C vía LD_PRELOAD",
    add_completion=True
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"[bold cyan]vasquez[/bold cyan] versión [green]{__version__}[/green]")
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "-v",
        "--version",
        help="Muestra la versión de VASQUEZ y finaliza.",
        callback=version_callback,
        is_eager=True,
    )
):
    """Punto de entrada principal de VASQUEZ."""
    pass


def generar_seccion_markdown(report: RobustnessReport) -> str:
    """Genera sección de inyección de fallos y programación defensiva para Dredd."""
    lines = ["## Inyección de Fallos y Programación Defensiva (Vasquez)\n"]
    lines.append(f"- **Archivo analizado:** `{Path(report.target_binary).name}`")
    lines.append(f"- **Escenarios inyectados:** {report.total_scenarios_tested}")
    lines.append(f"- **Crashes / Fallos de control:** {report.crashed_scenarios_count}\n")
    if report.passed:
        lines.append("> [!TIP]\n> **Manejo Defensivo Verificado:** El código manejó correctamente los retornos `NULL` de malloc/fopen sin crashear ni corromper memoria.\n")
    else:
        lines.append("> [!WARNING]\n> **Vulnerabilidad de Robustez:** Se detectaron accesos desprotegidos ante fallas del sistema operativo o falta de memoria.\n")
        lines.append("| Fallo Inyectado | Invocación # | Categoría | Estado | Retorno / Señal | Diagnóstico |")
        lines.append("| :--- | :---: | :--- | :---: | :---: | :--- |")
        for r in report.results:
            st = "✓ MANEJADO" if r.handled_gracefully else "❌ CRASH"
            ret_s = f"`Signal: {r.signal_name}`" if r.signal_name else f"`Exit: {r.exit_code}`"
            cat_s = r.crash_category or "N/A"
            lines.append(f"| `{r.fault_config.fault_type.value}` | {r.fault_config.fail_at_invocation} | `{cat_s}` | **{st}** | {ret_s} | {r.diagnosis} |")
        lines.append("")
    return "\n".join(lines)


@app.command("inject")
@app.command("check")
def inject(
    target: Path = typer.Argument(..., help="Archivo .c o binario a evaluar bajo inyección de fallos", exists=True),
    faults_str: Optional[str] = typer.Option(None, "--faults", "-f", help="Especificación: 'malloc:1,malloc:2,fopen:1,fwrite:1024'"),
    fail_malloc_at: Optional[int] = typer.Option(None, "--fail-malloc-at", help="Fallar en la llamada N a malloc."),
    fail_malloc_prob: Optional[float] = typer.Option(None, "--fail-malloc-prob", help="Probabilidad de fallo en malloc (0.0 a 1.0)."),
    fail_write_after: Optional[int] = typer.Option(None, "--fail-write-after", help="Simular disco lleno tras N bytes escritos."),
    trace: bool = typer.Option(False, "--trace", help="Habilitar registro detallado de funciones interceptadas."),
    check_leaks: bool = typer.Option(False, "--check-leaks", help="Verificar que no haya fugas de memoria en caminos de error."),
    input_data: str = typer.Option("", "--input", "-i", help="Entrada estándar (stdin)"),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en formato JSON estructurado"),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
):
    """Inyecta fallos controlados (malloc NULL, fopen EACCES, fwrite ENOSPC) evaluando la resiliencia del código C."""
    scenarios = []

    if fail_malloc_at is not None:
        scenarios.append(FaultConfig(
            fault_type=FaultType.MALLOC_FAIL,
            fail_at_invocation=fail_malloc_at,
            enable_trace=trace,
            check_leaks=check_leaks
        ))

    if fail_malloc_prob is not None:
        scenarios.append(FaultConfig(
            fault_type=FaultType.PROBABILISTIC,
            fail_probability=fail_malloc_prob,
            enable_trace=trace,
            check_leaks=check_leaks
        ))

    if fail_write_after is not None:
        scenarios.append(FaultConfig(
            fault_type=FaultType.FWRITE_FAIL,
            fail_after_bytes=fail_write_after,
            enable_trace=trace,
            check_leaks=check_leaks
        ))

    if faults_str:
        for item in faults_str.split(","):
            parts = item.strip().split(":")
            if parts:
                f_type_str = parts[0].lower()
                f_num = int(parts[1]) if len(parts) > 1 else 1
                if f_type_str == "malloc":
                    scenarios.append(FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=f_num, enable_trace=trace, check_leaks=check_leaks))
                elif f_type_str == "calloc":
                    scenarios.append(FaultConfig(fault_type=FaultType.CALLOC_FAIL, fail_at_invocation=f_num, enable_trace=trace, check_leaks=check_leaks))
                elif f_type_str == "realloc":
                    scenarios.append(FaultConfig(fault_type=FaultType.REALLOC_FAIL, fail_at_invocation=f_num, enable_trace=trace, check_leaks=check_leaks))
                elif f_type_str == "fopen":
                    scenarios.append(FaultConfig(fault_type=FaultType.FOPEN_FAIL, fail_at_invocation=f_num, errno_value=13, enable_trace=trace))
                elif f_type_str == "fwrite":
                    scenarios.append(FaultConfig(fault_type=FaultType.FWRITE_FAIL, fail_after_bytes=f_num, enable_trace=trace))

    report = evaluate_robustness(target, scenarios=scenarios if scenarios else None, input_data=input_data)

    if output_md:
        md_text = generar_seccion_markdown(report)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[bold green]✓ Sección Markdown generada en:[/bold green] {output_md}")
        raise typer.Exit(code=0 if report.passed else 1)

    if json_output:
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
        if not report.passed:
            raise typer.Exit(code=1)
        return

    table = Table(title=f"Evaluación de Robustez ante Inyección de Fallos ({target.name})", show_header=True, header_style="bold red")
    table.add_column("Escenario de Fallo", style="cyan")
    table.add_column("Llamada # / Config", style="dim", justify="right")
    table.add_column("Categoría", style="magenta")
    table.add_column("Estado", style="bold")
    table.add_column("Código / Señal", style="yellow")
    table.add_column("Diagnóstico de Robustez", style="white")

    for r in report.results:
        status_str = "[green]MANEJADO ✓[/green]" if r.handled_gracefully else "[red]CRASH ✗[/red]"
        exit_str = f"Signal: {r.signal_name}" if r.signal_name else f"Exit: {r.exit_code}"
        call_info = str(r.fault_config.fail_at_invocation) if r.fault_config.fail_at_invocation > 0 else f"prob={r.fault_config.fail_probability}"
        cat_info = r.crash_category or "N/A"
        table.add_row(
            r.fault_config.fault_type.value,
            call_info,
            cat_info,
            status_str,
            exit_str,
            r.diagnosis
        )

    console.print(table)

    if report.passed:
        console.print(Panel(
            f"[bold green]✓ Código Defensivo y Robusto[/bold green]\n"
            f"• Escenarios probados: {report.total_scenarios_tested}\n"
            f"• Ningún fallo de memoria o I/O provocó un Segmentation Fault.",
            title="[bold green]VASQUEZ Robustness Passed[/bold green]"
        ))
    else:
        console.print(Panel(
            f"[bold red]❌ Fallo de Robustez Detectado[/bold red]\n"
            f"• Escenarios que crashearon: {report.crashed_scenarios_count}/{report.total_scenarios_tested}\n"
            f"• El programa desreferenció punteros nulos o abortó sin limpiar recursos.",
            title="[bold red]VASQUEZ Robustness Failed[/bold red]"
        ))
        raise typer.Exit(code=1)


@app.command("stress")
def stress_cmd(
    target: Path = typer.Argument(..., help="Archivo .c o binario a evaluar bajo estrés probabilístico", exists=True),
    iterations: int = typer.Option(10, "--iterations", "-n", help="Cantidad de corridas bajo inyección aleatoria."),
    prob: float = typer.Option(0.25, "--prob", "-p", help="Probabilidad de fallo por llamada a malloc (0.0 a 1.0)."),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en formato JSON.")
):
    """Ejecuta una prueba de estrés repetitiva con fallos probabilísticos de asignación."""
    scenarios = [
        FaultConfig(fault_type=FaultType.PROBABILISTIC, fail_probability=prob)
        for _ in range(iterations)
    ]
    report = evaluate_robustness(target, scenarios=scenarios)

    if json_output:
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if report.passed else 1)

    console.print(f"[bold cyan]Prueba de Estrés Probabilístico ({iterations} corridas con p={prob}):[/bold cyan]")
    console.print(f"• Corridas exitosas / manejadas: [green]{report.passed_scenarios_count}/{iterations}[/green]")
    console.print(f"• Caídas / Crashes: [red]{report.crashed_scenarios_count}/{iterations}[/red]")

    if report.passed:
        console.print("[bold green]✓ El programa resistió todas las iteraciones de estrés sin crashear.[/bold green]")
        raise typer.Exit(code=0)
    else:
        console.print("[bold red]❌ El programa falló bajo estrés probabilístico.[/bold red]")
        raise typer.Exit(code=1)


@app.command("doctor")
def doctor_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emitir diagnóstico en formato JSON."),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Mostrar detalle completo.")
):
    """Audita el entorno y verifica la disponibilidad del compilador y la librería de inyección."""
    rep = ejecutar_diagnostico_doctor()
    if json_output:
        print(json.dumps(rep.model_dump(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if rep.all_ok else 1)

    table = Table(title="Diagnóstico del Entorno (VASQUEZ Doctor)", show_header=True, header_style="bold red")
    table.add_column("Componente", style="bold")
    table.add_column("Categoría", style="dim")
    table.add_column("Tipo", style="yellow")
    table.add_column("Estado", style="bold")
    table.add_column("Detalle", style="white")

    for c in rep.checks:
        st_color = "green" if c.status == "OK" else ("yellow" if c.status in ("INFO", "WARNING") else "red")
        req_s = "Requerido" if c.required else "Opcional"
        det = c.version if c.version else c.detail
        table.add_row(c.name, c.category, req_s, f"[{st_color}]{c.status}[/{st_color}]", det)

    console.print(table)
    if rep.all_ok:
        console.print("[bold green]✓ Todos los componentes requeridos por VASQUEZ están disponibles.[/bold green]")
        raise typer.Exit(code=0)
    else:
        console.print("[bold red]❌ Faltan componentes críticos para el funcionamiento de VASQUEZ.[/bold red]")
        raise typer.Exit(code=1)


@app.command("report")
def report_cmd(
    target: Path = typer.Argument(..., help="Archivo .c o binario a evaluar.", exists=True),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
    faults_str: Optional[str] = typer.Option(None, "--faults", "-f", help="Especificación de fallos."),
    input_data: str = typer.Option("", "--input", "-i", help="Entrada estándar."),
):
    """Genera directamente la sección de reporte Markdown de VASQUEZ para Dredd."""
    scenarios = []
    if faults_str:
        for item in faults_str.split(","):
            parts = item.strip().split(":")
            if parts:
                f_type_str = parts[0].lower()
                f_num = int(parts[1]) if len(parts) > 1 else 1
                if f_type_str == "malloc":
                    scenarios.append(FaultConfig(fault_type=FaultType.MALLOC_FAIL, fail_at_invocation=f_num))
                elif f_type_str == "fopen":
                    scenarios.append(FaultConfig(fault_type=FaultType.FOPEN_FAIL, fail_at_invocation=f_num, errno_value=13))

    report = evaluate_robustness(target, scenarios=scenarios if scenarios else None, input_data=input_data)
    md_content = generar_seccion_markdown(report)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[bold green]✓ Reporte Markdown generado en:[/bold green] {output}")
    else:
        print(md_content)


@app.command()
def version():
    """Muestra la versión de VASQUEZ."""
    console.print(f"[bold cyan]VASQUEZ[/bold cyan] versión [green]{__version__}[/green]")


if __name__ == "__main__":
    app()
