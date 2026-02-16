import argparse
import json
import re
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "outputs" / "knowledge" / "knowledge_index.jsonl"


def load_records() -> List[Dict[str, str]]:
    if not INDEX_PATH.exists():
        return []
    out: List[Dict[str, str]] = []
    for raw in INDEX_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def tokenize(text: str) -> List[str]:
    return [t for t in re.findall(r"[A-Za-z0-9_]+", text.lower()) if t]


def score_record(rec: Dict[str, str], terms: List[str]) -> int:
    topic = str(rec.get("topic", "")).lower()
    claim = str(rec.get("claim", "")).lower()
    joined = f"{topic} {claim}"
    score = 0
    for term in terms:
        if term in claim:
            score += 5
        if term in topic:
            score += 3
        # token exact match bonus
        if term in tokenize(joined):
            score += 2
    return score


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Query knowledge index with simple keyword scoring.")
    ap.add_argument("query", help="Keyword query, e.g. consistency")
    ap.add_argument("--source", choices=["official", "forum", "all"], default="all")
    ap.add_argument("--limit", type=int, default=15)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    records = load_records()
    if not records:
        print(f"No records found at {INDEX_PATH}. Run: py scripts/13_build_knowledge_index.py")
        return

    terms = tokenize(args.query)
    if not terms:
        print("Query produced no searchable terms.")
        return

    source_filter = args.source
    scored = []
    for i, rec in enumerate(records):
        src = str(rec.get("source", "")).lower()
        if source_filter != "all" and src != source_filter:
            continue
        s = score_record(rec, terms)
        if s > 0:
            scored.append((s, i, rec))

    if not scored:
        print("No matches.")
        return

    scored.sort(key=lambda x: (-x[0], x[1]))
    limit = max(1, args.limit)
    for rank, (s, _, rec) in enumerate(scored[:limit], start=1):
        print(f"{rank}. [score={s}] [{rec.get('source','')}] [{rec.get('confidence','')}] {rec.get('topic','')}")
        print(f"   Claim: {rec.get('claim','')}")
        src_url = rec.get("source_url", "")
        src_file = rec.get("source_file", "")
        if src_url:
            print(f"   URL: {src_url}")
        if src_file:
            print(f"   File: {src_file}")


if __name__ == "__main__":
    main()
