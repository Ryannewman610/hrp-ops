import json
from collections import Counter
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
MECH_PATH = ROOT / "outputs" / "mechanics" / "mechanics_index.json"
FORUM_PATH = ROOT / "outputs" / "forums" / "forum_claims.jsonl"
OUT_DIR = ROOT / "outputs" / "knowledge"
OUT_JSONL = OUT_DIR / "knowledge_index.jsonl"
OUT_SUMMARY = OUT_DIR / "KNOWLEDGE_SUMMARY.md"


def norm_confidence(value: str, default: str) -> str:
    v = (value or "").strip().lower()
    if v in {"high", "h"}:
        return "High"
    if v in {"med", "medium", "m"}:
        return "Med"
    if v in {"low", "l"}:
        return "Low"
    return default


def to_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_official() -> List[Dict[str, str]]:
    if not MECH_PATH.exists():
        return []
    try:
        data = json.loads(MECH_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out: List[Dict[str, str]] = []
    if not isinstance(data, list):
        return out
    for row in data:
        if not isinstance(row, dict):
            continue
        claim = to_text(row.get("claim"))
        if not claim:
            claim = to_text(row.get("snippet"))
        if not claim:
            continue
        out.append(
            {
                "source": "official",
                "topic": to_text(row.get("topic")) or "General",
                "claim": claim,
                "confidence": norm_confidence(to_text(row.get("confidence")), "High"),
                "source_url": to_text(row.get("source_url")),
                "source_file": str(MECH_PATH.relative_to(ROOT)).replace("\\", "/"),
                "author": "",
                "date": "",
            }
        )
    return out


def load_forum() -> List[Dict[str, str]]:
    if not FORUM_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for raw in FORUM_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        claim = to_text(row.get("claim"))
        if not claim:
            continue
        out.append(
            {
                "source": "forum",
                "topic": to_text(row.get("topic")) or "General forum intel",
                "claim": claim,
                "confidence": norm_confidence(to_text(row.get("confidence")), "Low"),
                "source_url": to_text(row.get("source_url")),
                "source_file": to_text(row.get("source_file")),
                "author": to_text(row.get("author")),
                "date": to_text(row.get("date")),
            }
        )
    return out


def write_jsonl(records: List[Dict[str, str]]) -> None:
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    OUT_JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(records: List[Dict[str, str]]) -> None:
    by_source = Counter(r["source"] for r in records)
    by_topic = Counter(r["topic"] for r in records)
    by_conf = Counter(r["confidence"] for r in records)

    lines = [
        "# Knowledge Summary",
        "",
        f"- Total records: {len(records)}",
        "",
        "## By Source",
    ]
    for k in sorted(by_source):
        lines.append(f"- {k}: {by_source[k]}")
    lines += ["", "## By Topic"]
    for k, v in sorted(by_topic.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {k}: {v}")
    lines += ["", "## By Confidence"]
    for k in ["High", "Med", "Low"]:
        lines.append(f"- {k}: {by_conf.get(k, 0)}")

    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = load_official() + load_forum()
    # Deterministic ordering: source, topic, claim
    records = sorted(records, key=lambda r: (r["source"], r["topic"], r["claim"]))
    write_jsonl(records)
    write_summary(records)
    print(f"Wrote {len(records)} records to {OUT_JSONL}")
    print(f"Summary: {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
