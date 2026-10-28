import hashlib
from copy import deepcopy
from dataclasses import dataclass

from app.v020_skill_contracts import (
    SKILL_REQUIREMENT_BATCH_SIZE,
    SKILL_SOURCE_BATCH_SIZE,
    StageDefinition,
)


@dataclass(frozen=True)
class SkillStageBatch:
    scope_ids: tuple[str, ...]
    context: dict
    artifacts: dict[str, dict]


def stage_batches(
    stage: StageDefinition,
    context: dict,
    artifacts: dict[str, dict],
    completed_scope_ids: set[str] | None = None,
) -> list[SkillStageBatch]:
    completed = completed_scope_ids or set()
    if stage.stage_id == "S00":
        scope_ids = [
            item["source_reference_id"] for item in context["fragments"]
            if item["source_reference_id"] not in completed
        ]
        size = SKILL_SOURCE_BATCH_SIZE
    else:
        scope_ids = [
            item["requirement_id"] for item in artifacts["S00"]["atomic_requirements"]
            if item["requirement_id"] not in completed
        ]
        size = SKILL_REQUIREMENT_BATCH_SIZE
    return [
        stage_batch(stage, context, artifacts, tuple(scope_ids[index:index + size]))
        for index in range(0, len(scope_ids), size)
    ]


def stage_batch(
    stage: StageDefinition,
    context: dict,
    artifacts: dict[str, dict],
    scope_ids: tuple[str, ...],
) -> SkillStageBatch:
    selected = set(scope_ids)
    if stage.stage_id == "S00":
        batch_context = {
            **context,
            "fragments": [
                item for item in context["fragments"] if item["source_reference_id"] in selected
            ],
        }
        return SkillStageBatch(scope_ids, batch_context, {})

    atomic_requirements = [
        item for item in artifacts["S00"]["atomic_requirements"] if item["requirement_id"] in selected
    ]
    source_ids = {item["source_reference_id"] for item in atomic_requirements}
    batch_context = {
        **context,
        "fragments": [
            item for item in context["fragments"] if item["source_reference_id"] in source_ids
        ],
    }
    batch_artifacts: dict[str, dict] = {
        "S00": {
            "atomic_requirements": deepcopy(atomic_requirements),
            "source_coverage": _source_coverage(artifacts["S00"], selected, source_ids),
            "questions": list(artifacts["S00"].get("questions", [])),
        },
    }
    if "S01" in artifacts:
        batch_artifacts["S01"] = {
            "functions": _filter_linked(artifacts["S01"].get("functions", []), selected),
        }
    if "S02" in artifacts:
        batch_artifacts["S02"] = {
            "rules": _filter_linked(artifacts["S02"].get("rules", []), selected),
        }
    return SkillStageBatch(scope_ids, batch_context, batch_artifacts)


def split_batch(stage: StageDefinition, context: dict, artifacts: dict[str, dict], batch: SkillStageBatch):
    middle = len(batch.scope_ids) // 2
    if middle < 1:
        return [batch]
    return [
        stage_batch(stage, context, artifacts, batch.scope_ids[:middle]),
        stage_batch(stage, context, artifacts, batch.scope_ids[middle:]),
    ]


def canonicalize_batch_output(stage: StageDefinition, raw: dict, batch: SkillStageBatch) -> dict:
    output = deepcopy(raw)
    token = hashlib.sha256("\n".join(batch.scope_ids).encode("utf-8")).hexdigest()[:8].upper()
    if stage.stage_id == "S00":
        mappings: dict[tuple[str, str], str] = {}
        counters: dict[str, int] = {}
        for item in output.get("atomic_requirements", []):
            source_id = str(item.get("source_reference_id", ""))
            old_id = str(item.get("requirement_id", ""))
            counters[source_id] = counters.get(source_id, 0) + 1
            new_id = f"REQ-{_identifier(source_id)}-{counters[source_id]:03d}"
            mappings[(source_id, old_id)] = new_id
            item["requirement_id"] = new_id
        for item in output.get("source_coverage", []):
            source_id = str(item.get("source_reference_id", ""))
            item["requirement_ids"] = [
                mappings.get((source_id, str(requirement_id)), str(requirement_id))
                for requirement_id in item.get("requirement_ids", [])
            ]
    elif stage.stage_id in {"S01", "S02"}:
        key, prefix = ("functions", "FUN") if stage.stage_id == "S01" else ("rules", "RULE")
        id_key = "function_id" if stage.stage_id == "S01" else "rule_id"
        for index, item in enumerate(output.get(key, []), start=1):
            item[id_key] = f"{prefix}-{token}-{index:03d}"
    return output


def merge_stage_outputs(stage: StageDefinition, outputs: list[dict]) -> dict:
    if stage.stage_id == "S00":
        return {
            "atomic_requirements": _unique_items(outputs, "atomic_requirements", "requirement_id"),
            "source_coverage": _unique_items(outputs, "source_coverage", "source_reference_id"),
            "questions": list(dict.fromkeys(
                question for output in outputs for question in output.get("questions", [])
            )),
        }
    if stage.stage_id == "S01":
        return {"functions": _merge_linked_items(outputs, "functions", ("module", "name", "description"))}
    if stage.stage_id == "S02":
        return {"rules": _merge_linked_items(outputs, "rules", ("description",))}
    rows: list[dict] = []
    seen: set[tuple[str, ...]] = set()
    for output in outputs:
        for row in output.get("rows", []):
            key = tuple(
                " ".join(str(row.get(field, "")).lower().split())
                for field in ("module", "test_item", "test_type", "related_requirement_id")
            )
            if key not in seen:
                seen.add(key)
                rows.append(row)
    return {"rows": rows}


def _source_coverage(stage00: dict, selected: set[str], source_ids: set[str]) -> list[dict]:
    coverage = []
    for item in stage00.get("source_coverage", []):
        if item["source_reference_id"] not in source_ids:
            continue
        requirement_ids = [value for value in item.get("requirement_ids", []) if value in selected]
        coverage.append({
            **item,
            "requirement_ids": requirement_ids,
            "no_requirement_reason": "" if requirement_ids else item.get("no_requirement_reason", ""),
        })
    return coverage


def _filter_linked(items: list[dict], selected: set[str]) -> list[dict]:
    filtered = []
    for item in items:
        requirement_ids = [value for value in item.get("requirement_ids", []) if value in selected]
        if requirement_ids:
            filtered.append({**item, "requirement_ids": requirement_ids})
    return filtered


def _unique_items(outputs: list[dict], key: str, id_key: str) -> list[dict]:
    values: list[dict] = []
    seen: set[str] = set()
    for output in outputs:
        for item in output.get(key, []):
            identifier = str(item.get(id_key, ""))
            if identifier not in seen:
                seen.add(identifier)
                values.append(item)
    return values


def _merge_linked_items(outputs: list[dict], collection: str, semantic_fields: tuple[str, ...]) -> list[dict]:
    values: list[dict] = []
    positions: dict[tuple[str, ...], int] = {}
    for output in outputs:
        for item in output.get(collection, []):
            key = tuple(" ".join(str(item.get(field, "")).lower().split()) for field in semantic_fields)
            if key not in positions:
                positions[key] = len(values)
                values.append(deepcopy(item))
                continue
            current = values[positions[key]]
            current["requirement_ids"] = list(dict.fromkeys([
                *current.get("requirement_ids", []), *item.get("requirement_ids", []),
            ]))
    return values


def _identifier(value: str) -> str:
    compact = "".join(character for character in value.upper() if character.isalnum())
    return compact[-12:] or hashlib.sha256(value.encode("utf-8")).hexdigest()[:8].upper()
