import json
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
MECH_DIR = ROOT / "docs" / "mechanics"
OUT_PATH = ROOT / "outputs" / "mechanics" / "mechanics_index.json"

REQUIRED_KEYS = ["topic", "claim", "source_url", "confidence", "snippet"]


def parse_block(block: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, val = line.split(":", 1)
        key_n = key.strip().lower().replace(" ", "_")
        val_n = val.strip()
        if key_n == "source_url":
            data["source_url"] = val_n
        elif key_n == "topic":
            data["topic"] = val_n
        elif key_n == "claim":
            data["claim"] = val_n
        elif key_n == "confidence":
            data["confidence"] = val_n
        elif key_n == "snippet":
            data["snippet"] = val_n.strip('"')
    return data


def validate_claim(data: Dict[str, str], source_file: Path) -> None:
    missing = [k for k in REQUIRED_KEYS if not data.get(k)]
    if missing:
        raise ValueError(f"{source_file}: missing keys {missing}")
    if data["confidence"] != "High":
        raise ValueError(f"{source_file}: confidence must be 'High' for all claims")
    if not data["source_url"].startswith("http"):
        raise ValueError(f"{source_file}: invalid source_url '{data['source_url']}'")
    words = [w for w in data["snippet"].split() if w.strip()]
    if len(words) > 25:
        raise ValueError(
            f"{source_file}: snippet exceeds 25 words ({len(words)}): {data['snippet']}"
        )


def parse_markdown_file(path: Path) -> List[Dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    claims: List[Dict[str, str]] = []
    for block in text.split("\n\n"):
        parsed = parse_block(block)
        if parsed:
            if any(k in parsed for k in ["topic", "claim", "source_url", "confidence", "snippet"]):
                validate_claim(parsed, path)
                claims.append({k: parsed[k] for k in REQUIRED_KEYS})
    return claims


def main() -> None:
    if not MECH_DIR.exists():
        raise FileNotFoundError(f"Mechanics directory not found: {MECH_DIR}")

    all_claims: List[Dict[str, str]] = []
    for md_path in sorted(MECH_DIR.glob("*.md")):
        all_claims.extend(parse_markdown_file(md_path))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(all_claims, indent=2), encoding="utf-8")
    print(f"Wrote {len(all_claims)} claims: {OUT_PATH}")


if __name__ == "__main__":
    main()
