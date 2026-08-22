"""Source analysis and report-request construction."""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rep_uuid import transmit_report_request


@dataclass(frozen=True)
class ReporterFinding:
    category: str
    severity: str
    message: str
    line: int | None = None
    evidence: str | None = None


class ReporterAgent:
    """Audit application source for common API and data-contract failures."""

    def __init__(self, source_path: str | Path = "app.py"):
        self.source_path = Path(source_path)

    def analyze(self) -> list[ReporterFinding]:
        source = self.source_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(self.source_path))
        except SyntaxError as error:
            return [ReporterFinding("syntax_error", "critical", error.msg, error.lineno)]
        findings = self._find_api_gaps(source)
        findings.extend(self._find_missing_data(tree))
        findings.extend(self._find_format_risks(tree))
        findings.extend(self._find_contradictions(source))
        return findings

    def build_request(self) -> dict[str, Any]:
        findings = self.analyze()
        report = {
            "agent": "reporter_agent",
            "source": str(self.source_path),
            "findings": [asdict(finding) for finding in findings],
            "summary": {
                "total": len(findings),
                "critical": sum(f.severity == "critical" for f in findings),
                "high": sum(f.severity == "high" for f in findings),
                "medium": sum(f.severity == "medium" for f in findings),
            },
        }
        return transmit_report_request(report)

    def _find_api_gaps(self, source: str) -> list[ReporterFinding]:
        checks = {
            "API error": r"(api|endpoint|request|http).{0,40}(error|exception|fail)",
            "API key": r"(api[_ -]?key|configure\s*\()",
        }
        return [
            ReporterFinding("api_endpoint_error", "high", f"No {label} handling was detected.")
            for label, pattern in checks.items()
            if not re.search(pattern, source, re.IGNORECASE)
        ]

    def _find_missing_data(self, tree: ast.AST) -> list[ReporterFinding]:
        return [
            ReporterFinding("missing_data", "medium", f"{node.func.attr}() is called without a key or path.", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "read_text"}
            and not node.args
            and not node.keywords
        ]

    def _find_format_risks(self, tree: ast.AST) -> list[ReporterFinding]:
        return [
            ReporterFinding("invalid_data_format", "medium", "JSON parsing requires malformed-input handling at this call site.", node.lineno)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "loads"
        ]

    def _find_contradictions(self, source: str) -> list[ReporterFinding]:
        if source.count("4–6") > 1:
            return [ReporterFinding("contradictory_statement", "low", "The strict 4–6 subtask contract is repeated; verify every caller enforces it.", evidence="4–6")]
        return []


def generate_report_request(source_path: str | Path = "app.py") -> dict[str, Any]:
    """Analyze source and return a UUID-tagged request for the reporting flow."""
    return ReporterAgent(source_path).build_request()