import json
import re
from hashlib import sha256


MAX_CONTEXT_CHARS = 6_000


def prepare_analysis_fragments(materials: list) -> tuple[list[dict], int]:
    """把解析行整理成章节块，减少重复元数据，但保留可反查的来源定位。"""
    chunks: list[dict] = []
    source_fragment_count = 0
    for material in materials:
        heading = ""
        pending: list[dict] = []
        pending_chars = 0
        for fragment in material.fragments:
            source_fragment_count += 1
            item = fragment.model_dump(mode="json")
            text = _normalize(item.get("text", ""))
            if not text:
                continue
            if item.get("kind") == "heading":
                if pending:
                    chunks.append(_merge_chunk(pending, heading))
                    pending, pending_chars = [], 0
                heading = text.lstrip("# ").strip()
                continue
            if pending and pending_chars + len(text) > MAX_CONTEXT_CHARS:
                chunks.append(_merge_chunk(pending, heading))
                pending, pending_chars = [], 0
            pending.append(item | {"text": text})
            pending_chars += len(text)
        if pending:
            chunks.append(_merge_chunk(pending, heading))
    return chunks, source_fragment_count


def input_fingerprint(page: str, mode: str, preflight: dict, context: dict) -> str:
    canonical = {
        "page": page,
        "mode": mode,
        "provider": preflight["provider"],
        "model": preflight["model"],
        "model_endpoint": preflight.get("model_endpoint", ""),
        "prompt_version": preflight["prompt_version"],
        "skill_version": preflight["skill_version"],
        "context": context,
    }
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _merge_chunk(items: list[dict], heading: str) -> dict:
    first = items[0]["source_reference"]
    last = items[-1]["source_reference"]
    locator = first.get("locator", "")
    if last.get("locator") and last.get("locator") != locator:
        locator = f"{locator} ～ {last['locator']}"
    body = "\n".join(item["text"] for item in items)
    return {
        "kind": "section",
        "text": f"【{heading}】\n{body}" if heading else body,
        "source_reference": {
            **first,
            "locator": locator,
            "section": heading,
            "source_fragment_count": len(items),
        },
    }


def _normalize(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value).strip()
