from __future__ import annotations

import argparse
import base64
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv


RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4.1-mini"


def llm_equation_regions(regions_json: Path, output_json: Path, limit: int | None = None, model: str | None = None) -> list[dict[str, Any]]:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY was not found in .env or environment")

    regions = json.loads(regions_json.read_text(encoding="utf-8"))
    selected = regions[:limit] if limit else regions
    model_name = model or os.getenv("OPENAI_VISION_MODEL", DEFAULT_MODEL)

    enriched: list[dict[str, Any]] = []
    for region in selected:
        crop_path = Path(region.get("crop_path") or f"output/equation_crops/{region['region_id']}.png")
        if not crop_path.exists():
            enriched.append({**region, "llm_status": "missing_crop", "llm_error": str(crop_path)})
            continue
        try:
            llm_result = _call_openai(api_key, model_name, region, crop_path)
            enriched.append({**region, **llm_result, "llm_model": model_name, "llm_status": "complete"})
        except Exception as exc:
            enriched.append({**region, "llm_model": model_name, "llm_status": "error", "llm_error": str(exc)})

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    return enriched


def _call_openai(api_key: str, model: str, region: dict[str, Any], crop_path: Path) -> dict[str, Any]:
    image_b64 = base64.b64encode(crop_path.read_bytes()).decode("ascii")
    prompt = (
        "You are extracting mathematical notation from a cropped PDF image. "
        "Return only valid JSON with keys: latex, plain_text, confidence, notes. "
        "Use LaTeX for math. Preserve subscripts/superscripts. "
        "If the crop is not math or is unreadable, set latex to null and explain briefly in notes. "
        f"Region type: {region.get('region_type')}. "
        f"PDF extracted raw text, possibly broken: {region.get('raw_text')!r}."
    )
    payload = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{image_b64}"},
                ],
            }
        ],
        "max_output_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=60) as client:
        response = client.post(RESPONSES_URL, headers=headers, json=payload)
        response.raise_for_status()
    data = response.json()
    text = _extract_response_text(data)
    parsed = _parse_json_text(text)
    return {
        "llm_latex": parsed.get("latex"),
        "llm_plain_text": parsed.get("plain_text"),
        "llm_confidence": parsed.get("confidence"),
        "llm_notes": parsed.get("notes"),
        "llm_raw_response": text,
    }


def _extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    parts: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return {"latex": None, "plain_text": None, "confidence": 0, "notes": f"Non-JSON response: {text[:300]}"}
    if not isinstance(parsed, dict):
        return {"latex": None, "plain_text": None, "confidence": 0, "notes": "JSON response was not an object"}
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpenAI vision extraction over equation crop images.")
    parser.add_argument("--regions-json", default="output/report_equation_ocr.json")
    parser.add_argument("--output-json", default="output/report_equation_llm.json")
    parser.add_argument("--limit", type=int, default=3, help="Limit regions processed for cost control. Use 0 for all.")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    limit = None if args.limit == 0 else args.limit
    results = llm_equation_regions(Path(args.regions_json), Path(args.output_json), limit=limit, model=args.model)
    print(f"llm_regions={len(results)}")
    print(args.output_json)


if __name__ == "__main__":
    main()
