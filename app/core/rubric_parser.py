"""Parser for architectural rubric YAML files."""

from pathlib import Path

import yaml


class RubricParser:
    """Loads and formats rubric rules from YAML files."""

    def load(self, paths: list[str]) -> list[dict]:
        """Load rubric rules from a list of YAML file paths."""
        rules = []
        for path in paths:
            p = Path(path)
            if not p.exists():
                continue
            with open(p) as f:
                data = yaml.safe_load(f)
            if data and "rules" in data:
                rules.extend(data["rules"])
        return rules

    def format_rules(self, rules: list[dict]) -> str:
        """Format loaded rules into a prompt-friendly string."""
        if not rules:
            return "No rubric rules loaded."
        lines = []
        for i, rule in enumerate(rules, 1):
            name = rule.get("name", "Unnamed")
            desc = rule.get("description", "")
            severity = rule.get("severity", "warning")
            lines.append(f"{i}. [{severity.upper()}] {name}: {desc}")
        return "\n".join(lines)
