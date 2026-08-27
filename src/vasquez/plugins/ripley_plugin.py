"""Plugin de VASQUEZ para el microkernel RIPLEY."""

from pathlib import Path
from typing import Dict, Any
from vasquez.core.fault_runner import evaluate_robustness


class VasquezPlugin:
    """Plugin de inyección de fallos para Ripley."""

    name = "fault_injection"
    description = "Inyección de fallos de memoria (malloc NULL) y disco vía LD_PRELOAD para evaluar robustez"

    def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        source_dir = Path(context.get("source_dir", "."))
        main_c = source_dir / "main.c"
        if not main_c.exists():
            return {"passed": True, "message": "main.c no encontrado"}

        try:
            report = evaluate_robustness(main_c)
            return {
                "passed": report.passed,
                "total_scenarios": report.total_scenarios_tested,
                "passed_scenarios": report.passed_scenarios_count,
                "crashed_scenarios": report.crashed_scenarios_count,
                "results": [r.model_dump() for r in report.results]
            }
        except Exception as e:
            return {"passed": False, "error": str(e)}
