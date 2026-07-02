from __future__ import annotations

import re


def clean_llm_text(text: str) -> str:
    """Normalize LLM prose for business reports and dashboard display."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            cleaned_lines.append("")
            continue
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*(\d+)[.)]\s+", r"\1. ", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"__(.*?)__", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", line)
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
