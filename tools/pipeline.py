"""
Full pipeline: PDF or image folder → OCR text → DeepSeek JSON

Usage:
  python tools/pipeline.py data/A1.pdf               # PDF full pipeline
  python tools/pipeline.py data/pics/B2              # image folder full pipeline
  python tools/pipeline.py data/A1.pdf --ocr-only    # only PDF→images + OCR
  python tools/pipeline.py data/A1.pdf --json-only   # only JSON (OCR already done)
  python tools/pipeline.py data/A1.pdf --dry-run     # preview words, no API call
  python tools/pipeline.py data/A1.pdf --force       # reprocess existing outputs

Output layout (name = PDF stem or folder name):
  data/pics/<name>/*.png          ← PDF pages (only when input is PDF)
  data/ocr_output/<name>/*.txt
  data/json_output/<name>/*.json
"""

import re
import json
import time
import argparse
import os
import subprocess
import sys
from pathlib import Path

# ── paths ──────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
TESSDATA = "/opt/homebrew/share/tessdata/"
LANG = "deu+chi_sim"
BATCH_SIZE = 8
MODEL = "deepseek-chat"


# ── step 0: PDF → images ───────────────────────────────────────────────────────

def pdf_to_images(pdf_path: Path, pics_dir: Path, dpi: int = 200, force: bool = False) -> None:
    pics_dir.mkdir(parents=True, exist_ok=True)
    existing = list(pics_dir.glob("*.png"))
    if existing and not force:
        print(f"\n[PDF] {len(existing)} pages already extracted, skipping (--force to redo)")
        return

    print(f"\n[PDF] Extracting pages from {pdf_path.name} → {pics_dir}  (dpi={dpi})")
    prefix = str(pics_dir / pdf_path.stem)
    result = subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), prefix],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"pdftoppm failed: {result.stderr}")

    pages = sorted(pics_dir.glob("*.png"))
    # Rename: A1-01.png → 1.png, A1-02.png → 2.png, ...
    for p in pages:
        parts = p.stem.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            new_name = p.with_name(f"{int(parts[1])}.png")
            p.rename(new_name)

    pages = sorted(pics_dir.glob("*.png"))
    print(f"  Extracted {len(pages)} pages")


# ── step 1: OCR ────────────────────────────────────────────────────────────────

def run_ocr(pics_dir: Path, ocr_dir: Path, force: bool = False) -> list[Path]:
    import tesserocr
    from PIL import Image

    images = sorted(pics_dir.glob("*.png")) + sorted(pics_dir.glob("*.jpg"))
    if not images:
        sys.exit(f"No PNG/JPG images found in {pics_dir}")

    ocr_dir.mkdir(parents=True, exist_ok=True)
    results = []

    print(f"\n[OCR] {len(images)} images → {ocr_dir}")
    with tesserocr.PyTessBaseAPI(path=TESSDATA, lang=LANG) as api:
        for img_path in images:
            out_path = ocr_dir / (img_path.stem + ".txt")
            if out_path.exists() and not force:
                print(f"  {img_path.name}: already done, skipping")
                results.append(out_path)
                continue
            img = Image.open(img_path)
            api.SetImage(img)
            text = api.GetUTF8Text()
            out_path.write_text(text, encoding="utf-8")
            print(f"  {img_path.name} → {out_path.name}  ({text.count(chr(10))} lines)")
            results.append(out_path)

    return results


# ── step 2: word extraction ────────────────────────────────────────────────────

_SKIP_WORDS = {
    "adj", "adv", "adì", "adi", "konj", "präp", "prp", "prep",
    "pl", "opl", "lv", "hv", "tv", "iv", "einf", "int", "üb",
    "sich", "mit", "von", "aus", "auf", "über", "unter", "nach",
}

_SKIP_LINE = re.compile(
    r'^\d+$'
    r'|^www\b'
    r'|^[A-Z]$'
    r'|^Glossar'
    r'|^[一-鿿]'
    r'|^\s*$',
    re.IGNORECASE,
)

_ARTICLE = re.compile(r'^(der|die|das)\s+', re.IGNORECASE)
_LEADING_NOISE = re.compile(r'^[*"\'`\s一-鿿\d_‘’‚“”,‚]+')
_SHORT_NOISE = re.compile(r'^[a-z]{1,2}\s+')
_GERMAN_WORD = re.compile(r'^([a-zA-ZäöüÄÖÜß]+(?:/[a-zA-ZäöüÄÖÜß]+)*)')


def _extract_word(line: str) -> str | None:
    line = line.strip()
    if not line or _SKIP_LINE.search(line):
        return None

    line = _LEADING_NOISE.sub("", line).strip()
    if not line:
        return None

    line = _ARTICLE.sub("", line).strip()

    if _SHORT_NOISE.match(line):
        line = _SHORT_NOISE.sub("", line).strip()

    m = _GERMAN_WORD.match(line)
    if not m:
        return None

    word = m.group(1).replace("/", "")

    if len(word) < 3 or word.lower() in _SKIP_WORDS:
        return None

    return word


def parse_words(ocr_path: Path) -> list[str]:
    words, seen = [], set()
    for line in ocr_path.read_text(encoding="utf-8").splitlines():
        w = _extract_word(line)
        if w and w.lower() not in seen:
            words.append(w)
            seen.add(w.lower())
    return words


# ── step 3: DeepSeek JSON ──────────────────────────────────────────────────────

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


def _call_api(client, words: list[str]) -> list[dict]:
    from openai import OpenAI  # imported here so --ocr-only doesn't require it
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": "【输入单词】\n" + ", ".join(words)},
        ],
        temperature=0.3,
        max_tokens=4096,
    )
    return json.loads(_strip_fences(resp.choices[0].message.content))


def _call_with_retry(client, words: list[str], max_retries: int = 2) -> list[dict]:
    entries = _call_api(client, words)
    returned = {e.get("lemma", "").lower() for e in entries} | {e.get("word", "").lower() for e in entries}
    missing = [w for w in words if w.lower() not in returned]

    for attempt in range(max_retries):
        if not missing:
            break
        print(f"      [retry {attempt+1}] missing: {missing}")
        time.sleep(1)
        extra = _call_api(client, missing)
        entries.extend(extra)
        returned |= {e.get("lemma", "").lower() for e in extra} | {e.get("word", "").lower() for e in extra}
        missing = [w for w in missing if w.lower() not in returned]

    if missing:
        print(f"      [warn] still missing after retries: {missing}")

    return entries


def run_json(ocr_dir: Path, json_dir: Path, client, force: bool = False) -> None:
    ocr_files = sorted(ocr_dir.glob("*.txt"))
    if not ocr_files:
        sys.exit(f"No OCR text files found in {ocr_dir}")

    json_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[JSON] {len(ocr_files)} files → {json_dir}")

    for ocr_path in ocr_files:
        out_path = json_dir / (ocr_path.stem + ".json")
        if out_path.exists() and not force:
            print(f"  {ocr_path.name}: already done, skipping")
            continue

        words = parse_words(ocr_path)
        if not words:
            print(f"  {ocr_path.name}: no words extracted, skipping")
            continue

        total_batches = -(-len(words) // BATCH_SIZE)
        print(f"  {ocr_path.name}: {len(words)} words, {total_batches} batches")

        all_entries: list[dict] = []
        for i in range(0, len(words), BATCH_SIZE):
            batch = words[i : i + BATCH_SIZE]
            print(f"    [{i//BATCH_SIZE+1}/{total_batches}] {batch}")
            try:
                entries = _call_with_retry(client, batch)
                all_entries.extend(entries)
            except json.JSONDecodeError as e:
                print(f"      [error] JSON parse failed: {e}")
            except Exception as e:
                print(f"      [error] API error: {e}")
            if i + BATCH_SIZE < len(words):
                time.sleep(0.3)

        out_path.write_text(json.dumps(all_entries, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    → {out_path.name}  ({len(all_entries)} entries)")


# ── CLI ────────────────────────────────────────────────────────────────────────

def load_api_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        env_file = ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("\"'")
                    break
    if not key:
        sys.exit("Error: set DEEPSEEK_API_KEY in env or .env file")
    return key


def main():
    parser = argparse.ArgumentParser(description="PDF or image folder → OCR → DeepSeek JSON")
    parser.add_argument("input", help="PDF file or image folder (e.g. data/A1.pdf or data/pics/B2)")
    parser.add_argument("--ocr-only", action="store_true", help="Run PDF→images + OCR only, skip JSON")
    parser.add_argument("--json-only", action="store_true", help="Run JSON step only (OCR already done)")
    parser.add_argument("--dry-run", action="store_true", help="Preview extracted words, no API call")
    parser.add_argument("--force", action="store_true", help="Reprocess existing outputs")
    parser.add_argument("--dpi", type=int, default=200, help="DPI for PDF page rendering (default: 200)")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        sys.exit(f"Not found: {input_path}")

    is_pdf = input_path.suffix.lower() == ".pdf"
    name = input_path.stem  # "A1" from A1.pdf, or "B2" from pics/B2
    pics_dir = ROOT / "data" / "pics" / name
    ocr_dir  = ROOT / "data" / "ocr_output" / name
    json_dir = ROOT / "data" / "json_output" / name

    if not is_pdf:
        pics_dir = input_path  # user passed the folder directly

    print(f"Input:  {input_path}")
    if is_pdf:
        print(f"Images: {pics_dir}")
    print(f"OCR:    {ocr_dir}")
    print(f"JSON:   {json_dir}")

    # dry-run: just show extracted words from existing OCR output
    if args.dry_run:
        if not ocr_dir.exists():
            sys.exit(f"OCR output not found: {ocr_dir}  (run without --dry-run first)")
        for p in sorted(ocr_dir.glob("*.txt")):
            words = parse_words(p)
            print(f"\n{p.name} ({len(words)} words):")
            for w in words:
                print(f"  {w}")
        return

    # step 0: PDF → images (only when input is a PDF)
    if is_pdf and not args.json_only:
        pdf_to_images(input_path, pics_dir, dpi=args.dpi, force=args.force)

    # step 1: OCR
    if not args.json_only:
        run_ocr(pics_dir, ocr_dir, force=args.force)

    # step 2: DeepSeek JSON
    if not args.ocr_only:
        from openai import OpenAI
        client = OpenAI(api_key=load_api_key(), base_url="https://api.deepseek.com")
        run_json(ocr_dir, json_dir, client, force=args.force)

    print("\nDone.")


if __name__ == "__main__":
    main()
