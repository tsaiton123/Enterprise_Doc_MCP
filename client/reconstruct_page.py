from __future__ import annotations

import argparse
from pathlib import Path

from mcp_server import kb


def reconstruct_page(source_file: str, page: int) -> str:
    chunks = kb.get_chunks_by_page(source_file, page)
    lines = [f"# Reconstruction: {source_file} page {page}", ""]
    if not chunks:
        lines.append("_No chunks found._")
        return "\n".join(lines)

    for chunk in chunks:
        lines.append(f"## {chunk['chunk_id']}")
        lines.append("")
        lines.append(chunk["text"])
        lines.append("")
        lines.append(f"- content_type: `{chunk['content_type']}`")
        lines.append(f"- bbox: `{chunk['bbox']}`")
        lines.append(f"- source_ref: `{chunk['metadata'].get('source_ref')}`")
        lines.append("")

    lines.append("## Extraction Audit Notes")
    lines.append("")
    lines.extend(_audit_notes(chunks))
    return "\n".join(lines)


def _audit_notes(chunks: list[dict]) -> list[str]:
    notes: list[str] = []
    combined = "\n".join(chunk["text"] for chunk in chunks)
    if "(cid:" in combined:
        notes.append("- PDF glyph extraction contains `(cid:...)` tokens; math/symbol normalization needs improvement.")
    if "- " in combined or "coli-" in combined or "plan-" in combined:
        notes.append("- Some hyphenated line breaks remain in the reconstructed text.")
    if any(chunk["bbox"] is None for chunk in chunks):
        notes.append("- At least one chunk is missing a bbox.")
    if not notes:
        notes.append("- No obvious extraction issues detected by this lightweight audit.")
    return notes


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct one source page from cleaned chunks.")
    parser.add_argument("source_file")
    parser.add_argument("page", type=int)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    markdown = reconstruct_page(args.source_file, args.page)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
