from __future__ import annotations

import re


OCR_FIXES = {
    "cust0mer": "customer",
    "retent1on": "retention",
    "remalns": "remains",
    "metr1c": "metric",
}


def normalize_text(text: str) -> str:
    for wrong, right in OCR_FIXES.items():
        text = text.replace(wrong, right)
    if text.lstrip().startswith("|"):
        return "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.splitlines())
    text = re.sub(r"(?<!\.)\n(?!\n)", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
