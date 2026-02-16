import json
import re
from collections import defaultdict
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = ROOT / "inputs" / "forums" / "raw"
OUTPUT_DIR = ROOT / "outputs" / "forums"
JSONL_PATH = OUTPUT_DIR / "forum_claims.jsonl"
SUMMARY_PATH = OUTPUT_DIR / "FORUM_CLAIMS_SUMMARY.md"
SUPPORTED_EXTS = {".txt", ".md", ".html"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"script", "style"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in {"script", "style"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag in {"p", "br", "div", "li", "tr", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self._skip_depth == 0 and data.strip():
            self._parts.append(data.strip() + " ")

    def get_text(self) -> str:
        return unescape("".join(self._parts))


def read_file_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".html":
        parser = _HTMLTextExtractor()
        parser.feed(raw)
        return parser.get_text()
    return raw


def parse_optional_headers(text: str) -> Tuple[str, str, str]:
    source_url = ""
    author = ""
    date = ""
    for raw_line in text.splitlines()[:20]:
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("url:") and not source_url:
            source_url = line.split(":", 1)[1].strip()
        elif line.lower().startswith(("author:", "posted by:", "user:")) and not author:
            author = line.split(":", 1)[1].strip()
        elif line.lower().startswith(("date:", "posted:")) and not date:
            date = line.split(":", 1)[1].strip()
    return source_url, author, date


def classify_topic(claim: str) -> str:
    c = claim.lower()
    if any(k in c for k in ["timed work", "start code", "pace", "effort", "workout"]):
        return "Timed Works"
    if any(k in c for k in ["train", "training mode", "racing mode", "rest mode"]):
        return "Training"
    if any(k in c for k in ["consistency"]):
        return "Consistency"
    if any(k in c for k in ["scratch", "eligible", "nomination", "entry", "post time"]):
        return "Race eligibility & scratches"
    if any(k in c for k in ["ship", "shipping", "relocat", "move track", "transit"]):
        return "Shipping/relocation"
    if any(k in c for k in ["breed", "breeding", "foal", "stallion", "mare"]):
        return "Breeding/foals"
    if any(k in c for k in ["blinkers", "lasix", "bute", "accessor", "gelded", "shadow roll"]):
        return "Accessories/adds"
    if any(k in c for k in ["weight", "handicap", "allowance"]):
        return "Handicapping weight rules"
    return "General forum intel"


def sentence_candidates(text: str) -> List[str]:
    # Remove obvious metadata lines from candidates.
    filtered_lines: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith(("url:", "author:", "posted by:", "user:", "date:", "posted:")):
            continue
        if len(line) < 20:
            continue
        filtered_lines.append(line)

    base_text = " ".join(filtered_lines)
    pieces = re.split(r"(?<=[.!?])\s+", base_text)
    out: List[str] = []
    seen = set()
    for p in pieces:
        claim = re.sub(r"\s+", " ", p).strip(" -\t")
        if len(claim.split()) < 6:
            continue
        if len(claim) > 400:
            continue
        key = claim.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(claim)
    return out


def parse_claims_from_file(path: Path) -> List[Dict[str, str]]:
    text = read_file_text(path)
    source_url, author, date = parse_optional_headers(text)
    claims: List[Dict[str, str]] = []
    for claim_text in sentence_candidates(text):
        claims.append(
            {
                "topic": classify_topic(claim_text),
                "claim": claim_text,
                "source_url": source_url,
                "source_file": str(path.relative_to(ROOT)).replace("\\", "/"),
                "author": author,
                "date": date,
                "confidence": "Low",
            }
        )
    return claims


def write_jsonl(claims: List[Dict[str, str]]) -> None:
    lines = [json.dumps(c, ensure_ascii=False) for c in claims]
    JSONL_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(claims: List[Dict[str, str]]) -> None:
    lines: List[str] = ["# Forum Claims Summary", ""]
    if not claims:
        lines.append("- No claims parsed from `inputs/forums/raw/`.")
        SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for c in claims:
        grouped[c["topic"]].append(c)

    for topic in sorted(grouped.keys()):
        lines.append(f"## {topic}")
        lines.append("")
        for c in grouped[topic]:
            src = c["source_url"] if c["source_url"] else "(no URL provided)"
            author = c["author"] if c["author"] else "(unknown)"
            date = c["date"] if c["date"] else "(unknown)"
            lines.append(f"- Claim: {c['claim']}")
            lines.append(f"  - Source: {src}")
            lines.append(f"  - File: `{c['source_file']}`")
            lines.append(f"  - Author: {author}")
            lines.append(f"  - Date: {date}")
            lines.append(f"  - Confidence: {c['confidence']}")
        lines.append("")

    SUMMARY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p
        for p in INPUT_DIR.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )

    all_claims: List[Dict[str, str]] = []
    for path in files:
        all_claims.extend(parse_claims_from_file(path))

    write_jsonl(all_claims)
    write_summary(all_claims)
    print(f"Parsed files: {len(files)}")
    print(f"Claims written: {len(all_claims)}")
    print(f"JSONL: {JSONL_PATH}")
    print(f"Summary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
