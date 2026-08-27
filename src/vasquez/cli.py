"""CLI principal de VASQUEZ."""

import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from vasquez.core.models import RobustnessReport, FaultConfig, FaultType
from vasquez.core.fault_runner import evaluate_robustness

app = typer.Typer(
    name="vasquez",
    help="Motor de inyección de fallos de entorno y hardware en C vía LD_PRELOAD",
    add_completion=True
)
console = Console()


@app.command()
def inject(
    target: Path = typer.Argument(..., help="Archivo .c o binario a evaluar bajo inyección de fallos", exists=True),
    faults_str: Optional[str] = typer.Option(None, "--faults", "-f", help="Especificación: 'malloc:1,malloc:2,fopen:1'"),
    input_data: str = typer.Option("", "--input", "-i", help="Entrada estándar (stdin)"),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en formato JSON estructurado")
):
    """Inyecta fallos controlados (malloc NULL, fopen EACCES) evaluando si el código C maneja el error sin crashear."""
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

    report = evaluate_robustness(target, scenarios=scenarios, input_data=input_data)

    if json_output:
        print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
        if not report.passed:
            raise typer.Exit(code=1)
        return

    table = Table(title=f"Evaluación de Robustez ante Inyección de Fallos ({target.name})", show_header=True, header_style="bold red")
    table.add_column("Escenario de Fallo", style="cyan")
    table.add_column("Llamada #", style="dim", justify="right")
    table.add_column("Estado", style="bold")
    table.add_column("Código / Señal", style="yellow")
    table.add_column("Diagnóstico de Robustez", style="white")

    for r in report.results:
        status_str = "[green]MANEJADO ✓[/green]" if r.handled_gracefully else "[red]CRASH ✗[/red]"
        exit_str = f"Signal: {r.signal_name}" if r.signal_name else f"Exit: {r.exit_code}"
        table.add_row(
            r.fault_config.fault_type.value,
            str(r.fault_config.fail_at_invocation),
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
            f"• El programa desreferenció punteros nulos sin verificar retornos.",
            title="[bold red]VASQUEZ Robustness Failed[/bold red]"
        ))
        raise typer.Exit(code=1)


@app.command()
def version():
    """Muestra la versión de VASQUEZ."""
    from vasquez import __version__
    console.print(f"[bold cyan]VASQUEZ[/bold cyan] versión [green]{__version__}[/green]")


if __name__ == "__main__":
    app()
