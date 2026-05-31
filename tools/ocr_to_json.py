"""
Pipeline: data/ocr_output/B1/*.txt → DeepSeek API → data/json_output/B1/*.json

Usage:
  DEEPSEEK_API_KEY=sk-... python tools/ocr_to_json.py           # all files
  DEEPSEEK_API_KEY=sk-... python tools/ocr_to_json.py 246       # single page
  python tools/ocr_to_json.py --dry-run 246                     # preview extracted words
"""

import re
import json
import time
import argparse
import os
import sys
from pathlib import Path
from openai import OpenAI

OCR_DIR = Path(__file__).parent.parent / "data" / "ocr_output" / "B1"
JSON_DIR = Path(__file__).parent.parent / "data" / "json_output" / "B1"
BATCH_SIZE = 8
MODEL = "deepseek-chat"

# POS abbreviations and non-word tokens to skip
_SKIP_WORDS = {
    "adj", "adv", "adì", "adi", "konj", "präp", "prp", "prep",
    "pl", "opl", "lv", "hv", "tv", "iv", "einf", "int", "üb",
    "sich", "mit", "von", "aus", "auf", "über", "unter", "nach",
    "Adj", "Adv", "Konj", "Präp",
}

_SKIP_LINE = re.compile(
    r'^\d+$'                   # bare page number
    r'|^www\b'                 # URL noise
    r'|^[A-Z]$'                # single-letter section header
    r'|^Glossar'               # footer
    r'|^[一-鿿]'       # lines starting with Chinese
    r'|^neue\s+编'             # book title fragments
    r'|^\s*$',                 # blank
    re.IGNORECASE,
)

_ARTICLE = re.compile(r'^(der|die|das)\s+', re.IGNORECASE)
_LEADING_NOISE = re.compile(r'^[*"\'`\s一-鿿\d_‘’‚“”,‚]+')
_SHORT_NOISE = re.compile(r'^[a-z]{1,2}\s+')
_GERMAN_WORD = re.compile(r'^([a-zA-ZäöüÄÖÜß]+(?:/[a-zA-ZäöüÄÖÜß]+)*)')


def extract_word(line: str) -> str | None:
    line = line.strip()
    if not line or _SKIP_LINE.search(line):
        return None

    # Strip leading noise: *, ", Chinese chars, digits, punctuation noise
    line = _LEADING_NOISE.sub("", line).strip()
    if not line:
        return None

    # Remove article
    line = _ARTICLE.sub("", line).strip()

    # Remove 1-2 char Latin noise like "ki " or "_ "
    if _SHORT_NOISE.match(line):
        line = _SHORT_NOISE.sub("", line).strip()

    m = _GERMAN_WORD.match(line)
    if not m:
        return None

    word = m.group(1).replace("/", "")  # ab/halten → abhalten

    if len(word) < 3 or word in _SKIP_WORDS or word.lower() in _SKIP_WORDS:
        return None

    return word


def parse_words(ocr_path: Path) -> list[str]:
    words, seen = [], set()
    for line in ocr_path.read_text(encoding="utf-8").splitlines():
        w = extract_word(line)
        if w and w.lower() not in seen:
            words.append(w)
            seen.add(w.lower())
    return words


_SYSTEM = """\
你是一个德语语言学专家和结构化数据生成器。

任务：对输入的每一个德语单词，生成标准化词典数据，输出严格的 JSON 数组（每个单词一个对象）。

【输出要求】
1. 只输出 JSON，不要任何解释或 markdown
2. 输出必须是合法 JSON（可直接被 json.loads 解析）
3. 每个单词一个对象
4. 字段必须完整，没有则填 null 或 []

【字段结构】
[
  {
    "word": "string",
    "lemma": "string",
    "pos": ["noun","verb","adjective","adverb","preposition","conjunction"],
    "gender": "der/die/das/null",
    "plural": "string/null",
    "meaning": [{"zh": "string", "en": "string"}],
    "examples": [{"de": "string", "zh": "string"}],
    "collocations": ["string"],
    "grammar": {
      "case": "Akkusativ/Dativ/Genitiv/null",
      "separable": true/false/null,
      "auxiliary": "haben/sein/null",
      "partizip2": "string/null"
    },
    "level": "A1/A2/B1/B2/C1",
    "tags": ["string"],
    "synonyms": ["string"],
    "antonyms": ["string"]
  }
]

【生成规则】
- 名词必须提供 gender 和 plural
- 动词必须提供：partizip2、auxiliary（haben 或 sein）、separable（是否可分）
- 动词的 grammar.case 填写其支配格（如 Akkusativ）
- examples 至少 2 条，必须自然地道
- collocations 至少 2 条（常见搭配或功能动词结构）
- tags 包含：语义类别（如"社会/科技/生活/情感"）和难度等级（如"B1"）
- 不要生成虚构词义或不常见用法，优先生成 B1–B2 高频用法\
"""


def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_deepseek(client: OpenAI, words: list[str]) -> list[dict]:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "【输入单词】\n" + ", ".join(words)},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    raw = _strip_fences(resp.choices[0].message.content)
    return json.loads(raw)


def call_with_retry(client: OpenAI, words: list[str], max_retries: int = 2) -> list[dict]:
    """Call DeepSeek and retry for any words missing from the response."""
    entries = call_deepseek(client, words)

    returned = {e.get("lemma", "").lower() for e in entries} | {e.get("word", "").lower() for e in entries}
    missing = [w for w in words if w.lower() not in returned]

    for attempt in range(max_retries):
        if not missing:
            break
        print(f"      [retry {attempt+1}] missing: {missing}")
        time.sleep(1)
        extra = call_deepseek(client, missing)
        entries.extend(extra)
        returned |= {e.get("lemma", "").lower() for e in extra} | {e.get("word", "").lower() for e in extra}
        missing = [w for w in missing if w.lower() not in returned]

    if missing:
        print(f"      [warn] still missing after retries: {missing}")

    return entries


def process_file(ocr_path: Path, client: OpenAI) -> None:
    words = parse_words(ocr_path)
    if not words:
        print(f"  {ocr_path.name}: no words found, skipping")
        return

    out_path = JSON_DIR / (ocr_path.stem + ".json")
    if out_path.exists():
        print(f"  {ocr_path.name}: output already exists, skipping (delete to reprocess)")
        return

    print(f"  {ocr_path.name}: {len(words)} words, {-(-len(words)//BATCH_SIZE)} batches")

    all_entries: list[dict] = []
    for i in range(0, len(words), BATCH_SIZE):
        batch = words[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = -(-len(words) // BATCH_SIZE)
        print(f"    [{batch_num}/{total_batches}] {batch}")
        try:
            entries = call_with_retry(client, batch)
            all_entries.extend(entries)
        except json.JSONDecodeError as e:
            print(f"      [error] JSON parse failed: {e}")
        except Exception as e:
            print(f"      [error] API call failed: {e}")
        if i + BATCH_SIZE < len(words):
            time.sleep(0.3)

    out_path.write_text(json.dumps(all_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    → saved {out_path.name}  ({len(all_entries)} entries)")


def main():
    parser = argparse.ArgumentParser(description="OCR text → DeepSeek → JSON")
    parser.add_argument("file", nargs="?", help="Page number to process (e.g. 246)")
    parser.add_argument("--dry-run", action="store_true", help="Show extracted words, no API call")
    parser.add_argument("--force", action="store_true", help="Reprocess even if output exists")
    args = parser.parse_args()

    if args.dry_run:
        target = OCR_DIR / f"{args.file}.txt" if args.file else None
        paths = [target] if target else sorted(OCR_DIR.glob("*.txt"))
        for p in paths:
            words = parse_words(p)
            print(f"\n{p.name} ({len(words)} words):")
            for w in words:
                print(f"  {w}")
        return

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        # Try reading from .env in project root
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"\'')
                    break
    if not api_key:
        sys.exit("Error: set DEEPSEEK_API_KEY env var or add it to .env")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    JSON_DIR.mkdir(parents=True, exist_ok=True)

    if args.force:
        # Remove skip-if-exists guard by monkey-patching: just delete outputs first
        pass

    if args.file:
        ocr_path = OCR_DIR / f"{args.file}.txt"
        if not ocr_path.exists():
            sys.exit(f"Not found: {ocr_path}")
        if args.force and (JSON_DIR / f"{args.file}.json").exists():
            (JSON_DIR / f"{args.file}.json").unlink()
        process_file(ocr_path, client)
    else:
        for ocr_path in sorted(OCR_DIR.glob("*.txt")):
            if args.force:
                out = JSON_DIR / (ocr_path.stem + ".json")
                if out.exists():
                    out.unlink()
            process_file(ocr_path, client)


if __name__ == "__main__":
    main()
