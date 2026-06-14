from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import random
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock, Thread
from typing import Iterable

from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Select, delete, func, or_, select, text
from sqlalchemy.orm import Session, selectinload
from pydantic import ValidationError

from .db import Base, SessionLocal, engine, get_session
from .models import Collocation, EntryForm, EntryImage, EntrySimilarity, EntryTag, ExampleSentence, IrregularVerb, Meaning, ReadingBook, ReadingPage, ReadingPageMessage, VocabularyEntry, WordFrequency, WordMastery, WordMasteryEvent
from .routers.noun_gender import router as noun_gender_router
from .serializers import entry_image_url, entry_query, serialize_entry, serialize_frequency, serialize_mastery, serialize_mastery_event

from .schemas import (
    EntryCreate,
    EntryDraftRequest,
    FormPayload,
    TagPayload,
    EntryImageCandidate,
    EntryImageSelectRequest,
    EntryListResponse,
    EntryNotesUpdate,
    EntryResolveRequest,
    EntryResolveResponse,
    EntryResponse,
    EntryUpdate,
    ImportResult,
    IrregularVerbListResponse,
    IrregularVerbQuizItem,
    IrregularVerbResponse,
    ReadingBookResponse,
    ReadingMessageResponse,
    ReadingPageAskRequest,
    ReadingPageAskResponse,
    ReadingPageNotesUpdate,
    ReadingPageTextUpdate,
    ReadingPageResponse,
    SimilarEntryResponse,
    WordMasteryReviewRequest,
    WordMasteryReviewResponse,
    WordFrequencyResponse,
)


BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
MEDIA_DIR = BASE_DIR / "public" / "media"
ENTRY_IMAGE_DIR = MEDIA_DIR / "entry-images"
BOOKS_DIR = BASE_DIR / "data" / "books"
READING_PAGE_IMAGE_DIR = MEDIA_DIR / "reading-pages"
ENTRY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
READING_PAGE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


MASTERY_RATING_DELTAS = {
    "again": -2,
    "hard": 1,
    "easy": 3,
    "simple": 5,
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(BASE_DIR / ".env")

app = FastAPI(title="Deutsche Study API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")
app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")
app.include_router(noun_gender_router)


TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
WRITE_LOCK = Lock()
FREQUENCY_BACKFILL_LOCK = Lock()
FREQUENCY_BACKFILL_JOB = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "total_target": 0,
    "attempted_count": 0,
    "success_count": 0,
    "no_result_count": 0,
    "failed_count": 0,
    "remaining_count": 0,
    "last_entry_id": None,
    "last_lemma": None,
    "error": None,
}
MEANING_BACKFILL_LOCK = Lock()
MEANING_BACKFILL_JOB = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "total_target": 0,
    "attempted_count": 0,
    "updated_count": 0,
    "failed_count": 0,
    "remaining_count": 0,
    "last_entry_id": None,
    "last_lemma": None,
    "error": None,
}
CHINESE_QUERY_EXPANSION_CACHE: dict[str, list[str]] = {}
COMMON_CHINESE_QUERY_SYNONYMS = {
    "买": ["购买", "采购"],
    "购买": ["买", "采购"],
    "卖": ["出售", "销售"],
    "出售": ["卖", "销售"],
    "房子": ["房屋", "住宅", "住所", "家"],
    "住所": ["住处", "居住地", "家", "住宅"],
    "家": ["住所", "住处", "住宅"],
    "工作": ["职业", "职位", "劳动"],
    "职业": ["工作", "职位"],
    "开心": ["高兴", "快乐", "愉快"],
    "高兴": ["开心", "快乐", "愉快"],
    "难过": ["悲伤", "伤心"],
    "悲伤": ["难过", "伤心"],
    "车": ["汽车", "车辆"],
    "汽车": ["车", "车辆"],
    "说": ["讲", "谈", "表达"],
    "讲": ["说", "谈", "表达"],
    "看": ["观看", "观察"],
    "吃": ["食用", "进食"],
    "医生": ["医师"],
    "学生": ["学员"],
    "老师": ["教师"],
}
FREQUENCY_IMPORTANCE_DIMENSIONS = [
    {"name": "重要性：极高", "value": "5", "scores": [5]},
    {"name": "重要性：高", "value": "4", "scores": [4]},
    {"name": "重要性：中", "value": "3", "scores": [3]},
    {"name": "重要性：低", "value": "2", "scores": [2]},
    {"name": "重要性：很低", "value": "very_low", "scores": [0, 1]},
]
def normalize_lemma(value: str) -> str:
    return " ".join(value.strip().lower().split())


def clean_surface_form(value: str) -> str:
    cleaned = re.sub(r"^[\"'„“”‚‘’()\[\]{}<>«»]+|[\"'„“”‚‘’()\[\]{}<>«»,.;:!?]+$", "", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def unique_values(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        cleaned = normalize_lemma(clean_surface_form(value))
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def german_surface_candidates(value: str) -> list[str]:
    base = normalize_lemma(clean_surface_form(value))
    if not base:
        return []
    candidates = [base]
    if " " in base:
        candidates.append(re.sub(r"^(der|die|das|den|dem|des|ein|eine|einen|einem|eines)\s+", "", base))

    simple = candidates[-1]
    suffix_replacements = [
        ("test", "ten"),
        ("tet", "ten"),
        ("ten", "en"),
        ("te", "en"),
        ("est", "en"),
        ("st", "en"),
        ("et", "en"),
        ("t", "en"),
        ("ern", "er"),
        ("en", ""),
        ("ern", ""),
        ("er", ""),
        ("es", ""),
        ("em", ""),
        ("e", ""),
        ("n", ""),
        ("s", ""),
    ]
    for suffix, replacement in suffix_replacements:
        if simple.endswith(suffix) and len(simple) > len(suffix) + 2:
            stem = simple[: -len(suffix)]
            candidates.append(stem + replacement)
            if replacement == "":
                candidates.append(stem + "en")
    if simple.startswith("ge") and len(simple) > 5:
        inner = simple[2:]
        if inner.endswith("t") and len(inner) > 3:
            candidates.append(inner[:-1] + "en")
        if inner.endswith("en") and len(inner) > 4:
            candidates.append(inner)

    expanded = []
    for candidate in candidates:
        expanded.append(candidate)
        expanded.append(fold_german_umlauts(candidate))
        if "ä" in candidate:
            expanded.append(candidate.replace("ä", "a"))
        if "ö" in candidate:
            expanded.append(candidate.replace("ö", "o"))
        if "ü" in candidate:
            expanded.append(candidate.replace("ü", "u"))
    return unique_values(expanded)


def find_entry_by_normalized_candidates(session: Session, candidates: list[str]) -> VocabularyEntry | None:
    candidates = unique_values(candidates)
    if not candidates:
        return None
    rows = session.scalars(entry_query().where(VocabularyEntry.normalized_lemma.in_(candidates))).unique().all()
    by_normalized = {entry.normalized_lemma: entry for entry in rows}
    for candidate in candidates:
        if candidate in by_normalized:
            return by_normalized[candidate]

    folded_candidates = {fold_german_umlauts(candidate) for candidate in candidates}
    if folded_candidates:
        id_rows = session.execute(select(VocabularyEntry.id, VocabularyEntry.normalized_lemma)).all()
        for entry_id, normalized in id_rows:
            if fold_german_umlauts(normalized) in folded_candidates:
                return session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    return None


def resolve_existing_entry_from_surface(
    session: Session,
    value: str,
) -> tuple[VocabularyEntry | None, str | None, str | None]:
    surface = normalize_lemma(clean_surface_form(value))
    if not surface:
        return None, None, None

    entry = find_entry_by_normalized_candidates(session, [surface])
    if entry:
        return entry, entry.lemma, "exact"

    form_rows = session.execute(
        select(EntryForm.entry_id, EntryForm.label)
        .where(func.lower(EntryForm.value) == surface)
        .limit(5)
    ).all()
    if form_rows:
        entry = session.scalars(entry_query().where(VocabularyEntry.id == form_rows[0][0])).first()
        if entry:
            return entry, entry.lemma, f"form:{form_rows[0][1]}"

    irregular = session.scalars(
        select(IrregularVerb).where(
            or_(
                func.lower(IrregularVerb.infinitive) == surface,
                func.lower(IrregularVerb.present) == surface,
                func.lower(IrregularVerb.preterite) == surface,
                func.lower(IrregularVerb.participle_ii) == surface,
                func.lower(IrregularVerb.imperative) == surface,
                func.lower(IrregularVerb.subjunctive_ii) == surface,
            )
        )
    ).first()
    if irregular:
        entry = find_entry_by_normalized_candidates(session, [irregular.infinitive])
        if entry:
            return entry, irregular.infinitive, "irregular_verb"
        return None, irregular.infinitive, "irregular_verb"

    candidates = german_surface_candidates(surface)
    entry = find_entry_by_normalized_candidates(session, candidates)
    if entry:
        return entry, entry.lemma, "suffix_guess"
    return None, candidates[0] if candidates else surface, None


def parse_frequency_importance_values(values: list[str]) -> list[int]:
    parsed: list[int] = []
    dimension_scores = {
        str(dimension["value"]): list(dimension["scores"])
        for dimension in FREQUENCY_IMPORTANCE_DIMENSIONS
    }
    dimension_scores.update({
        str(dimension["name"]): list(dimension["scores"])
        for dimension in FREQUENCY_IMPORTANCE_DIMENSIONS
    })
    short_labels = {"极高": [5], "高": [4], "中": [3], "低": [2], "很低": [0, 1]}
    for raw_value in values:
        value = str(raw_value).strip()
        if not value:
            continue
        if value in dimension_scores:
            parsed.extend(dimension_scores[value])
            continue
        if value.isdigit():
            parsed.append(int(value))
            continue
        if value in short_labels:
            parsed.extend(short_labels[value])
    return list(dict.fromkeys(parsed))


def fold_german_umlauts(value: str | None) -> str:
    folded = (value or "").lower()
    replacements = {
        "ä": "a",
        "ö": "o",
        "ü": "u",
        "ß": "ss",
        "Ä": "a",
        "Ö": "o",
        "Ü": "u",
    }
    for source, target in replacements.items():
        folded = folded.replace(source, target)
    return " ".join(folded.split())


def strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    text_value = re.sub(r"<[^>]+>", "", value)
    text_value = re.sub(r"\s+", " ", text_value).strip()
    return text_value or None


def mastery_level_for_score(score: int) -> str:
    if score <= 0:
        return "new / weak"
    if score <= 5:
        return "difficult"
    if score <= 15:
        return "familiar"
    if score <= 30:
        return "known"
    return "stable"


def safe_reading_slug(value: str) -> str:
    slug = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-")
    return slug or "book"


def pdf_page_count(path: Path) -> int:
    try:
        result = subprocess.run(
            ["pdfinfo", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return 0
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, flags=re.MULTILINE)
    return int(match.group(1)) if match else 0


def ensure_reading_books(session: Session) -> None:
    BOOKS_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_path in sorted(BOOKS_DIR.glob("*.pdf")):
        relative_path = str(pdf_path.relative_to(BASE_DIR))
        book = session.scalar(select(ReadingBook).where(ReadingBook.file_path == relative_path))
        page_count = pdf_page_count(pdf_path)
        if not book:
            book = ReadingBook(
                title=pdf_path.stem,
                file_path=relative_path,
                page_count=page_count,
                status="ready" if page_count else "needs_check",
            )
            session.add(book)
            session.flush()
        else:
            book.title = book.title or pdf_path.stem
            book.page_count = page_count or book.page_count
            book.status = "ready" if book.page_count else "needs_check"
        existing_pages = {
            row[0]
            for row in session.execute(select(ReadingPage.page_number).where(ReadingPage.book_id == book.id)).all()
        }
        for page_number in range(1, (book.page_count or 0) + 1):
            if page_number not in existing_pages:
                session.add(ReadingPage(book_id=book.id, page_number=page_number, status="new"))
    session.commit()


def reading_book_path(book: ReadingBook) -> Path:
    path = (BASE_DIR / book.file_path).resolve()
    if not path.is_file() or BOOKS_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="书籍文件不存在")
    return path


def reading_page_image_url(image_path: str | None) -> str | None:
    if not image_path:
        return None
    return f"/media/{image_path.lstrip('/')}"


def serialize_reading_message(message: ReadingPageMessage) -> ReadingMessageResponse:
    return ReadingMessageResponse(
        id=message.id,
        page_id=message.page_id,
        role=message.role,
        content=message.content,
        created_at=message.created_at.isoformat(),
    )


def serialize_reading_book(book: ReadingBook) -> ReadingBookResponse:
    return ReadingBookResponse(
        id=book.id,
        title=book.title,
        file_path=book.file_path,
        page_count=book.page_count,
        status=book.status,
        created_at=book.created_at.isoformat() if book.created_at else None,
        updated_at=book.updated_at.isoformat() if book.updated_at else None,
    )


def serialize_reading_page(page: ReadingPage) -> ReadingPageResponse:
    return ReadingPageResponse(
        id=page.id,
        book_id=page.book_id,
        page_number=page.page_number,
        image_url=reading_page_image_url(page.image_path),
        ocr_text=page.ocr_text,
        translation_zh=page.translation_zh,
        keywords=page.keywords or [],
        grammar_notes=page.grammar_notes,
        notes=page.notes,
        status=page.status,
        messages=[serialize_reading_message(message) for message in page.messages],
    )


def render_reading_page_image(book: ReadingBook, page: ReadingPage) -> str:
    if page.image_path and (MEDIA_DIR / page.image_path).exists():
        return page.image_path
    pdf_path = reading_book_path(book)
    book_dir = READING_PAGE_IMAGE_DIR / f"{book.id}-{safe_reading_slug(book.title)}"
    book_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = book_dir / f"page-{page.page_number:03d}"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page.page_number),
            "-l",
            str(page.page_number),
            "-singlefile",
            "-r",
            "220",
            "-png",
            str(pdf_path),
            str(output_prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    )
    image_file = output_prefix.with_suffix(".png")
    relative_path = str(image_file.relative_to(MEDIA_DIR))
    page.image_path = relative_path
    return relative_path


def extract_reading_page_text(book: ReadingBook, page: ReadingPage) -> str:
    pdf_path = reading_book_path(book)
    temp_text = Path("/private/tmp") / f"reading-page-{book.id}-{page.page_number}.txt"
    try:
        subprocess.run(
            [
                "pdftotext",
                "-f",
                str(page.page_number),
                "-l",
                str(page.page_number),
                "-layout",
                str(pdf_path),
                str(temp_text),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        text_value = temp_text.read_text(encoding="utf-8", errors="ignore").strip()
        text_value = re.sub(r"\n{3,}", "\n\n", text_value)
        if len(text_value) >= 80:
            return text_value
    except Exception:
        pass

    image_path = render_reading_page_image(book, page)
    image_file = MEDIA_DIR / image_path
    ocr_prefix = Path("/private/tmp") / f"reading-page-ocr-{book.id}-{page.page_number}"
    subprocess.run(
        ["tesseract", str(image_file), str(ocr_prefix), "-l", "deu+eng", "--psm", "6"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    text_value = ocr_prefix.with_suffix(".txt").read_text(encoding="utf-8", errors="ignore").strip()
    return re.sub(r"\n{3,}", "\n\n", text_value)


def prepare_reading_page(session: Session, page: ReadingPage) -> ReadingPage:
    book = session.get(ReadingBook, page.book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    render_reading_page_image(book, page)
    if not page.ocr_text:
        page.ocr_text = extract_reading_page_text(book, page)
    page.status = "ocr_ready" if page.ocr_text else "image_ready"
    session.add(page)
    session.commit()
    session.refresh(page)
    return page


def generate_reading_page_deepseek(page: ReadingPage) -> ReadingPage:
    if not page.ocr_text:
        raise HTTPException(status_code=400, detail="请先 OCR 当前页")
    system_prompt = (
        "你是严谨的德语精读老师。只返回 JSON，不要 Markdown。"
        "字段必须是 translation_zh, keywords, grammar_notes。"
        "translation_zh 必须是中德对照文本，不是纯中文整段翻译。"
        "keywords 是数组，每项包含 term, meaning_zh, note。"
    )
    user_prompt = f"""
请处理下面这一页德语阅读材料：

页码: {page.page_number}

德语原文/OCR:
{page.ocr_text}

要求：
1. translation_zh 生成“中德对照”格式：保留德语标题/条目/句子，再紧跟对应中文译文。
   - 如果是目录页，尽量按条目输出：德语条目 + 中文译文 + 页码。
   - 短条目可放在同一行，例如：Vorwort  前言    5
   - 长条目可分两行：先德语原文，下一行中文译文，再保留页码。
   - 保留章节编号、页码、重要符号；不要把全页先德语后中文分成两大块。
   - OCR 明显错误可轻微修正，但不要臆造原文没有的信息。
2. keywords 选 8-18 个关键词/短语，解释中文含义和在本页中的用法。
3. grammar_notes 用中文解释本页重要语法、句式、从句、时态或固定搭配。
"""
    try:
        data = call_deepseek_json(system_prompt, user_prompt, max_tokens=3600, timeout=120)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    page.translation_zh = optional_text(data.get("translation_zh"))
    keywords = data.get("keywords") if isinstance(data.get("keywords"), list) else []
    page.keywords = [
        {
            "term": str(item.get("term", "")).strip(),
            "meaning_zh": str(item.get("meaning_zh", "")).strip(),
            "note": str(item.get("note", "")).strip(),
        }
        for item in keywords
        if isinstance(item, dict) and str(item.get("term", "")).strip()
    ]
    page.grammar_notes = optional_text(data.get("grammar_notes"))
    page.status = "deepseek_ready"
    return page


def clean_image_query(entry: VocabularyEntry) -> str:
    cached = (entry.extra_data or {}).get("image_search_query") if isinstance(entry.extra_data, dict) else None
    if cached:
        return str(cached)
    lemma = re.sub(r"^(der|die|das)\s+", "", entry.lemma.strip(), flags=re.IGNORECASE)
    if entry.part_of_speech == "noun":
        return lemma
    return lemma


ABSTRACT_HINTS = {
    "abschaffung", "ersatz", "steuer", "steuern", "freiheit", "entscheidung", "möglichkeit",
    "entwicklung", "beziehung", "bedeutung", "erfahrung", "verantwortung", "gesellschaft",
    "politik", "wirtschaft", "bildung", "zeit", "problem", "idee", "angst", "liebe",
    "recht", "pflicht", "chance", "grund", "folge", "wirkung", "ursache", "änderung",
    "klang", "karriere", "kandidatur", "kandidat", "bewerber", "person", "mensch",
    "rolle", "status", "prozess", "vorgang", "zustand", "system", "methode",
    "jahr", "jahrzehnt", "monat", "woche", "tag", "investor", "internet", "netz",
    "website", "software", "daten", "information",
    "jahrhundert", "hitliste", "rangliste",
}
CONCRETE_HINTS = {
    "tier", "pflanze", "baum", "blume", "frucht", "obst", "gemüse", "essen", "getränk",
    "kleidung", "möbel", "gerät", "werkzeug", "fahrzeug", "gebäude", "raum", "körper",
    "vogel", "hund", "katze", "biene", "haus", "tisch", "stuhl", "auto", "zug", "buch",
}
ABSTRACT_ZH_HINTS = {
    "制度", "主义", "关系", "情况", "意义", "经验", "责任", "社会", "政治", "经济",
    "教育", "时间", "问题", "想法", "机会", "原因", "结果", "影响", "变化", "自由",
    "决定", "可能", "发展", "取消", "替代", "税", "权利", "义务",
    "声音", "音色", "职业", "事业", "候选", "参选", "资格", "身份", "状态", "过程",
    "方法", "系统", "人物", "人",
    "十年", "年代", "年", "月", "周", "天", "投资者", "互联网", "网络", "网站",
    "软件", "数据", "信息",
    "世纪", "排行榜", "排名",
}
CONCRETE_ZH_HINTS = {
    "动物", "植物", "树", "花", "水果", "蔬菜", "食物", "饮料", "衣服", "家具",
    "工具", "车辆", "建筑", "房间", "身体", "鸟", "狗", "猫", "蜜蜂", "房子",
    "桌", "椅", "车", "书", "鱼", "虫", "机器", "设备",
}


def entry_is_concrete_noun(entry: VocabularyEntry) -> bool:
    if isinstance(entry.extra_data, dict) and entry.extra_data.get("image_skip"):
        return False
    lemma = normalize_similarity_text(entry.lemma)
    meaning_text = " ".join(item.gloss for item in entry.meanings).lower()
    tag_text = " ".join(item.name for item in entry.tags).lower()
    text = f"{lemma} {meaning_text} {tag_text}"
    if any(hint in text for hint in CONCRETE_HINTS) or any(hint in meaning_text for hint in CONCRETE_ZH_HINTS):
        return True
    if any(hint in text for hint in ABSTRACT_HINTS) or any(hint in meaning_text for hint in ABSTRACT_ZH_HINTS):
        return False
    if lemma.endswith(("ung", "heit", "keit", "schaft", "tion", "ismus", "tät")):
        return False
    return True


def image_candidate_is_relevant(item: dict) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("title", "description", "categories")
    ).lower()
    blocked_terms = {
        "portrait",
        "person",
        "people",
        "man ",
        "woman ",
        "politician",
        "grave",
        "coat of arms",
        "signature",
        "painting of",
        "photograph of",
    }
    return not any(term in text for term in blocked_terms)


def parse_multi_values(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.replace("\n", "|").split("|")]
    return [part for part in parts if part]


def json_or_empty(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": value}


def extract_json_object(content: str) -> dict:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("DeepSeek did not return valid JSON")
        parsed = json.loads(content[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("DeepSeek response must be a JSON object")
    return parsed


def optional_text(value) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def clean_meanings(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if isinstance(item, str):
            gloss = item.strip()
            if gloss:
                cleaned.append({"language": "zh", "gloss": gloss})
            continue
        if not isinstance(item, dict):
            continue
        gloss = optional_text(item.get("gloss") or item.get("zh") or item.get("meaning") or item.get("translation"))
        if gloss:
            cleaned.append(
                {
                    "language": optional_text(item.get("language")) or "zh",
                    "gloss": gloss,
                    "detail": optional_text(item.get("detail") or item.get("note")),
                }
            )
    return cleaned


def clean_forms(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        label = optional_text(item.get("label") or item.get("type"))
        value = optional_text(item.get("value") or item.get("form"))
        if label and value:
            cleaned.append({"label": label, "value": value, "note": optional_text(item.get("note"))})
    return cleaned


def clean_collocations(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if isinstance(item, str):
            phrase = item.strip()
            if phrase:
                cleaned.append({"phrase": phrase})
            continue
        if not isinstance(item, dict):
            continue
        phrase = optional_text(item.get("phrase") or item.get("de") or item.get("text"))
        if phrase:
            cleaned.append(
                {
                    "phrase": phrase,
                    "kind": optional_text(item.get("kind")),
                    "meaning": optional_text(item.get("meaning") or item.get("zh")),
                }
            )
    return cleaned


def clean_examples(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        german_text = optional_text(item.get("german_text") or item.get("de") or item.get("sentence"))
        if german_text:
            cleaned.append(
                {
                    "german_text": german_text,
                    "chinese_text": optional_text(item.get("chinese_text") or item.get("zh") or item.get("translation")),
                    "note": optional_text(item.get("note")),
                }
            )
    return cleaned


def clean_tags(items) -> list[dict]:
    if not isinstance(items, list):
        return []
    cleaned = []
    seen = set()
    for item in items:
        name = item if isinstance(item, str) else item.get("name") if isinstance(item, dict) else None
        name = optional_text(name)
        if name and name not in seen:
            seen.add(name)
            cleaned.append({"name": name, "tag_type": item.get("tag_type") if isinstance(item, dict) else None})
    return cleaned


def normalize_form_label(value: str | None) -> str:
    return normalize_lemma(value or "").replace("-", "_").replace(" ", "_")


def first_form_value(forms: list[FormPayload], labels: set[str]) -> str | None:
    for item in forms:
        if normalize_form_label(item.label) in labels and item.value.strip():
            return item.value.strip()
    return None


def add_form_if_missing(forms: list[FormPayload], label: str, value: str | None, note: str | None = None) -> None:
    value = optional_text(value)
    if not value:
        return
    normalized_label = normalize_form_label(label)
    for item in forms:
        if normalize_form_label(item.label) == normalized_label:
            if not item.value.strip():
                item.value = value
            return
    forms.append(FormPayload(label=label, value=value, note=note))


def add_tag_if_missing(tags: list[TagPayload], name: str, tag_type: str | None = None) -> None:
    normalized_name = normalize_lemma(name)
    if any(normalize_lemma(tag.name) == normalized_name for tag in tags):
        return
    tags.append(TagPayload(name=name, tag_type=tag_type))


def present_3sg_from_irregular(value: str | None) -> str | None:
    value = optional_text(value)
    if not value:
        return None
    parts = [part.strip() for part in re.split(r"[,;/]", value) if part.strip()]
    return parts[-1] if parts else value


def perfect_3sg(auxiliary: str | None, participle: str | None) -> str | None:
    participle = optional_text(participle)
    if not participle:
        return None
    auxiliary = optional_text(auxiliary)
    if not auxiliary:
        return None
    auxiliaries = [item.strip() for item in re.split(r"[/,;]", auxiliary) if item.strip()]
    if not auxiliaries:
        return None
    finite_auxiliaries = []
    for item in auxiliaries:
        lower = item.lower()
        if lower == "sein":
            finite_auxiliaries.append("ist")
        elif lower == "haben":
            finite_auxiliaries.append("hat")
        elif lower in {"ist", "hat"}:
            finite_auxiliaries.append(lower)
    if not finite_auxiliaries:
        return None
    return " / ".join(f"er/sie/es {aux} {participle}" for aux in finite_auxiliaries)


def append_verb_conjugation_note(payload: EntryCreate) -> None:
    present = first_form_value(
        payload.forms,
        {"present_3sg", "praesens_3sg", "präsens_3sg", "现在三单", "praesens", "präsens"},
    )
    preterite = first_form_value(
        payload.forms,
        {"preterite_3sg", "praeteritum_3sg", "präteritum_3sg", "past_3sg", "过去三单", "preterite", "past"},
    )
    perfect = first_form_value(payload.forms, {"perfect_3sg", "perfekt_3sg", "完成时三单", "perfect", "perfekt"})
    if not any([present, preterite, perfect]):
        return
    conjugation_note = "动词变位："
    parts = []
    if present:
        parts.append(f"现在三单 {present}")
    if preterite:
        parts.append(f"过去三单 {preterite}")
    if perfect:
        parts.append(f"完成时三单 {perfect}")
    conjugation_note += "；".join(parts)
    existing_lines = [
        line
        for line in (payload.notes or "").splitlines()
        if not line.strip().startswith("动词变位：")
    ]
    existing_lines.append(conjugation_note)
    payload.notes = "\n".join(line for line in existing_lines if line.strip())


def enrich_verb_forms(payload: EntryCreate, session: Session) -> EntryCreate:
    lemma = re.sub(r"^sich\s+", "", payload.lemma.strip(), flags=re.IGNORECASE)
    irregular = session.scalar(select(IrregularVerb).where(func.lower(IrregularVerb.infinitive) == lemma.lower()))
    is_verb = normalize_lemma(payload.part_of_speech or "") == "verb" or any(
        normalize_lemma(tag.name) == "动词" for tag in payload.tags
    )
    if not is_verb and not irregular:
        return payload

    if irregular:
        payload.part_of_speech = payload.part_of_speech or "verb"
        add_tag_if_missing(payload.tags, "动词", "词性")
        add_tag_if_missing(payload.tags, "不规则动词", "语法")
        present = present_3sg_from_irregular(irregular.present)
        preterite = irregular.preterite
        participle = irregular.participle_ii
        auxiliary = irregular.auxiliary
        add_form_if_missing(payload.forms, "present_3sg", present, "现在三单")
        add_form_if_missing(payload.forms, "preterite_3sg", preterite, "过去三单")
        add_form_if_missing(payload.forms, "participle_ii", participle, "第二分词")
        add_form_if_missing(payload.forms, "auxiliary", auxiliary, "完成时助动词")
        add_form_if_missing(payload.forms, "perfect_3sg", perfect_3sg(auxiliary, participle), "完成时三单")
    else:
        participle = first_form_value(payload.forms, {"participle_ii", "partizip_ii", "partizip_2", "第二分词"})
        auxiliary = first_form_value(payload.forms, {"auxiliary", "hilfsverb", "助动词"})
        add_form_if_missing(payload.forms, "perfect_3sg", perfect_3sg(auxiliary, participle), "完成时三单")

    append_verb_conjugation_note(payload)
    return payload


def normalize_deepseek_payload(lemma: str, data: dict) -> EntryCreate:
    forms = clean_forms(data.get("forms"))
    plural_form = data.get("plural_form")
    if not plural_form:
        plural_form = next(
            (
                item.get("value")
                for item in forms
                if isinstance(item, dict) and item.get("label") == "plural" and item.get("value")
            ),
            None,
        )
    payload = EntryCreate(
        lemma=(data.get("lemma") or lemma).strip(),
        language=data.get("language") or "de",
        part_of_speech=data.get("part_of_speech"),
        word_category=data.get("word_category"),
        gender=data.get("gender"),
        article=data.get("article"),
        plural_form=plural_form,
        cefr_level=data.get("cefr_level"),
        pronunciation=data.get("pronunciation"),
        source_type="deepseek_draft",
        source_ref=DEEPSEEK_MODEL,
        notes=data.get("notes"),
        extra_data=data.get("extra_data") if isinstance(data.get("extra_data"), dict) else {},
        raw_payload={"deepseek": data},
        meanings=clean_meanings(data.get("meanings")),
        forms=forms,
        collocations=clean_collocations(data.get("collocations")),
        examples=clean_examples(data.get("examples")),
        tags=clean_tags(data.get("tags")),
    )
    return payload


def generate_entry_draft_with_deepseek(lemma: str) -> EntryCreate:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="请先设置 DEEPSEEK_API_KEY 环境变量")

    system_prompt = """
You are a German vocabulary editor for a Chinese-speaking learner.
Return only valid JSON. No markdown.
The JSON must match this shape:
{
  "lemma": "German lemma",
  "language": "de",
  "part_of_speech": "noun|verb|adjective|adverb|phrase|...",
  "word_category": "optional category",
  "gender": "masculine|feminine|neuter|null",
  "article": "der|die|das|null",
  "plural_form": "optional plural",
  "cefr_level": "A1|A2|B1|B2|C1|C2|null",
  "pronunciation": "optional IPA or simple hint",
  "notes": "short Chinese learning note or null",
  "extra_data": {},
  "meanings": [{"language": "zh", "gloss": "中文释义", "detail": "optional nuance"}],
  "forms": [{"label": "plural|past|partizip_ii|comparative|superlative|...", "value": "form", "note": null}],
  "collocations": [{"phrase": "German collocation", "kind": null, "meaning": "中文含义"}],
  "examples": [{"german_text": "German sentence", "chinese_text": "中文翻译", "note": null}],
  "tags": [{"name": "short-tag", "tag_type": null}]
}
Prefer common, learner-useful meanings. Include 2-4 meanings, 2-4 collocations, and 2 examples when possible.
If the user input is an inflected form, plural, participle, tense form, declined adjective, or case form,
normalize it first and put the dictionary lemma in "lemma".
Examples: "ging" -> "gehen", "gegangen" -> "gehen", "Häusern" -> "Haus", "besseren" -> "besser".
For verbs, always include these forms when known:
- present_3sg: er/sie/es Präsens form
- preterite_3sg: er/sie/es Präteritum form
- participle_ii: Partizip II
- auxiliary: haben or sein
- perfect_3sg: er/sie/es hat/ist + Partizip II
Also include a concise Chinese "动词变位：" line in notes for verbs.
"""
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"为这个德语词条生成学习卡片草稿。输入可能是变形形式，请先还原为词典形：{lemma}"},
        ],
        "stream": False,
        "temperature": 0.2,
        "max_tokens": 1800,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(status_code=502, detail=f"DeepSeek 请求失败: {detail}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek 连接失败: {exc.reason}") from exc

    content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise HTTPException(status_code=502, detail="DeepSeek 没有返回可用内容")
    try:
        return normalize_deepseek_payload(lemma, extract_json_object(content))
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail=f"DeepSeek 返回格式无法解析: {exc}") from exc


def generate_image_search_query(entry: VocabularyEntry) -> str:
    cached = (entry.extra_data or {}).get("image_search_query") if isinstance(entry.extra_data, dict) else None
    if cached:
        return str(cached)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    lemma = re.sub(r"^(der|die|das)\s+", "", entry.lemma.strip(), flags=re.IGNORECASE)
    meanings = " / ".join(item.gloss for item in entry.meanings if item.language == "zh")
    if not api_key:
        return lemma
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return only JSON like {\"query\":\"english concrete object image search term\"}. No markdown.",
            },
            {
                "role": "user",
                "content": f"German noun: {entry.lemma}\nChinese meanings: {meanings}\nGive a concise English image search query for the physical object, not an abstract concept.",
            },
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 80,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
        content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
        parsed = extract_json_object(content or "{}")
        query = optional_text(parsed.get("query"))
        return query or lemma
    except Exception:
        return lemma


def call_deepseek_json(system_prompt: str, user_prompt: str, max_tokens: int = 1800, timeout: int = 90) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先设置 DEEPSEEK_API_KEY 环境变量")
    body = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response_data = json.loads(response.read().decode("utf-8"))
    content = response_data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("DeepSeek 没有返回可用内容")
    return extract_json_object(content)


def build_searchable_text(payload: EntryCreate) -> str:
    chunks = [
        payload.lemma,
        payload.part_of_speech or "",
        payload.word_category or "",
        payload.article or "",
        payload.plural_form or "",
        payload.notes or "",
    ]
    chunks.extend(item.gloss for item in payload.meanings)
    chunks.extend(item.detail or "" for item in payload.meanings)
    chunks.extend(item.value for item in payload.forms)
    chunks.extend(item.phrase for item in payload.collocations)
    chunks.extend(item.german_text for item in payload.examples)
    chunks.extend(item.chinese_text or "" for item in payload.examples)
    chunks.extend(item.name for item in payload.tags)
    return " ".join(chunk for chunk in chunks if chunk)


def entry_search_document(entry: VocabularyEntry) -> dict[str, str | int]:
    text_parts = [
        entry.lemma or "",
        entry.searchable_text or "",
        " ".join(item.value for item in entry.forms),
        " ".join(item.phrase for item in entry.collocations),
        " ".join(item.german_text for item in entry.examples),
    ]
    return {
        "entry_id": entry.id,
        "lemma": entry.lemma or "",
        "folded_lemma": fold_german_umlauts(entry.lemma),
        "folded_text": fold_german_umlauts(" ".join(text_parts)),
        "meanings": " ".join(
            " ".join(part for part in (item.gloss, item.detail) if part)
            for item in entry.meanings
        ),
        "forms": " ".join(item.value for item in entry.forms),
        "collocations": " ".join(
            " ".join(part for part in (item.phrase, item.meaning) if part)
            for item in entry.collocations
        ),
        "examples": " ".join(
            " ".join(part for part in (item.german_text, item.chinese_text) if part)
            for item in entry.examples
        ),
        "tags": " ".join(item.name for item in entry.tags),
    }


def wikimedia_search_images(query: str, limit: int) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": query,
            "gsrlimit": max(limit * 4, 8),
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata|commonmetadata",
            "iiurlwidth": "900",
            "origin": "*",
        }
    )
    request = urllib.request.Request(
        f"https://commons.wikimedia.org/w/api.php?{params}",
        headers={"User-Agent": "DeutscheStudy/0.1 local vocabulary image fetcher"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    pages = payload.get("query", {}).get("pages", {})
    results = []
    for page in pages.values():
        imageinfo = (page.get("imageinfo") or [{}])[0]
        mime = imageinfo.get("mime") or ""
        image_url = imageinfo.get("thumburl") or imageinfo.get("url")
        if not image_url or mime not in {"image/jpeg", "image/png", "image/webp"}:
            continue
        metadata = imageinfo.get("extmetadata") or {}
        source_url = imageinfo.get("url") or image_url
        title = page.get("title") or metadata.get("ObjectName", {}).get("value")
        item = {
            "image_url": image_url,
            "source_url": source_url,
            "page_url": imageinfo.get("descriptionurl") or f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(page.get('title', '').replace(' ', '_'))}",
            "title": strip_markup(title),
            "description": strip_markup(metadata.get("ImageDescription", {}).get("value")),
            "categories": strip_markup(metadata.get("Categories", {}).get("value")),
            "license": strip_markup(metadata.get("LicenseShortName", {}).get("value")),
            "attribution": strip_markup(metadata.get("Artist", {}).get("value") or metadata.get("Credit", {}).get("value")),
            "mime": mime,
        }
        if not image_candidate_is_relevant(item):
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def download_entry_image(entry_id: int, item: dict, index: int) -> EntryImage:
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(item["mime"], ".jpg")
    filename = f"entry-{entry_id}-{index}{extension}"
    destination = ENTRY_IMAGE_DIR / filename
    request = urllib.request.Request(
        item["image_url"],
        headers={
            "User-Agent": "DeutscheStudy/0.1 (local vocabulary image fetcher; Wikimedia Commons API client)",
            "Accept": "image/avif,image/webp,image/png,image/jpeg,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        with destination.open("wb") as file:
            shutil.copyfileobj(response, file)
    return EntryImage(
        entry_id=entry_id,
        local_path=f"entry-images/{filename}",
        source_url=item["source_url"],
        page_url=item.get("page_url"),
        title=item.get("title"),
        license=item.get("license"),
        attribution=item.get("attribution"),
        provider="wikimedia_commons",
    )


def remote_entry_image(entry_id: int, item: dict) -> EntryImage:
    return EntryImage(
        entry_id=entry_id,
        local_path=item["image_url"],
        source_url=item["source_url"],
        page_url=item.get("page_url"),
        title=item.get("title"),
        license=item.get("license"),
        attribution=item.get("attribution"),
        provider="wikimedia_commons_remote",
    )


def create_search_index() -> None:
    with engine.begin() as connection:
        existing_columns = []
        try:
            existing_columns = [row[1] for row in connection.execute(text("PRAGMA table_info(entry_search)")).all()]
        except Exception:
            existing_columns = []
        if existing_columns and ("folded_text" not in existing_columns or "folded_lemma" not in existing_columns):
            connection.execute(text("DROP TABLE entry_search"))
        connection.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS entry_search USING fts5(
                    entry_id UNINDEXED,
                    lemma,
                    folded_lemma,
                    folded_text,
                    meanings,
                    forms,
                    collocations,
                    examples,
                    tags,
                    tokenize='trigram'
                )
                """
            )
        )


def sync_entry_search(session: Session, entry: VocabularyEntry) -> None:
    if not entry.id:
        return
    document = entry_search_document(entry)
    session.execute(text("DELETE FROM entry_search WHERE entry_id = :entry_id"), {"entry_id": entry.id})
    session.execute(
        text(
            """
            INSERT INTO entry_search(entry_id, lemma, folded_lemma, folded_text, meanings, forms, collocations, examples, tags)
            VALUES (:entry_id, :lemma, :folded_lemma, :folded_text, :meanings, :forms, :collocations, :examples, :tags)
            """
        ),
        document,
    )


def rebuild_search_index(session: Session) -> None:
    session.execute(text("DELETE FROM entry_search"))
    entries = session.scalars(entry_query()).unique().all()
    for entry in entries:
        sync_entry_search(session, entry)
    session.commit()


def normalize_similarity_text(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def token_set(value: str | None) -> set[str]:
    return {token.lower() for token in TOKEN_RE.findall(value or "") if token.strip()}


def contains_cjk(value: str | None) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value or ""))


def cjk_char_set(value: str | None) -> set[str]:
    return {char for char in (value or "") if "\u4e00" <= char <= "\u9fff"}


def cjk_bigram_set(value: str | None) -> set[str]:
    chars = [char for char in (value or "") if "\u4e00" <= char <= "\u9fff"]
    if len(chars) < 2:
        return set(chars)
    return {"".join(chars[index : index + 2]) for index in range(len(chars) - 1)}


def split_meaning_parts(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[/|;；,，、.。()（）\[\]【】]+", value)
    return [normalize_similarity_text(part) for part in parts if normalize_similarity_text(part)]


def zh_meaning_parts(entry: VocabularyEntry) -> list[str]:
    parts = []
    seen = set()
    for meaning in entry.meanings:
        if meaning.language != "zh":
            continue
        for part in split_meaning_parts(meaning.gloss):
            cjk_len = len(cjk_char_set(part))
            if cjk_len < 2 or part in seen:
                continue
            seen.add(part)
            parts.append(part)
    return parts


def expanded_zh_meaning_parts(entry: VocabularyEntry) -> list[str]:
    parts = []
    seen = set()
    for part in zh_meaning_parts(entry):
        for term in expand_common_chinese_query_terms(part):
            if len(cjk_char_set(term)) >= 2 and term not in seen:
                seen.add(term)
                parts.append(term)
    return parts


def chinese_phrase_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_len = len(cjk_char_set(left))
    right_len = len(cjk_char_set(right))
    if min(left_len, right_len) >= 2 and (left in right or right in left):
        return 0.92
    bigram_score = jaccard(cjk_bigram_set(left), cjk_bigram_set(right))
    char_score = jaccard(cjk_char_set(left), cjk_char_set(right))
    ratio_score = SequenceMatcher(None, left, right).ratio()
    return max(bigram_score, char_score * 0.62, ratio_score * 0.48)


def zh_meaning_similarity_score(source: VocabularyEntry, target: VocabularyEntry) -> float:
    source_parts = expanded_zh_meaning_parts(source)
    target_parts = expanded_zh_meaning_parts(target)
    if not source_parts or not target_parts:
        return 0.0
    return max(
        chinese_phrase_similarity(source_part, target_part)
        for source_part in source_parts
        for target_part in target_parts
    )


def compact_query_terms(values: Iterable[str], limit: int = 12) -> list[str]:
    terms = []
    seen = set()
    for value in values:
        term = normalize_similarity_text(value)
        if not term or term in seen or len(term) > 16:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def expand_common_chinese_query_terms(query: str) -> list[str]:
    terms = [query]
    normalized_query = normalize_similarity_text(query)
    for key, synonyms in COMMON_CHINESE_QUERY_SYNONYMS.items():
        normalized_key = normalize_similarity_text(key)
        if normalized_query == normalized_key:
            terms.extend(synonyms)
        elif len(normalized_query) >= 2 and normalized_query in normalized_key:
            terms.append(key)
            terms.extend(synonyms[:2])
        elif len(normalized_key) >= 2 and normalized_key in normalized_query:
            terms.extend(synonyms[:2])
    return compact_query_terms(terms)


def expand_chinese_query_terms(query: str) -> list[str]:
    normalized_query = normalize_similarity_text(query)
    if not normalized_query:
        return []
    if normalized_query in CHINESE_QUERY_EXPANSION_CACHE:
        return CHINESE_QUERY_EXPANSION_CACHE[normalized_query]

    terms = expand_common_chinese_query_terms(normalized_query)
    if len(cjk_char_set(normalized_query)) >= 2 and os.environ.get("DEEPSEEK_API_KEY"):
        try:
            payload = call_deepseek_json(
                "只返回 JSON，不要 Markdown。格式为 {\"terms\":[\"中文近义词或同义短语\"]}。",
                (
                    "为德语词汇本地检索扩展一个中文查询。"
                    "给出 5 到 10 个中文同义词、近义词、常见释义表达，避免英文，避免解释。\n"
                    f"查询：{normalized_query}"
                ),
                max_tokens=220,
                timeout=8,
            )
            llm_terms = payload.get("terms")
            if isinstance(llm_terms, list):
                terms = compact_query_terms([*terms, *(str(item) for item in llm_terms)])
        except Exception:
            pass

    CHINESE_QUERY_EXPANSION_CACHE[normalized_query] = terms
    return terms


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def entry_similarity_text(entry: VocabularyEntry) -> str:
    chunks = [
        entry.lemma,
        entry.part_of_speech,
        entry.word_category,
        entry.cefr_level,
        entry.searchable_text,
    ]
    chunks.extend(item.gloss for item in entry.meanings)
    chunks.extend(item.detail or "" for item in entry.meanings)
    chunks.extend(item.phrase for item in entry.collocations)
    chunks.extend(item.meaning or "" for item in entry.collocations)
    chunks.extend(item.name for item in entry.tags)
    return " ".join(chunk for chunk in chunks if chunk)


def similarity_score(source: VocabularyEntry, target: VocabularyEntry) -> tuple[float, list[str]]:
    source_lemma = normalize_similarity_text(source.lemma)
    target_lemma = normalize_similarity_text(target.lemma)
    lemma_ratio = SequenceMatcher(None, source_lemma, target_lemma).ratio()
    prefix_score = 1.0 if source_lemma and target_lemma and (
        source_lemma.startswith(target_lemma) or target_lemma.startswith(source_lemma)
    ) else 0.0

    source_tags = {item.name.lower() for item in source.tags}
    target_tags = {item.name.lower() for item in target.tags}
    tag_score = jaccard(source_tags, target_tags)

    metadata_matches = sum(
        1
        for left, right in (
            (source.part_of_speech, target.part_of_speech),
            (source.cefr_level, target.cefr_level),
            (source.word_category, target.word_category),
        )
        if left and right and left == right
    )
    metadata_score = metadata_matches / 3

    text_score = jaccard(token_set(entry_similarity_text(source)), token_set(entry_similarity_text(target)))
    zh_meaning_score = zh_meaning_similarity_score(source, target)
    collocation_score = jaccard(
        token_set(" ".join(item.phrase for item in source.collocations)),
        token_set(" ".join(item.phrase for item in target.collocations)),
    )
    score = (
        0.20 * lemma_ratio
        + 0.15 * prefix_score
        + 0.12 * tag_score
        + 0.08 * metadata_score
        + 0.12 * text_score
        + 0.28 * zh_meaning_score
        + 0.05 * collocation_score
    )

    reasons = []
    if lemma_ratio >= 0.55 or prefix_score:
        reasons.append("词形相近")
    if source_tags & target_tags:
        reasons.append("共享标签: " + " / ".join(sorted(source_tags & target_tags)[:3]))
    if source.part_of_speech and source.part_of_speech == target.part_of_speech:
        reasons.append(f"同词性: {source.part_of_speech}")
    if source.cefr_level and source.cefr_level == target.cefr_level:
        reasons.append(f"同级别: {source.cefr_level}")
    if zh_meaning_score >= 0.68:
        reasons.append("中文释义相近")
    elif text_score >= 0.12:
        reasons.append("释义或例句文本相近")
    if collocation_score >= 0.15:
        reasons.append("搭配相近")
    return score, reasons


def search_result_score(query: str, entry: VocabularyEntry) -> float:
    normalized_query = normalize_similarity_text(query)
    folded_query = fold_german_umlauts(query)
    if not normalized_query:
        return 0.0

    lemma = normalize_similarity_text(entry.lemma)
    searchable = normalize_similarity_text(entry.searchable_text)
    folded_lemma = fold_german_umlauts(entry.lemma)
    folded_searchable = fold_german_umlauts(entry.searchable_text)
    if lemma == normalized_query:
        return 1.0
    if folded_lemma == folded_query:
        return 0.96
    if lemma.startswith(normalized_query) or normalized_query in lemma:
        return 0.85
    if folded_lemma.startswith(folded_query) or folded_query in folded_lemma:
        return 0.82
    if normalized_query in searchable:
        return 0.7
    if folded_query in folded_searchable:
        return 0.68

    query_tokens = token_set(normalized_query)
    entry_tokens = token_set(entry_similarity_text(entry))
    token_overlap = jaccard(query_tokens, entry_tokens)
    lemma_ratio = SequenceMatcher(None, normalized_query, lemma).ratio()
    return max(token_overlap, lemma_ratio * 0.55)


def best_search_result_score(queries: Iterable[str], entry: VocabularyEntry) -> float:
    return max((search_result_score(query, entry) for query in queries if query), default=0.0)


def chinese_meaning_text(entry: VocabularyEntry) -> str:
    chunks = []
    for item in entry.meanings:
        if item.language != "zh":
            continue
        chunks.append(item.gloss)
        if item.detail:
            chunks.append(item.detail)
    return " ".join(chunk for chunk in chunks if chunk)


def chinese_meaning_search_score(query: str, entry: VocabularyEntry) -> float:
    normalized_query = normalize_similarity_text(query)
    if not normalized_query:
        return 0.0
    query_cjk_length = len(cjk_char_set(normalized_query))

    zh_parts = []
    for item in entry.meanings:
        if item.language != "zh":
            continue
        zh_parts.append(item.gloss)
        if item.detail:
            zh_parts.append(item.detail)
    zh_parts = [normalize_similarity_text(part) for part in zh_parts if part]
    if not zh_parts:
        return 0.0

    combined = normalize_similarity_text(" ".join(zh_parts))
    if normalized_query == combined:
        return 1.0

    best = 0.0
    for part in zh_parts:
        part_cjk_length = len(cjk_char_set(part))
        if normalized_query == part:
            best = max(best, 1.0)
        if normalized_query in part:
            best = max(best, 0.9)
        if (
            part in normalized_query
            and part_cjk_length >= 2
            and part_cjk_length / max(query_cjk_length, 1) >= 0.6
        ):
            best = max(best, 0.68)
        if part_cjk_length > 1 or query_cjk_length <= 1:
            bigram_overlap = jaccard(cjk_bigram_set(normalized_query), cjk_bigram_set(part))
            ratio_weight = 0.55 if bigram_overlap > 0 or query_cjk_length <= 1 else 0.45
            best = max(best, SequenceMatcher(None, normalized_query, part).ratio() * ratio_weight)

    if normalized_query in combined:
        best = max(best, 0.86)
    combined_bigram_overlap = jaccard(cjk_bigram_set(normalized_query), cjk_bigram_set(combined))
    combined_ratio_weight = 0.55 if combined_bigram_overlap > 0 or query_cjk_length <= 1 else 0.45
    best = max(best, SequenceMatcher(None, normalized_query, combined).ratio() * combined_ratio_weight)
    best = max(best, jaccard(cjk_char_set(normalized_query), cjk_char_set(combined)) * 0.72)
    best = max(best, combined_bigram_overlap * 0.9)
    return best


def rebuild_similarity_index(session: Session) -> None:
    entries = session.scalars(entry_query()).unique().all()
    session.execute(delete(EntrySimilarity))
    for source in entries:
        ranked = []
        for target in entries:
            if source.id == target.id:
                continue
            score, reasons = similarity_score(source, target)
            if score >= 0.18:
                ranked.append((score, target.id, reasons))
        for score, target_id, reasons in sorted(ranked, reverse=True)[:12]:
            session.add(
                EntrySimilarity(
                    source_entry_id=source.id,
                    target_entry_id=target_id,
                    score=round(score * 1000),
                    reasons={"items": reasons},
                )
            )
    session.commit()


def rebuild_similarity_for_entry(session: Session, entry_id: int) -> None:
    source = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not source:
        return
    session.execute(delete(EntrySimilarity).where(EntrySimilarity.source_entry_id == entry_id))
    entries = session.scalars(entry_query().where(VocabularyEntry.id != entry_id)).unique().all()
    ranked = []
    for target in entries:
        score, reasons = similarity_score(source, target)
        if score >= 0.18:
            ranked.append((score, target.id, reasons))
    for score, target_id, reasons in sorted(ranked, reverse=True)[:12]:
        session.add(
            EntrySimilarity(
                source_entry_id=source.id,
                target_entry_id=target_id,
                score=round(score * 1000),
                reasons={"items": reasons},
            )
        )
    session.commit()


def calculate_similar_entries(session: Session, entry_id: int, limit: int) -> list[SimilarEntryResponse]:
    source = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not source:
        return []
    entries = session.scalars(entry_query().where(VocabularyEntry.id != entry_id)).unique().all()
    ranked = []
    for target in entries:
        score, reasons = similarity_score(source, target)
        if score >= 0.18:
            ranked.append((score, target, reasons))
    results = []
    for score, target, reasons in sorted(ranked, key=lambda item: item[0], reverse=True)[:limit]:
        results.append(
            SimilarEntryResponse(
                entry=serialize_entry(target),
                score=round(score, 3),
                reasons=reasons,
            )
        )
    return results


def refresh_indexes(session: Session) -> None:
    rebuild_search_index(session)
    rebuild_similarity_index(session)


def search_index_is_empty(session: Session) -> bool:
    count = session.scalar(text("SELECT count(*) FROM entry_search")) or 0
    return count == 0


def search_index_needs_rebuild(session: Session) -> bool:
    columns = [row[1] for row in session.execute(text("PRAGMA table_info(entry_search)")).all()]
    return "folded_text" not in columns or "folded_lemma" not in columns or search_index_is_empty(session)


def escape_fts_query(value: str) -> str:
    return '"' + value.strip().replace('"', '""') + '"'


def replace_children(entry: VocabularyEntry, payload: EntryCreate, session: Session | None = None) -> None:
    if session is not None and entry.id:
        entry.meanings.clear()
        entry.forms.clear()
        entry.collocations.clear()
        entry.examples.clear()
        entry.tags.clear()
        session.flush()

    entry.meanings = [
        Meaning(sort_order=index, language=item.language, gloss=item.gloss, detail=item.detail)
        for index, item in enumerate(payload.meanings)
    ]
    entry.forms = [EntryForm(label=item.label, value=item.value, note=item.note) for item in payload.forms]
    entry.collocations = [
        Collocation(phrase=item.phrase, kind=item.kind, meaning=item.meaning)
        for item in payload.collocations
    ]
    entry.examples = [
        ExampleSentence(german_text=item.german_text, chinese_text=item.chinese_text, note=item.note)
        for item in payload.examples
    ]
    seen_tags: set[str] = set()
    tags: list[EntryTag] = []
    for item in payload.tags:
        name = item.name.strip()
        if name and name not in seen_tags:
            seen_tags.add(name)
            tags.append(EntryTag(name=name, tag_type=item.tag_type))
    entry.tags = tags


def apply_payload(entry: VocabularyEntry, payload: EntryCreate, session: Session | None = None) -> VocabularyEntry:
    if session is not None:
        payload = enrich_verb_forms(payload, session)
    entry.lemma = payload.lemma.strip()
    entry.normalized_lemma = normalize_lemma(payload.lemma)
    entry.language = payload.language
    entry.part_of_speech = payload.part_of_speech
    entry.word_category = payload.word_category
    entry.gender = payload.gender
    entry.article = payload.article
    entry.plural_form = payload.plural_form
    entry.cefr_level = payload.cefr_level
    entry.pronunciation = payload.pronunciation
    entry.source_type = payload.source_type
    entry.source_ref = payload.source_ref
    entry.notes = payload.notes
    entry.extra_data = payload.extra_data
    entry.raw_payload = payload.raw_payload
    entry.searchable_text = build_searchable_text(payload)
    replace_children(entry, payload, session=session)
    return entry


def serialize_irregular_verb(verb: IrregularVerb) -> IrregularVerbResponse:
    return IrregularVerbResponse(
        id=verb.id,
        infinitive=verb.infinitive,
        present=verb.present,
        preterite=verb.preterite,
        participle_ii=verb.participle_ii,
        imperative=verb.imperative,
        subjunctive_ii=verb.subjunctive_ii,
        auxiliary=verb.auxiliary,
        meaning_zh=verb.meaning_zh,
        source_ref=verb.source_ref,
        notes=verb.notes,
    )


def clean_anki_field(value: str | None) -> str:
    return (
        html_escape(value or "")
        .replace("\t", " ")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("\r", "<br>")
    )


def html_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def unique_join(values: Iterable[str]) -> str:
    seen = set()
    result = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return " / ".join(result)


def vocabulary_meanings_by_infinitive(session: Session, verbs: list[IrregularVerb]) -> dict[str, str]:
    normalized_values = sorted({normalize_lemma(verb.infinitive) for verb in verbs})
    if not normalized_values:
        return {}

    rows = session.execute(
        select(VocabularyEntry.normalized_lemma, Meaning.gloss)
        .join(Meaning, Meaning.entry_id == VocabularyEntry.id)
        .where(
            VocabularyEntry.normalized_lemma.in_(normalized_values),
            VocabularyEntry.part_of_speech == "verb",
            Meaning.language == "zh",
        )
        .order_by(VocabularyEntry.id, Meaning.sort_order)
    ).all()

    meanings: dict[str, list[str]] = {}
    for normalized, gloss in rows:
        meanings.setdefault(normalized, []).append(gloss)
    return {normalized: unique_join(items) for normalized, items in meanings.items()}


def irregular_verb_anki_back(verb: IrregularVerb, meaning: str | None = None) -> str:
    rows = [
        ("中文", meaning or verb.meaning_zh),
        ("现在时", verb.present),
        ("过去式", verb.preterite),
        ("第二分词", verb.participle_ii),
        ("助动词", verb.auxiliary),
        ("命令式", verb.imperative),
        ("第二虚拟式", verb.subjunctive_ii),
    ]
    table_rows = "".join(
        f"<tr><th>{clean_anki_field(label)}</th><td>{clean_anki_field(value)}</td></tr>"
        for label, value in rows
        if value
    )
    return (
        "<div class=\"irregular-verb-card\">"
        f"<h3>{clean_anki_field(verb.infinitive)}</h3>"
        "<table>"
        f"{table_rows}"
        "</table>"
        "</div>"
    )


def build_irregular_verbs_anki_tsv(
    verbs: list[IrregularVerb],
    vocabulary_meanings: dict[str, str] | None = None,
) -> str:
    vocabulary_meanings = vocabulary_meanings or {}
    lines = [
        "#separator:tab",
        "#html:true",
        "#notetype:Basic",
        "#deck:Deutsch::不规则动词",
        "#tags column:3",
    ]
    for verb in verbs:
        lines.append(
            "\t".join(
                [
                    clean_anki_field(verb.infinitive),
                    irregular_verb_anki_back(verb, vocabulary_meanings.get(normalize_lemma(verb.infinitive))),
                    "不规则动词 irregular_verbs Deutsch",
                ]
            )
        )
    return "\n".join(lines) + "\n"


def csv_row_to_payload(row: dict[str, str]) -> EntryCreate:
    meanings = [
        {"language": "zh", "gloss": gloss}
        for gloss in parse_multi_values(row.get("meanings"))
    ]
    forms = []
    for label in ("plural", "past", "partizip_ii", "comparative", "superlative"):
        value = row.get(label)
        if value:
            forms.append({"label": label, "value": value})
    collocations = []
    for item in parse_multi_values(row.get("collocations")):
        if "::" in item:
            phrase, meaning = item.split("::", 1)
            collocations.append({"phrase": phrase.strip(), "meaning": meaning.strip()})
        else:
            collocations.append({"phrase": item})
    examples = []
    german_examples = parse_multi_values(row.get("example_de"))
    chinese_examples = parse_multi_values(row.get("example_zh"))
    for index, german_text in enumerate(german_examples):
        chinese_text = chinese_examples[index] if index < len(chinese_examples) else None
        examples.append({"german_text": german_text, "chinese_text": chinese_text})
    tags = [{"name": tag} for tag in parse_multi_values(row.get("tags"))]

    return EntryCreate(
        lemma=row.get("lemma", "").strip(),
        language=row.get("language", "de").strip() or "de",
        part_of_speech=row.get("part_of_speech") or None,
        word_category=row.get("word_category") or None,
        gender=row.get("gender") or None,
        article=row.get("article") or None,
        plural_form=row.get("plural_form") or None,
        cefr_level=row.get("cefr_level") or None,
        pronunciation=row.get("pronunciation") or None,
        source_type=row.get("source_type") or "csv",
        source_ref=row.get("source_ref") or None,
        notes=row.get("notes") or None,
        extra_data=json_or_empty(row.get("extra_data")),
        raw_payload=json_or_empty(row.get("raw_payload")),
        meanings=meanings,
        forms=forms,
        collocations=collocations,
        examples=examples,
        tags=tags,
    )


def fetch_dwds_frequency(lemma: str) -> dict | None:
    """Fetch word frequency data from the DWDS API."""
    url = f"https://www.dwds.de/api/frequency/?q={urllib.parse.quote(lemma)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DeutscheStudy/0.1 (frequency fetcher)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def save_entry_frequency(
    session: Session,
    entry: VocabularyEntry,
    query_lemma: str,
    data: dict | None,
    status: str,
    error: str | None = None,
) -> WordFrequency:
    existing = session.scalar(
        select(WordFrequency).where(WordFrequency.entry_id == entry.id)
    )
    freq_record = existing or WordFrequency(
        entry_id=entry.id,
        q=query_lemma,
        lemma=query_lemma,
    )
    if data:
        freq_record.q = str(data.get("q", query_lemma))
        freq_record.lemma = str(data.get("lemma", query_lemma))
        freq_record.frequency = data.get("frequency")
        freq_record.hits = data.get("hits")
        freq_record.total = str(data.get("total", "")) if data.get("total") else None
    else:
        freq_record.q = query_lemma
        freq_record.lemma = query_lemma
        freq_record.frequency = None
        freq_record.hits = None
        freq_record.total = None
    freq_record.status = status
    freq_record.last_error = error
    freq_record.attempt_count = (freq_record.attempt_count or 0) + 1
    session.add(freq_record)
    session.commit()
    session.refresh(freq_record)
    return freq_record


def get_entry_frequency(session: Session, entry: VocabularyEntry, force_refresh: bool = False) -> dict | None:
    """Get frequency data for an entry, from cache or by fetching from DWDS."""
    freq = session.scalar(
        select(WordFrequency).where(WordFrequency.entry_id == entry.id)
    )
    if freq and not force_refresh:
        return serialize_frequency(freq)
    # Try to fetch from DWDS
    lemma = re.sub(r"^(der|die|das)\s+", "", entry.lemma.strip(), flags=re.IGNORECASE)
    data = fetch_dwds_frequency(lemma)
    status = "success" if data and data.get("frequency") is not None else "no_result" if data else "failed"
    error = None if data else "DWDS request failed"
    with WRITE_LOCK:
        freq_record = save_entry_frequency(session, entry, lemma, data, status, error)
    return serialize_frequency(freq_record)


def upsert_entries(session: Session, payloads: Iterable[EntryCreate]) -> int:

    create_search_index()
    with WRITE_LOCK:
        imported = 0
        changed_entries: list[VocabularyEntry] = []
        for payload in payloads:
            if not payload.lemma.strip():
                continue
            stmt = entry_query().where(VocabularyEntry.normalized_lemma == normalize_lemma(payload.lemma))
            existing = session.scalars(stmt).first()
            entry = existing or VocabularyEntry(lemma="", normalized_lemma="")
            apply_payload(entry, payload, session=session)
            session.add(entry)
            changed_entries.append(entry)
            imported += 1
        session.flush()
        for entry in changed_entries:
            sync_entry_search(session, entry)
        session.commit()
        return imported


def ensure_word_frequency_columns() -> None:
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(word_frequencies)").all()
        }
        if "status" not in columns:
            connection.exec_driver_sql("ALTER TABLE word_frequencies ADD COLUMN status VARCHAR(32)")
        if "attempt_count" not in columns:
            connection.exec_driver_sql("ALTER TABLE word_frequencies ADD COLUMN attempt_count INTEGER DEFAULT 0")
        if "last_error" not in columns:
            connection.exec_driver_sql("ALTER TABLE word_frequencies ADD COLUMN last_error TEXT")
        connection.execute(
            text(
                """
                UPDATE word_frequencies
                SET status = CASE
                    WHEN frequency IS NOT NULL THEN 'success'
                    ELSE 'no_result'
                END
                WHERE status IS NULL OR status = ''
                """
            )
        )
        connection.execute(
            text("UPDATE word_frequencies SET attempt_count = 1 WHERE attempt_count IS NULL OR attempt_count = 0")
        )


def ensure_reading_page_columns() -> None:
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(reading_pages)").all()
        }
        if "notes" not in columns:
            connection.exec_driver_sql("ALTER TABLE reading_pages ADD COLUMN notes TEXT")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_word_frequency_columns()
    ensure_reading_page_columns()
    create_search_index()
    with SessionLocal() as session:
        ensure_reading_books(session)
        if search_index_needs_rebuild(session):
            rebuild_search_index(session)


@app.get("/")
def index():
    if (FRONTEND_DIST_DIR / "index.html").exists():
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
    return HTMLResponse(
        """
        <html><body style="font-family: sans-serif; padding: 24px;">
        <h2>React 前端尚未构建</h2>
        <p>请先在 <code>frontend/</code> 目录执行 <code>npm install</code> 和 <code>npm run build</code>。</p>
        </body></html>
        """
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/stats")
def stats(session: Session = Depends(get_session)):
    total = session.scalar(select(func.count(VocabularyEntry.id))) or 0
    levels = session.execute(
        select(VocabularyEntry.cefr_level, func.count(VocabularyEntry.id))
        .group_by(VocabularyEntry.cefr_level)
        .order_by(VocabularyEntry.cefr_level)
    ).all()
    return {
        "total_entries": total,
        "cefr_levels": [
            {"level": level or "", "count": count}
            for level, count in levels
        ],
    }


@app.get("/api/reading/books", response_model=list[ReadingBookResponse])
def list_reading_books(session: Session = Depends(get_session)):
    ensure_reading_books(session)
    books = session.scalars(select(ReadingBook).order_by(ReadingBook.updated_at.desc(), ReadingBook.title)).all()
    return [serialize_reading_book(book) for book in books]


@app.get("/api/reading/books/{book_id}", response_model=ReadingBookResponse)
def get_reading_book(book_id: int, session: Session = Depends(get_session)):
    book = session.get(ReadingBook, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return serialize_reading_book(book)


def reading_page_query() -> Select[tuple[ReadingPage]]:
    return select(ReadingPage).options(selectinload(ReadingPage.messages))


@app.get("/api/reading/books/{book_id}/pages/{page_number}", response_model=ReadingPageResponse)
def get_reading_page(book_id: int, page_number: int, session: Session = Depends(get_session)):
    page = session.scalars(
        reading_page_query().where(
            ReadingPage.book_id == book_id,
            ReadingPage.page_number == page_number,
        )
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return serialize_reading_page(page)


@app.post("/api/reading/pages/{page_id}/prepare", response_model=ReadingPageResponse)
def prepare_reading_page_api(page_id: int, session: Session = Depends(get_session)):
    page = session.scalars(reading_page_query().where(ReadingPage.id == page_id)).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    page = prepare_reading_page(session, page)
    page = session.scalars(reading_page_query().where(ReadingPage.id == page.id)).first()
    return serialize_reading_page(page)


@app.post("/api/reading/pages/{page_id}/deepseek", response_model=ReadingPageResponse)
def generate_reading_page_analysis(page_id: int, session: Session = Depends(get_session)):
    page = session.scalars(reading_page_query().where(ReadingPage.id == page_id)).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    if not page.ocr_text or not page.image_path:
        page = prepare_reading_page(session, page)
    page = generate_reading_page_deepseek(page)
    session.add(page)
    session.commit()
    page = session.scalars(reading_page_query().where(ReadingPage.id == page.id)).first()
    return serialize_reading_page(page)


@app.patch("/api/reading/pages/{page_id}/notes", response_model=ReadingPageResponse)
def update_reading_page_notes(page_id: int, payload: ReadingPageNotesUpdate, session: Session = Depends(get_session)):
    page = session.scalars(reading_page_query().where(ReadingPage.id == page_id)).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    page.notes = payload.notes.strip() if payload.notes and payload.notes.strip() else None
    session.add(page)
    session.commit()
    page = session.scalars(reading_page_query().where(ReadingPage.id == page.id)).first()
    return serialize_reading_page(page)


@app.patch("/api/reading/pages/{page_id}/text", response_model=ReadingPageResponse)
def update_reading_page_text(page_id: int, payload: ReadingPageTextUpdate, session: Session = Depends(get_session)):
    page = session.scalars(reading_page_query().where(ReadingPage.id == page_id)).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    if payload.ocr_text is not None:
        page.ocr_text = payload.ocr_text.strip() or None
    if payload.translation_zh is not None:
        page.translation_zh = payload.translation_zh.strip() or None
    if page.translation_zh or page.grammar_notes or (page.keywords or []):
        page.status = "deepseek_ready"
    elif page.ocr_text:
        page.status = "ocr_ready"
    elif page.image_path:
        page.status = "image_ready"
    else:
        page.status = "new"
    session.add(page)
    session.commit()
    page = session.scalars(reading_page_query().where(ReadingPage.id == page.id)).first()
    return serialize_reading_page(page)


@app.post("/api/reading/pages/{page_id}/ask", response_model=ReadingPageAskResponse)
def ask_reading_page(page_id: int, payload: ReadingPageAskRequest, session: Session = Depends(get_session)):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="问题不能为空")
    page = session.scalars(reading_page_query().where(ReadingPage.id == page_id)).first()
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    if not page.ocr_text:
        page = prepare_reading_page(session, page)

    user_message = ReadingPageMessage(page_id=page.id, role="user", content=question)
    session.add(user_message)
    session.commit()

    keywords_text = "\n".join(
        f"- {item.get('term')}: {item.get('meaning_zh')} ({item.get('note')})"
        for item in (page.keywords or [])
        if isinstance(item, dict)
    )
    system_prompt = "你是德语精读问答助手。只根据当前页内容回答。返回 JSON：{\"answer\":\"...\"}。"
    user_prompt = f"""
当前页页码: {page.page_number}

德语原文/OCR:
{page.ocr_text or ""}

中文翻译:
{page.translation_zh or ""}

关键词:
{keywords_text}

语法讲解:
{page.grammar_notes or ""}

用户问题:
{question}

请用中文回答，必要时引用德语原文中的词或短语。
"""
    try:
        data = call_deepseek_json(system_prompt, user_prompt, max_tokens=1600, timeout=90)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    answer = optional_text(data.get("answer")) or "这页内容里暂时找不到足够依据回答。"
    assistant_message = ReadingPageMessage(page_id=page.id, role="assistant", content=answer)
    session.add(assistant_message)
    session.commit()
    session.refresh(assistant_message)
    return ReadingPageAskResponse(message=serialize_reading_message(assistant_message))


@app.get("/api/tags")
def list_tags(session: Session = Depends(get_session)):
    topic_tree = [
        {
            "name": "日常生活",
            "children": [
                {"name": "生活实物", "tags": ["生活实物"]},
                {"name": "食物", "tags": ["食物"], "children": [
                    {"name": "蔬菜", "tags": ["蔬菜"]},
                    {"name": "水果", "tags": ["水果"]},
                    {"name": "肉类", "tags": ["肉类"]},
                    {"name": "海鲜鱼类", "tags": ["海鲜鱼类"]},
                    {"name": "乳制品", "tags": ["乳制品"]},
                    {"name": "面包点心", "tags": ["面包点心"]},
                    {"name": "零食", "tags": ["零食"]},
                    {"name": "饮料", "tags": ["饮料"]},
                    {"name": "调料干货", "tags": ["调料干货"]},
                ]},
                {"name": "居家用品", "children": [
                    {"name": "厨房", "tags": ["厨房"]},
                    {"name": "浴室", "tags": ["浴室"]},
                    {"name": "家具家居", "tags": ["家具家居"]},
                    {"name": "电子用品", "tags": ["电子用品"]},
                ]},
                {"name": "个人物品", "children": [
                    {"name": "衣物", "tags": ["衣物"]},
                    {"name": "文具", "tags": ["文具"]},
                    {"name": "工具", "tags": ["工具"]},
                    {"name": "超市购物", "tags": ["超市购物"]},
                ]},
            ],
        },
        {
            "name": "公共事务",
            "children": [
                {"name": "政治场景", "tags": ["政治场景"]},
                {"name": "政治制度", "children": [
                    {"name": "政治通用", "tags": ["政治通用"]},
                    {"name": "政府机构", "tags": ["政府机构"]},
                    {"name": "政治制度", "tags": ["政治制度"]},
                    {"name": "政党议会", "tags": ["政党议会"]},
                ]},
                {"name": "选举与政策", "children": [
                    {"name": "选举投票", "tags": ["选举投票"]},
                    {"name": "法律政策", "tags": ["法律政策"]},
                    {"name": "社会议题", "tags": ["社会议题"]},
                ]},
                {"name": "国际与媒体", "children": [
                    {"name": "国际关系", "tags": ["国际关系"]},
                    {"name": "政治新闻", "tags": ["政治新闻"]},
                    {"name": "权利自由", "tags": ["权利自由"]},
                ]},
            ],
        },
        {
            "name": "经济金融",
            "children": [
                {"name": "金融场景", "tags": ["金融场景"]},
                {"name": "个人金融", "children": [
                    {"name": "银行账户", "tags": ["银行账户"]},
                    {"name": "支付转账", "tags": ["支付转账"]},
                    {"name": "贷款信用", "tags": ["贷款信用"]},
                    {"name": "收入预算", "tags": ["收入预算"]},
                ]},
                {"name": "投资与保障", "children": [
                    {"name": "投资证券", "tags": ["投资证券"]},
                    {"name": "保险", "tags": ["保险"]},
                    {"name": "税务", "tags": ["税务"]},
                ]},
                {"name": "企业与宏观", "children": [
                    {"name": "公司财务", "tags": ["公司财务"]},
                    {"name": "宏观金融", "tags": ["宏观金融"]},
                ]},
            ],
        },
        {
            "name": "交通出行",
            "children": [
                {"name": "驾照理论", "tags": ["驾照理论"]},
                {"name": "交通基础", "children": [
                    {"name": "车辆类型", "tags": ["车辆类型"]},
                    {"name": "交通参与者", "tags": ["交通参与者"]},
                    {"name": "交通状况", "tags": ["交通状况"]},
                    {"name": "道路场景", "tags": ["道路场景"]},
                    {"name": "交通标志", "tags": ["交通标志"]},
                ]},
                {"name": "规则与法规", "children": [
                    {"name": "交通规则", "tags": ["交通规则"]},
                    {"name": "驾照法规", "tags": ["驾照法规"]},
                    {"name": "方向位置", "tags": ["方向位置"]},
                ]},
                {"name": "驾驶安全", "children": [
                    {"name": "事故应急", "tags": ["事故应急"]},
                    {"name": "危险因素", "tags": ["危险因素"]},
                    {"name": "车辆部件", "tags": ["车辆部件"]},
                    {"name": "驾驶动作", "tags": ["驾驶动作"]},
                ]},
            ],
        },
    ]
    user_tag_rows = session.execute(
        select(EntryTag.name, func.count(EntryTag.id))
        .group_by(EntryTag.name)
        .order_by(func.count(EntryTag.id).desc(), EntryTag.name)
    ).all()
    tag_counts = {name: count for name, count in user_tag_rows}
    pos_rows = session.execute(
        select(VocabularyEntry.part_of_speech, func.count(VocabularyEntry.id))
        .where(VocabularyEntry.part_of_speech.is_not(None))
        .group_by(VocabularyEntry.part_of_speech)
        .order_by(func.count(VocabularyEntry.id).desc(), VocabularyEntry.part_of_speech)
    ).all()
    level_rows = session.execute(
        select(VocabularyEntry.cefr_level, func.count(VocabularyEntry.id))
        .where(VocabularyEntry.cefr_level.is_not(None))
        .group_by(VocabularyEntry.cefr_level)
        .order_by(VocabularyEntry.cefr_level)
    ).all()
    frequency_rows = session.execute(
        select(WordFrequency.frequency, func.count(WordFrequency.entry_id))
        .where(WordFrequency.frequency.is_not(None))
        .group_by(WordFrequency.frequency)
        .order_by(WordFrequency.frequency.desc())
    ).all()
    frequency_counts = {frequency: count for frequency, count in frequency_rows}
    frequency_children = [
        {
            "name": str(dimension["name"]),
            "tag_type": "词频重要性",
            "filter_type": "frequency_importance",
            "value": str(dimension["value"]),
            "count": sum(frequency_counts.get(score, 0) for score in dimension["scores"]),
        }
        for dimension in FREQUENCY_IMPORTANCE_DIMENSIONS
        if sum(frequency_counts.get(score, 0) for score in dimension["scores"])
    ]
    hidden_tag_names = {"名词", "noun", "verb", "adjective", "adverb", "conjunction", "der", "die", "das"}
    workflow_tag_names = {"已配图", "未配图", "跳过配图", "DeepSeek 生成", "手动录入", "CSV 导入", "需要复习", "重点", "易混淆"}
    def leaf_filter(name: str, tag_type: str, filter_type: str, count: int) -> dict[str, object]:
        return {"name": name, "tag_type": tag_type, "filter_type": filter_type, "count": count}

    def tree_node(node: dict[str, object], group_name: str) -> dict[str, object] | None:
        children = [tree_node(child, group_name) for child in node.get("children", [])]
        children = [child for child in children if child]
        tag_names = [tag for tag in node.get("tags", []) if tag_counts.get(tag)]
        leaves = [
            leaf_filter(tag_name, group_name, "tag", tag_counts[tag_name])
            for tag_name in tag_names
        ]
        for leaf, tag_name in zip(leaves, tag_names):
            leaf["value"] = tag_name
        if not children and len(leaves) == 1:
            return leaves[0]
        all_children = [*leaves, *children]
        if not all_children:
            return None
        result = {
            "name": node["name"],
            "tag_type": group_name,
            "filter_type": "group",
            "count": sum(child["count"] for child in children) + sum(child["count"] for child in leaves),
            "children": children or leaves,
        }
        if children and leaves:
            select_filter = leaves[0].copy()
            select_filter["name"] = f"全部{node['name']}"
            result["select_filter"] = select_filter
        return result

    def collect_tag_names(nodes: list[dict[str, object]]) -> set[str]:
        names = set()
        for node in nodes:
            names.update(node.get("tags", []))
            names.update(collect_tag_names(node.get("children", [])))
        return names

    grouped_names = collect_tag_names(topic_tree)
    goethe_count = sum(tag_counts.get(name, 0) for name in ("Goethe A1", "Goethe A2", "Goethe B1"))
    verb_type_names = ("反身动词", "非反身动词", "不规则动词")
    verb_type_count = sum(tag_counts.get(name, 0) for name in verb_type_names)

    groups = [
        {
            "name": "语言属性",
            "tag_type": "system",
            "filter_type": "group",
            "count": sum(count for _, count in pos_rows) + verb_type_count + sum(count for _, count in level_rows) + sum(frequency_counts.values()) + goethe_count,
            "children": [
                {
                    "name": "词性",
                    "tag_type": "system",
                    "filter_type": "group",
                    "count": sum(count for _, count in pos_rows),
                    "children": [
                        {"name": pos, "tag_type": "词性", "filter_type": "part_of_speech", "count": count}
                        for pos, count in pos_rows
                    ],
                },
                {
                    "name": "动词类型",
                    "tag_type": "system",
                    "filter_type": "group",
                    "count": verb_type_count,
                    "children": [
                        {
                            "name": name,
                            "tag_type": "语法" if name == "不规则动词" else "语言属性",
                            "filter_type": "tag",
                            "count": tag_counts[name],
                            "value": name,
                        }
                        for name in verb_type_names
                        if tag_counts.get(name)
                    ],
                },
                {
                    "name": "等级",
                    "tag_type": "system",
                    "filter_type": "group",
                    "count": sum(count for _, count in level_rows),
                    "children": [
                        {"name": level, "tag_type": "等级", "filter_type": "cefr_level", "count": count}
                        for level, count in level_rows
                    ],
                },
                {
                    "name": "Goethe 词表",
                    "tag_type": "system",
                    "filter_type": "group",
                    "count": goethe_count,
                    "children": [
                        {
                            "name": name,
                            "tag_type": "Goethe",
                            "filter_type": "tag",
                            "value": name,
                            "count": tag_counts[name],
                        }
                        for name in ("Goethe A1", "Goethe A2", "Goethe B1")
                        if tag_counts.get(name)
                    ],
                },
                *([
                    {
                        "name": "词频重要性",
                        "tag_type": "system",
                        "filter_type": "group",
                        "count": sum(frequency_counts.values()),
                        "children": frequency_children,
                    }
                ] if frequency_children else []),
            ],
        }
    ]
    for group in topic_tree:
        node = tree_node(group, group["name"])
        if node:
            groups.append(node)
    other_children = [
        {"name": name, "tag_type": "其他", "filter_type": "tag", "count": count}
        for name, count in user_tag_rows
        if name in workflow_tag_names and name not in grouped_names and name not in hidden_tag_names
    ]
    if other_children:
        groups.append(
            {
                "name": "学习管理",
                "tag_type": "workflow",
                "filter_type": "group",
                "count": sum(item["count"] for item in other_children),
                "children": other_children,
            }
        )
    return groups


@app.get("/api/entries", response_model=EntryListResponse)
def list_entries(
    q: str | None = Query(default=None),
    part_of_speech: list[str] = Query(default=[]),
    article: list[str] = Query(default=[]),
    cefr_level: list[str] = Query(default=[]),
    frequency_importance: list[str] = Query(default=[]),
    tag: list[str] = Query(default=[]),
    sort: str = Query(default="relevance", pattern="^(relevance|frequency_desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    if q:
        cleaned_query = q.strip()
        frequency_values = parse_frequency_importance_values(frequency_importance)
        if contains_cjk(cleaned_query):
            query_terms = expand_chinese_query_terms(cleaned_query)
            common_query_terms = set(expand_common_chinese_query_terms(cleaned_query))
            normalized_cleaned_query = normalize_similarity_text(cleaned_query)

            stmt = entry_query()
            if part_of_speech:
                stmt = stmt.where(VocabularyEntry.part_of_speech.in_(part_of_speech))
            if article:
                stmt = stmt.where(VocabularyEntry.article.in_(article))
            if cefr_level:
                stmt = stmt.where(VocabularyEntry.cefr_level.in_(cefr_level))
            if frequency_values:
                frequency_entry_ids = select(WordFrequency.entry_id).where(WordFrequency.frequency.in_(frequency_values))
                stmt = stmt.where(VocabularyEntry.id.in_(frequency_entry_ids))
            if tag:
                stmt = stmt.where(VocabularyEntry.tags.any(EntryTag.name.in_(tag)))

            candidate_entries = session.scalars(stmt).unique().all()

            original_scores = {
                entry.id: chinese_meaning_search_score(cleaned_query, entry)
                for entry in candidate_entries
            }
            has_strong_original_match = any(score >= 0.8 for score in original_scores.values())

            def semantic_chinese_score(entry: VocabularyEntry) -> float:
                scores = [original_scores.get(entry.id, 0.0)]
                for term in query_terms:
                    if term == normalized_cleaned_query:
                        continue
                    if len(cjk_char_set(normalized_cleaned_query)) >= 2 and len(cjk_char_set(term)) < 2:
                        continue
                    score = chinese_meaning_search_score(term, entry)
                    if term in common_query_terms:
                        score *= 0.82
                    else:
                        score *= 0.35 if has_strong_original_match else 0.7
                    scores.append(score)
                return max(scores, default=0.0)

            scored_entries = [
                (semantic_chinese_score(entry), entry)
                for entry in candidate_entries
            ]
            filtered_entries = [
                (score, entry)
                for score, entry in scored_entries
                if score >= 0.4
            ]
            filtered_entries.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
            if sort == "frequency_desc":
                filtered_ids = [entry.id for _, entry in filtered_entries]
                frequency_rows = session.execute(
                    select(WordFrequency.entry_id, WordFrequency.frequency, WordFrequency.hits)
                    .where(WordFrequency.entry_id.in_(filtered_ids))
                ).all()
                frequencies = {
                    entry_id: (frequency if frequency is not None else -1, hits or 0)
                    for entry_id, frequency, hits in frequency_rows
                }
                relevance_position = {entry.id: index for index, (_, entry) in enumerate(filtered_entries)}
                filtered_entries.sort(
                    key=lambda item: (
                        -frequencies.get(item[1].id, (-1, 0))[0],
                        -frequencies.get(item[1].id, (-1, 0))[1],
                        relevance_position[item[1].id],
                    )
                )
            page_entries = filtered_entries[offset : offset + limit]
            return EntryListResponse(
                items=[serialize_entry(entry, session=session) for _, entry in page_entries],
                total=len(filtered_entries),
                limit=limit,
                offset=offset,
            )

        query_candidates = unique_values([cleaned_query, *german_surface_candidates(cleaned_query)])
        folded_query = fold_german_umlauts(cleaned_query)
        fts_terms = unique_values(
            [
                *query_candidates,
                *(fold_german_umlauts(candidate) for candidate in query_candidates),
            ]
        )
        fts_query = " OR ".join(escape_fts_query(term) for term in fts_terms if term)
        params: dict[str, object] = {"query": fts_query}
        filters = []
        if part_of_speech:
            pos_keys = []
            for index, value in enumerate(part_of_speech):
                key = f"part_of_speech_{index}"
                pos_keys.append(f":{key}")
                params[key] = value
            filters.append(f"vocabulary_entries.part_of_speech IN ({', '.join(pos_keys)})")
        if article:
            article_keys = []
            for index, value in enumerate(article):
                key = f"article_{index}"
                article_keys.append(f":{key}")
                params[key] = value
            filters.append(f"vocabulary_entries.article IN ({', '.join(article_keys)})")
        if cefr_level:
            level_keys = []
            for index, value in enumerate(cefr_level):
                key = f"cefr_level_{index}"
                level_keys.append(f":{key}")
                params[key] = value
            filters.append(f"vocabulary_entries.cefr_level IN ({', '.join(level_keys)})")
        if frequency_values:
            frequency_keys = []
            for index, value in enumerate(frequency_values):
                key = f"frequency_importance_{index}"
                frequency_keys.append(f":{key}")
                params[key] = value
            filters.append(
                "EXISTS (SELECT 1 FROM word_frequencies WHERE word_frequencies.entry_id = vocabulary_entries.id "
                f"AND word_frequencies.frequency IN ({', '.join(frequency_keys)}))"
            )
        if tag:
            tag_keys = []
            for index, value in enumerate(tag):
                key = f"tag_{index}"
                tag_keys.append(f":{key}")
                params[key] = value
            filters.append(
                "EXISTS (SELECT 1 FROM entry_tags WHERE entry_tags.entry_id = vocabulary_entries.id AND entry_tags.name IN "
                f"({', '.join(tag_keys)}))"
            )
        where_sql = " AND ".join(["entry_search MATCH :query", *filters])
        rows = session.execute(
            text(
                f"""
                SELECT vocabulary_entries.id AS id,
                       bm25(entry_search, 8.0, 8.0, 7.0, 5.0, 3.0, 2.0, 1.5, 1.0) AS rank
                FROM entry_search
                JOIN vocabulary_entries ON vocabulary_entries.id = entry_search.entry_id
                WHERE {where_sql}
                ORDER BY
                    CASE WHEN lower(vocabulary_entries.normalized_lemma) = lower(:query_text) THEN 0 ELSE 1 END,
                    CASE WHEN lower(entry_search.folded_lemma) = lower(:folded_query_text) THEN 0 ELSE 1 END,
                    CASE WHEN lower(entry_search.folded_lemma) LIKE lower(:folded_query_prefix) THEN 0 ELSE 1 END,
                    CASE
                        WHEN lower(vocabulary_entries.normalized_lemma) LIKE lower(:query_word_prefix)
                          OR lower(vocabulary_entries.normalized_lemma) LIKE lower(:query_word_suffix)
                        THEN 0 ELSE 1
                    END,
                    CASE WHEN lower(vocabulary_entries.normalized_lemma) LIKE lower(:query_prefix) THEN 0 ELSE 1 END,
                    rank,
                    vocabulary_entries.updated_at DESC
                """
            ),
            {
                **params,
                "query_text": normalize_lemma(cleaned_query),
                "query_prefix": f"{normalize_lemma(cleaned_query)}%",
                "query_word_prefix": f"{normalize_lemma(cleaned_query)} %",
                "query_word_suffix": f"% {normalize_lemma(cleaned_query)}",
                "folded_query_text": folded_query,
                "folded_query_prefix": f"{folded_query}%",
            },
        ).all()
        ids = [row.id for row in rows]
        if ids:
            entries = session.scalars(entry_query().where(VocabularyEntry.id.in_(ids))).unique().all()
            by_id = {entry.id: entry for entry in entries}
            filtered_ids = [
                entry_id
                for entry_id in ids
                if entry_id in by_id and best_search_result_score(query_candidates, by_id[entry_id]) >= 0.18
            ]
            if sort == "frequency_desc":
                frequency_rows = session.execute(
                    select(WordFrequency.entry_id, WordFrequency.frequency, WordFrequency.hits)
                    .where(WordFrequency.entry_id.in_(filtered_ids))
                ).all()
                frequencies = {
                    entry_id: (frequency if frequency is not None else -1, hits or 0)
                    for entry_id, frequency, hits in frequency_rows
                }
                relevance_position = {entry_id: index for index, entry_id in enumerate(filtered_ids)}
                filtered_ids = sorted(
                    filtered_ids,
                    key=lambda entry_id: (
                        -frequencies.get(entry_id, (-1, 0))[0],
                        -frequencies.get(entry_id, (-1, 0))[1],
                        relevance_position[entry_id],
                    ),
                )
            page_ids = filtered_ids[offset : offset + limit]
            return EntryListResponse(
                items=[serialize_entry(by_id[entry_id], session=session) for entry_id in page_ids],
                total=len(filtered_ids),
                limit=limit,
                offset=offset,
            )

        fallback_patterns = [f"%{candidate}%" for candidate in query_candidates]
        pattern = fallback_patterns[0]
        stmt = entry_query().where(
            or_(
                *[
                    condition
                    for candidate_pattern in fallback_patterns
                    for condition in (
                        VocabularyEntry.lemma.ilike(candidate_pattern),
                        VocabularyEntry.searchable_text.ilike(candidate_pattern),
                    )
                ]
            )
        )
    else:
        stmt = entry_query()
    if part_of_speech:
        stmt = stmt.where(VocabularyEntry.part_of_speech.in_(part_of_speech))
    if article:
        stmt = stmt.where(VocabularyEntry.article.in_(article))
    if cefr_level:
        stmt = stmt.where(VocabularyEntry.cefr_level.in_(cefr_level))
    frequency_values = parse_frequency_importance_values(frequency_importance)
    if frequency_values:
        frequency_entry_ids = select(WordFrequency.entry_id).where(WordFrequency.frequency.in_(frequency_values))
        stmt = stmt.where(VocabularyEntry.id.in_(frequency_entry_ids))
    if tag:
        stmt = stmt.where(VocabularyEntry.tags.any(EntryTag.name.in_(tag)))
    if sort == "frequency_desc":
        stmt = (
            stmt.order_by(None)
            .outerjoin(WordFrequency, WordFrequency.entry_id == VocabularyEntry.id)
            .order_by(
                WordFrequency.frequency.is_(None),
                WordFrequency.frequency.desc(),
                WordFrequency.hits.desc(),
                VocabularyEntry.updated_at.desc(),
            )
        )
    count_stmt = select(func.count(func.distinct(VocabularyEntry.id))).select_from(VocabularyEntry)
    if q:
        count_stmt = count_stmt.where(
            or_(
                *[
                    condition
                    for candidate_pattern in fallback_patterns
                    for condition in (
                        VocabularyEntry.lemma.ilike(candidate_pattern),
                        VocabularyEntry.searchable_text.ilike(candidate_pattern),
                    )
                ]
            )
        )
    if part_of_speech:
        count_stmt = count_stmt.where(VocabularyEntry.part_of_speech.in_(part_of_speech))
    if article:
        count_stmt = count_stmt.where(VocabularyEntry.article.in_(article))
    if cefr_level:
        count_stmt = count_stmt.where(VocabularyEntry.cefr_level.in_(cefr_level))
    if frequency_values:
        frequency_entry_ids = select(WordFrequency.entry_id).where(WordFrequency.frequency.in_(frequency_values))
        count_stmt = count_stmt.where(VocabularyEntry.id.in_(frequency_entry_ids))
    if tag:
        count_stmt = count_stmt.where(VocabularyEntry.tags.any(EntryTag.name.in_(tag)))
    total = session.scalar(count_stmt) or 0
    stmt = stmt.offset(offset).limit(limit)
    entries = session.scalars(stmt).unique().all()
    return EntryListResponse(
        items=[serialize_entry(entry, session=session) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/api/entries/browse", response_model=EntryListResponse)
def browse_entries(
    part_of_speech: str = Query(default="noun"),
    noun_gender: str = Query(default="all", pattern="^(all|masculine|feminine|neuter)$"),
    sort: str = Query(default="alphabet_asc", pattern="^(alphabet_asc|alphabet_desc|frequency_desc|frequency_asc)$"),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = entry_query()
    count_stmt = select(func.count(func.distinct(VocabularyEntry.id))).select_from(VocabularyEntry)

    if part_of_speech and part_of_speech != "all":
        if part_of_speech == "noun":
            pos_filter = or_(
                VocabularyEntry.part_of_speech == "noun",
                VocabularyEntry.article.in_(["der", "die", "das"]),
                VocabularyEntry.gender.in_(["masculine", "feminine", "neuter", "der", "die", "das"]),
            )
        else:
            pos_filter = VocabularyEntry.part_of_speech == part_of_speech
        stmt = stmt.where(pos_filter)
        count_stmt = count_stmt.where(pos_filter)

    if noun_gender != "all":
        article_by_gender = {
            "masculine": "der",
            "feminine": "die",
            "neuter": "das",
        }
        gender_filter = or_(
            VocabularyEntry.gender == noun_gender,
            VocabularyEntry.gender == article_by_gender[noun_gender],
            VocabularyEntry.article == article_by_gender[noun_gender],
        )
        stmt = stmt.where(gender_filter)
        count_stmt = count_stmt.where(gender_filter)

    if sort.startswith("frequency"):
        stmt = stmt.order_by(None).outerjoin(WordFrequency, WordFrequency.entry_id == VocabularyEntry.id)
        if sort == "frequency_desc":
            stmt = stmt.order_by(
                WordFrequency.hits.is_(None),
                WordFrequency.hits.desc(),
                WordFrequency.frequency.desc(),
                func.lower(VocabularyEntry.lemma),
            )
        else:
            stmt = stmt.order_by(
                WordFrequency.hits.is_(None),
                WordFrequency.hits.asc(),
                WordFrequency.frequency.asc(),
                func.lower(VocabularyEntry.lemma),
            )
    else:
        lemma_order = func.lower(VocabularyEntry.lemma).desc() if sort == "alphabet_desc" else func.lower(VocabularyEntry.lemma).asc()
        stmt = stmt.order_by(None).order_by(lemma_order, VocabularyEntry.updated_at.desc())

    total = session.scalar(count_stmt) or 0
    entries = session.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return EntryListResponse(
        items=[serialize_entry(entry, session=session) for entry in entries],
        total=total,
        limit=limit,
        offset=offset,
    )


@app.get("/api/entries/{entry_id}", response_model=EntryResponse)
def get_entry(entry_id: int, session: Session = Depends(get_session)):

    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return serialize_entry(entry, session=session)


@app.get("/api/entries/{entry_id}/frequency")
def get_entry_frequency_endpoint(
    entry_id: int,
    session: Session = Depends(get_session),
) -> WordFrequencyResponse:
    """Get DWDS frequency data for an entry, fetching from API if not cached."""
    entry = session.get(VocabularyEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    result = get_entry_frequency(session, entry)
    if not result:
        return {"q": entry.lemma, "lemma": entry.lemma, "frequency": None, "hits": None, "total": None}
    return result


@app.post("/api/frequencies/fetch-batch", response_model=dict[int, WordFrequencyResponse])
def fetch_frequencies_batch(
    entry_ids: list[int] = Body(...),
    session: Session = Depends(get_session),
) -> dict[int, WordFrequencyResponse]:
    """Fetch DWDS frequencies for multiple entries in batch."""
    unique_ids = list(dict.fromkeys(entry_ids))
    if len(unique_ids) > 100:
        raise HTTPException(status_code=400, detail="一次最多批量获取 100 个词频")
    entries = session.scalars(
        select(VocabularyEntry).where(VocabularyEntry.id.in_(unique_ids))
    ).all()
    results: dict[int, dict] = {}
    for entry in entries:
        result = get_entry_frequency(session, entry)
        if result:
            results[entry.id] = result
        else:
            results[entry.id] = {"q": entry.lemma, "lemma": entry.lemma, "frequency": None, "hits": None, "total": None}
    return results


@app.post("/api/frequencies/refresh-existing")
def refresh_existing_frequencies(
    limit: int = Query(default=500, ge=1, le=500),
    session: Session = Depends(get_session),
):
    """Refresh DWDS frequencies for entries that already have cached frequency data."""
    total_existing = session.scalar(select(func.count(WordFrequency.entry_id))) or 0
    entries = session.scalars(
        select(VocabularyEntry)
        .join(WordFrequency, WordFrequency.entry_id == VocabularyEntry.id)
        .order_by(WordFrequency.updated_at.asc())
        .limit(limit)
    ).all()
    results: dict[int, dict] = {}
    failed_ids: list[int] = []
    for entry in entries:
        result = get_entry_frequency(session, entry, force_refresh=True)
        if result:
            results[entry.id] = result
        else:
            failed_ids.append(entry.id)
    return {
        "total_existing": total_existing,
        "requested_count": len(entries),
        "updated_count": len(results),
        "failed_count": len(failed_ids),
        "failed_ids": failed_ids,
        "results": results,
    }


@app.post("/api/frequencies/fetch-missing")
def fetch_missing_frequencies(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=40, ge=1, le=100),
    delay_ms: int = Query(default=350, ge=0, le=3000),
    session: Session = Depends(get_session),
):
    """Fetch DWDS frequencies for entries without cached frequency data, moving forward by id."""
    cached_entry_ids = select(WordFrequency.entry_id)
    total_missing_before = session.scalar(
        select(func.count(VocabularyEntry.id)).where(~VocabularyEntry.id.in_(cached_entry_ids))
    ) or 0
    entries = session.scalars(
        select(VocabularyEntry)
        .where(VocabularyEntry.id > cursor)
        .where(~VocabularyEntry.id.in_(cached_entry_ids))
        .order_by(VocabularyEntry.id.asc())
        .limit(limit)
    ).all()
    results: dict[int, dict] = {}
    failed_ids: list[int] = []
    attempted_ids: list[int] = []
    last_id = cursor
    for index, entry in enumerate(entries):
        attempted_ids.append(entry.id)
        last_id = entry.id
        result = get_entry_frequency(session, entry)
        if result:
            results[entry.id] = result
        else:
            failed_ids.append(entry.id)
        if delay_ms and index < len(entries) - 1:
            time.sleep(delay_ms / 1000)
    has_more = bool(
        session.scalar(
            select(VocabularyEntry.id)
            .where(VocabularyEntry.id > last_id)
            .where(~VocabularyEntry.id.in_(cached_entry_ids))
            .order_by(VocabularyEntry.id.asc())
            .limit(1)
        )
    )
    remaining_missing = session.scalar(
        select(func.count(VocabularyEntry.id)).where(~VocabularyEntry.id.in_(cached_entry_ids))
    ) or 0
    return {
        "cursor": last_id,
        "has_more": has_more,
        "total_missing_before": total_missing_before,
        "remaining_missing": remaining_missing,
        "attempted_count": len(attempted_ids),
        "updated_count": len(results),
        "failed_count": len(failed_ids),
        "attempted_ids": attempted_ids,
        "failed_ids": failed_ids,
        "results": results,
    }


def frequency_missing_count(session: Session) -> int:
    cached_entry_ids = select(WordFrequency.entry_id)
    return session.scalar(
        select(func.count(VocabularyEntry.id)).where(~VocabularyEntry.id.in_(cached_entry_ids))
    ) or 0


def frequency_status_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(WordFrequency.status, func.count(WordFrequency.id))
        .group_by(WordFrequency.status)
    ).all()
    return {status or "unknown": count for status, count in rows}


def entry_has_meaning(entry: VocabularyEntry, language: str) -> bool:
    return any(item.language == language and item.gloss.strip() for item in entry.meanings)


def meaning_backfill_target_query(cursor: int = 0):
    goethe_tagged = VocabularyEntry.tags.any(EntryTag.name.in_(["Goethe A1", "Goethe A2", "Goethe B1"]))
    missing_zh = ~VocabularyEntry.meanings.any(Meaning.language == "zh")
    missing_en = ~VocabularyEntry.meanings.any(Meaning.language == "en")
    return (
        entry_query()
        .where(VocabularyEntry.id > cursor)
        .where((goethe_tagged & missing_zh) | missing_en)
        .order_by(None)
        .order_by(VocabularyEntry.id.asc())
    )


def meaning_backfill_remaining_count(session: Session) -> int:
    goethe_tagged = VocabularyEntry.tags.any(EntryTag.name.in_(["Goethe A1", "Goethe A2", "Goethe B1"]))
    missing_zh = ~VocabularyEntry.meanings.any(Meaning.language == "zh")
    missing_en = ~VocabularyEntry.meanings.any(Meaning.language == "en")
    return session.scalar(
        select(func.count(VocabularyEntry.id)).where((goethe_tagged & missing_zh) | missing_en)
    ) or 0


def normalize_glosses(value) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    cleaned: list[str] = []
    for item in items:
        text_value = str(item).strip()
        if text_value and text_value not in cleaned:
            cleaned.append(text_value[:255])
    return cleaned[:3]


def build_meaning_searchable_text(entry: VocabularyEntry) -> str:
    chunks = [
        entry.lemma or "",
        entry.part_of_speech or "",
        entry.word_category or "",
        entry.article or "",
        entry.plural_form or "",
        entry.notes or "",
    ]
    chunks.extend(item.gloss for item in entry.meanings)
    chunks.extend(item.detail or "" for item in entry.meanings)
    chunks.extend(item.value for item in entry.forms)
    chunks.extend(item.phrase for item in entry.collocations)
    chunks.extend(item.german_text for item in entry.examples)
    chunks.extend(item.chinese_text or "" for item in entry.examples)
    chunks.extend(item.name for item in entry.tags)
    return " ".join(chunk for chunk in chunks if chunk)


def set_meaning_backfill_job(**updates) -> None:
    with MEANING_BACKFILL_LOCK:
        MEANING_BACKFILL_JOB.update(updates)


def meaning_backfill_snapshot(session: Session | None = None) -> dict:
    with MEANING_BACKFILL_LOCK:
        snapshot = dict(MEANING_BACKFILL_JOB)
    if session is not None:
        snapshot["remaining_count"] = meaning_backfill_remaining_count(session)
    return snapshot


def set_frequency_backfill_job(**updates) -> None:
    with FREQUENCY_BACKFILL_LOCK:
        FREQUENCY_BACKFILL_JOB.update(updates)


def frequency_backfill_snapshot(session: Session | None = None) -> dict:
    with FREQUENCY_BACKFILL_LOCK:
        snapshot = dict(FREQUENCY_BACKFILL_JOB)
    if session is not None:
        snapshot["remaining_count"] = frequency_missing_count(session)
        snapshot["status_counts"] = frequency_status_counts(session)
    return snapshot


def run_frequency_backfill(batch_size: int, delay_ms: int) -> None:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    with SessionLocal() as session:
        total_target = frequency_missing_count(session)
        set_frequency_backfill_job(
            status="running",
            started_at=started_at,
            finished_at=None,
            total_target=total_target,
            attempted_count=0,
            success_count=0,
            no_result_count=0,
            failed_count=0,
            remaining_count=total_target,
            last_entry_id=None,
            last_lemma=None,
            error=None,
        )
        try:
            while True:
                cached_entry_ids = select(WordFrequency.entry_id)
                entries = session.scalars(
                    select(VocabularyEntry)
                    .where(~VocabularyEntry.id.in_(cached_entry_ids))
                    .order_by(VocabularyEntry.id.asc())
                    .limit(batch_size)
                ).all()
                if not entries:
                    break
                for entry in entries:
                    result = get_entry_frequency(session, entry)
                    with FREQUENCY_BACKFILL_LOCK:
                        FREQUENCY_BACKFILL_JOB["attempted_count"] += 1
                        if result.get("status") == "success":
                            FREQUENCY_BACKFILL_JOB["success_count"] += 1
                        elif result.get("status") == "no_result":
                            FREQUENCY_BACKFILL_JOB["no_result_count"] += 1
                        else:
                            FREQUENCY_BACKFILL_JOB["failed_count"] += 1
                        FREQUENCY_BACKFILL_JOB["last_entry_id"] = entry.id
                        FREQUENCY_BACKFILL_JOB["last_lemma"] = entry.lemma
                    if delay_ms:
                        time.sleep(delay_ms / 1000)
                set_frequency_backfill_job(remaining_count=frequency_missing_count(session))
            set_frequency_backfill_job(
                status="completed",
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                remaining_count=frequency_missing_count(session),
            )
        except Exception as exc:
            set_frequency_backfill_job(
                status="failed",
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                error=str(exc),
                remaining_count=frequency_missing_count(session),
            )


def run_meaning_backfill(batch_size: int, delay_ms: int) -> None:
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    system_prompt = """
You are a precise German vocabulary editor.
Return only valid JSON. No markdown.
For each item, provide concise learner-friendly meanings.
JSON shape:
{
  "items": [
    {"id": 123, "zh": ["中文释义1", "中文释义2"], "en": ["English meaning 1", "English meaning 2"]}
  ]
}
Only fill requested languages. If a language is not requested, return an empty array for it.
Keep each gloss short: no examples, no markdown, no numbering.
"""
    with SessionLocal() as session:
        total_target = meaning_backfill_remaining_count(session)
        set_meaning_backfill_job(
            status="running",
            started_at=started_at,
            finished_at=None,
            total_target=total_target,
            attempted_count=0,
            updated_count=0,
            failed_count=0,
            remaining_count=total_target,
            last_entry_id=None,
            last_lemma=None,
            error=None,
        )
        try:
            cursor = 0
            while True:
                entries = session.scalars(meaning_backfill_target_query(cursor).limit(batch_size)).unique().all()
                if not entries:
                    break
                cursor = max(entry.id for entry in entries)
                request_items = []
                by_id = {entry.id: entry for entry in entries}
                for entry in entries:
                    needs_zh = any(tag.name in {"Goethe A1", "Goethe A2", "Goethe B1"} for tag in entry.tags) and not entry_has_meaning(entry, "zh")
                    needs_en = not entry_has_meaning(entry, "en")
                    existing_zh = [item.gloss for item in entry.meanings if item.language == "zh"]
                    request_items.append(
                        {
                            "id": entry.id,
                            "lemma": entry.lemma,
                            "part_of_speech": entry.part_of_speech,
                            "article": entry.article,
                            "gender": entry.gender,
                            "cefr_level": entry.cefr_level,
                            "needs_zh": needs_zh,
                            "needs_en": needs_en,
                            "existing_zh": existing_zh[:3],
                        }
                    )
                user_prompt = "Fill missing meanings for these German vocabulary entries:\n" + json.dumps(
                    {"items": request_items},
                    ensure_ascii=False,
                )
                try:
                    parsed = call_deepseek_json(system_prompt, user_prompt, max_tokens=max(1200, batch_size * 180))
                    response_items = parsed.get("items")
                    if not isinstance(response_items, list):
                        raise ValueError("DeepSeek JSON must contain an items array")
                except Exception as exc:
                    with MEANING_BACKFILL_LOCK:
                        MEANING_BACKFILL_JOB["failed_count"] += len(entries)
                        MEANING_BACKFILL_JOB["attempted_count"] += len(entries)
                        MEANING_BACKFILL_JOB["error"] = str(exc)
                        MEANING_BACKFILL_JOB["last_entry_id"] = entries[-1].id
                        MEANING_BACKFILL_JOB["last_lemma"] = entries[-1].lemma
                    if delay_ms:
                        time.sleep(delay_ms / 1000)
                    continue

                updated_entries = 0
                for item in response_items:
                    if not isinstance(item, dict):
                        continue
                    try:
                        entry_id = int(item.get("id"))
                    except (TypeError, ValueError):
                        continue
                    entry = by_id.get(entry_id)
                    if not entry:
                        continue
                    added = 0
                    next_sort_order = len(entry.meanings)
                    if not entry_has_meaning(entry, "zh"):
                        for gloss in normalize_glosses(item.get("zh")):
                            entry.meanings.append(
                                Meaning(language="zh", gloss=gloss, sort_order=next_sort_order)
                            )
                            next_sort_order += 1
                            added += 1
                    if not entry_has_meaning(entry, "en"):
                        for gloss in normalize_glosses(item.get("en")):
                            entry.meanings.append(
                                Meaning(language="en", gloss=gloss, sort_order=next_sort_order)
                            )
                            next_sort_order += 1
                            added += 1
                    if added:
                        extra_data = dict(entry.extra_data or {})
                        extra_data["meaning_backfilled_by"] = DEEPSEEK_MODEL
                        entry.extra_data = extra_data
                        entry.searchable_text = build_meaning_searchable_text(entry)
                        sync_entry_search(session, entry)
                        updated_entries += 1
                    with MEANING_BACKFILL_LOCK:
                        MEANING_BACKFILL_JOB["last_entry_id"] = entry.id
                        MEANING_BACKFILL_JOB["last_lemma"] = entry.lemma
                session.commit()
                set_meaning_backfill_job(
                    attempted_count=MEANING_BACKFILL_JOB["attempted_count"] + len(entries),
                    updated_count=MEANING_BACKFILL_JOB["updated_count"] + updated_entries,
                    remaining_count=meaning_backfill_remaining_count(session),
                )
                if delay_ms:
                    time.sleep(delay_ms / 1000)
            set_meaning_backfill_job(
                status="completed",
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                remaining_count=meaning_backfill_remaining_count(session),
            )
        except Exception as exc:
            set_meaning_backfill_job(
                status="failed",
                finished_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                error=str(exc),
                remaining_count=meaning_backfill_remaining_count(session),
            )


@app.post("/api/frequencies/backfill/start")
def start_frequency_backfill(
    batch_size: int = Query(default=40, ge=1, le=100),
    delay_ms: int = Query(default=350, ge=0, le=3000),
    session: Session = Depends(get_session),
):
    already_running = False
    with FREQUENCY_BACKFILL_LOCK:
        if FREQUENCY_BACKFILL_JOB["status"] == "running":
            already_running = True
        else:
            FREQUENCY_BACKFILL_JOB["status"] = "starting"
    if already_running:
        return frequency_backfill_snapshot(session)
    thread = Thread(
        target=run_frequency_backfill,
        args=(batch_size, delay_ms),
        daemon=True,
    )
    thread.start()
    return frequency_backfill_snapshot(session)


@app.get("/api/frequencies/backfill/status")
def get_frequency_backfill_status(session: Session = Depends(get_session)):
    return frequency_backfill_snapshot(session)


@app.post("/api/meanings/backfill/start")
def start_meaning_backfill(
    batch_size: int = Query(default=15, ge=1, le=30),
    delay_ms: int = Query(default=1200, ge=0, le=10000),
    session: Session = Depends(get_session),
):
    already_running = False
    with MEANING_BACKFILL_LOCK:
        if MEANING_BACKFILL_JOB["status"] == "running":
            already_running = True
        else:
            MEANING_BACKFILL_JOB["status"] = "starting"
    if already_running:
        return meaning_backfill_snapshot(session)
    thread = Thread(
        target=run_meaning_backfill,
        args=(batch_size, delay_ms),
        daemon=True,
    )
    thread.start()
    return meaning_backfill_snapshot(session)


@app.get("/api/meanings/backfill/status")
def get_meaning_backfill_status(session: Session = Depends(get_session)):
    return meaning_backfill_snapshot(session)



@app.get("/api/image-workbench/nouns", response_model=list[EntryResponse])
def image_workbench_nouns(
    missing_only: bool = Query(default=True),
    limit: int = Query(default=80, ge=1, le=200),
    session: Session = Depends(get_session),
):
    stmt = entry_query().where(VocabularyEntry.part_of_speech == "noun")
    stmt = stmt.where(
        or_(
            VocabularyEntry.extra_data.is_(None),
            VocabularyEntry.extra_data["image_skip"].as_boolean().is_not(True),
        )
    )
    if missing_only:
        stmt = stmt.where(
            ~select(EntryImage.id)
            .where(EntryImage.entry_id == VocabularyEntry.id)
            .exists()
        )
    entries = session.scalars(stmt.limit(limit * 4)).unique().all()
    concrete_entries = [entry for entry in entries if entry_is_concrete_noun(entry)][:limit]
    return [serialize_entry(entry) for entry in concrete_entries]


@app.get("/api/irregular-verbs", response_model=IrregularVerbListResponse)
def list_irregular_verbs(
    q: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    stmt = select(IrregularVerb).order_by(IrregularVerb.infinitive)
    count_stmt = select(func.count(IrregularVerb.id))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        criteria = or_(
            IrregularVerb.infinitive.ilike(pattern),
            IrregularVerb.present.ilike(pattern),
            IrregularVerb.preterite.ilike(pattern),
            IrregularVerb.participle_ii.ilike(pattern),
            IrregularVerb.meaning_zh.ilike(pattern),
        )
        stmt = stmt.where(criteria)
        count_stmt = count_stmt.where(criteria)
    total = session.scalar(count_stmt) or 0
    verbs = session.scalars(stmt.offset(offset).limit(limit)).all()
    return IrregularVerbListResponse(
        items=[serialize_irregular_verb(verb) for verb in verbs],
        total=total,
    )


@app.get("/api/export/anki/irregular-verbs")
def export_irregular_verbs_anki(session: Session = Depends(get_session)):
    verbs = session.scalars(select(IrregularVerb).order_by(IrregularVerb.infinitive)).all()
    content = build_irregular_verbs_anki_tsv(verbs, vocabulary_meanings_by_infinitive(session, verbs))
    return Response(
        content=content,
        media_type="text/tab-separated-values; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="irregular_verbs_anki.tsv"',
        },
    )


@app.get("/api/irregular-verbs/quiz", response_model=list[IrregularVerbQuizItem])
def irregular_verb_quiz(
    limit: int = Query(default=10, ge=1, le=50),
    mode: str = Query(default="mixed"),
    session: Session = Depends(get_session),
):
    verbs = session.scalars(select(IrregularVerb)).all()
    random.shuffle(verbs)
    items = []
    for verb in verbs[:limit]:
        prompt_field = "infinitive"
        prompt_value = verb.infinitive
        if mode == "participle":
            prompt_field = "participle_ii"
            prompt_value = verb.participle_ii
        elif mode == "preterite":
            prompt_field = "preterite"
            prompt_value = verb.preterite
        items.append(
            IrregularVerbQuizItem(
                id=verb.id,
                prompt_field=prompt_field,
                prompt_value=prompt_value,
                infinitive=verb.infinitive,
                present=verb.present,
                preterite=verb.preterite,
                participle_ii=verb.participle_ii,
                auxiliary=verb.auxiliary,
                meaning_zh=verb.meaning_zh,
            )
        )
    return items


@app.get("/api/entries/{entry_id}/images/query")
def get_entry_image_query(entry_id: int, session: Session = Depends(get_session)):
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    query = generate_image_search_query(entry)
    if query and isinstance(entry.extra_data, dict) and entry.extra_data.get("image_search_query") != query:
        entry.extra_data = {**(entry.extra_data or {}), "image_search_query": query}
        session.add(entry)
        session.commit()
    return {"query": query}


@app.post("/api/entries/{entry_id}/images/skip")
def skip_entry_image_work(entry_id: int, session: Session = Depends(get_session)):
    with WRITE_LOCK:
        entry = session.get(VocabularyEntry, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        entry.extra_data = {**(entry.extra_data or {}), "image_skip": True}
        session.add(entry)
        session.commit()
    return {"skipped": True}


@app.get("/api/entries/{entry_id}/similar", response_model=list[SimilarEntryResponse])
def get_similar_entries(
    entry_id: int,
    limit: int = Query(default=8, ge=1, le=30),
    session: Session = Depends(get_session),
):
    entry = session.get(VocabularyEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return calculate_similar_entries(session, entry_id, limit)


@app.get("/api/entries/{entry_id}/images/candidates", response_model=list[EntryImageCandidate])
def get_entry_image_candidates(
    entry_id: int,
    q: str | None = Query(default=None),
    limit: int = Query(default=9, ge=1, le=12),
    session: Session = Depends(get_session),
):
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    search_query = (q or clean_image_query(entry)).strip()
    if not search_query:
        raise HTTPException(status_code=400, detail="没有可用于图片搜索的词条")
    try:
        return wikimedia_search_images(search_query, limit=limit)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"Wikimedia 图片搜索失败: {exc}") from exc


@app.post("/api/entries/{entry_id}/images/select", response_model=EntryResponse)
def select_entry_image(
    entry_id: int,
    candidate: EntryImageSelectRequest,
    session: Session = Depends(get_session),
):
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    item = candidate.model_dump()
    with WRITE_LOCK:
        if any(image.source_url == item["source_url"] for image in entry.images):
            return serialize_entry(entry)
        try:
            image = download_entry_image(entry_id, item, len(entry.images) + 1)
        except urllib.error.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"选中图片下载失败: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise HTTPException(status_code=502, detail=f"选中图片下载失败: {exc.reason}") from exc
        session.add(image)
        session.commit()
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    return serialize_entry(entry)


@app.post("/api/entries/{entry_id}/images/fetch", response_model=EntryResponse)
def fetch_entry_images(
    entry_id: int,
    q: str | None = Query(default=None),
    limit: int = Query(default=3, ge=1, le=6),
    force: bool = Query(default=False),
    download: bool = Query(default=False),
    session: Session = Depends(get_session),
):
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.images and not force:
        return serialize_entry(entry)

    search_query = (q or clean_image_query(entry)).strip()
    if not search_query:
        raise HTTPException(status_code=400, detail="没有可用于图片搜索的词条")

    try:
        candidates = wikimedia_search_images(search_query, limit=limit)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"Wikimedia 图片搜索失败: {exc}") from exc
    if not candidates:
        raise HTTPException(status_code=404, detail="没有找到合适的 Wikimedia Commons 图片")

    existing_sources = {image.source_url for image in entry.images}
    downloaded = 0
    skipped_errors = []
    with WRITE_LOCK:
        if force:
            for image in list(entry.images):
                local_file = MEDIA_DIR / image.local_path if not image.local_path.startswith(("http://", "https://")) else None
                if local_file and local_file.exists():
                    local_file.unlink()
                session.delete(image)
            session.flush()
            entry.images = []
            existing_sources = set()
        for index, candidate in enumerate(candidates, start=1):
            if candidate["source_url"] in existing_sources:
                continue
            try:
                image = (
                    download_entry_image(entry_id, candidate, len(entry.images) + index)
                    if download
                    else remote_entry_image(entry_id, candidate)
                )
            except urllib.error.HTTPError as exc:
                skipped_errors.append(f"{candidate.get('title') or candidate['source_url']}: HTTP {exc.code}")
                if exc.code == 429:
                    time.sleep(1.2)
                continue
            except urllib.error.URLError as exc:
                skipped_errors.append(f"{candidate.get('title') or candidate['source_url']}: {exc.reason}")
                continue
            session.add(image)
            downloaded += 1
            if download:
                time.sleep(0.35)
        session.commit()
    if downloaded == 0 and not entry.images:
        detail = "Wikimedia 图片下载失败"
        if skipped_errors:
            detail += "：" + "；".join(skipped_errors[:3])
        raise HTTPException(status_code=502, detail=detail)
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry_id)).first()
    return serialize_entry(entry)


@app.post("/api/entries/draft/deepseek", response_model=EntryResponse | EntryCreate)
def create_deepseek_entry_draft(payload: EntryDraftRequest, session: Session = Depends(get_session)):
    lemma = payload.lemma.strip()
    if not lemma:
        raise HTTPException(status_code=400, detail="lemma 不能为空")
    existing, resolved_lemma, _reason = resolve_existing_entry_from_surface(session, lemma)
    if existing:
        return serialize_entry(existing)
    draft = generate_entry_draft_with_deepseek(resolved_lemma or lemma)
    return enrich_verb_forms(draft, session)


@app.post("/api/entries/resolve", response_model=EntryResolveResponse)
def resolve_entry_surface(payload: EntryResolveRequest, session: Session = Depends(get_session)):
    lemma = payload.lemma.strip()
    if not lemma:
        raise HTTPException(status_code=400, detail="lemma 不能为空")
    entry, resolved_lemma, reason = resolve_existing_entry_from_surface(session, lemma)
    return EntryResolveResponse(
        lemma=lemma,
        resolved_lemma=resolved_lemma,
        reason=reason,
        entry=serialize_entry(entry, session) if entry else None,
    )


@app.post("/api/entries", response_model=EntryResponse)
def create_entry(payload: EntryCreate, session: Session = Depends(get_session)):
    with WRITE_LOCK:
        entry = apply_payload(VocabularyEntry(lemma="", normalized_lemma=""), payload)
        session.add(entry)
        session.flush()
        sync_entry_search(session, entry)
        session.commit()
        session.refresh(entry)
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry.id)).first()
    return serialize_entry(entry)


@app.put("/api/entries/{entry_id}", response_model=EntryResponse)
def update_entry(entry_id: int, payload: EntryUpdate, session: Session = Depends(get_session)):
    with WRITE_LOCK:
        entry = session.get(VocabularyEntry, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        apply_payload(entry, payload, session=session)
        session.add(entry)
        session.flush()
        sync_entry_search(session, entry)
        session.commit()
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry.id)).first()
    return serialize_entry(entry)


@app.patch("/api/entries/{entry_id}/notes", response_model=EntryResponse)
def update_entry_notes(entry_id: int, payload: EntryNotesUpdate, session: Session = Depends(get_session)):
    with WRITE_LOCK:
        entry = session.get(VocabularyEntry, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        entry.notes = payload.notes.strip() if payload.notes and payload.notes.strip() else None
        session.add(entry)
        session.flush()
        sync_entry_search(session, entry)
        session.commit()
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry.id)).first()
    return serialize_entry(entry)


@app.post("/api/entries/{entry_id}/mastery/review", response_model=WordMasteryReviewResponse)
def review_entry_mastery(
    entry_id: int,
    payload: WordMasteryReviewRequest,
    session: Session = Depends(get_session),
):
    rating = payload.rating.strip()
    if rating not in MASTERY_RATING_DELTAS:
        raise HTTPException(status_code=422, detail="rating 必须是 again / hard / easy / simple")
    score_delta = MASTERY_RATING_DELTAS[rating]
    source = payload.source.strip() or "detail_self_review"
    now = datetime.utcnow()

    with WRITE_LOCK:
        entry = session.get(VocabularyEntry, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        event = WordMasteryEvent(
            word_id=entry_id,
            rating=rating,
            score_delta=score_delta,
            source=source,
            created_at=now,
        )
        session.add(event)

        mastery = session.get(WordMastery, entry_id)
        if not mastery:
            mastery = WordMastery(word_id=entry_id, current_score=0, current_level="new / weak")
            session.add(mastery)
        mastery.current_score = (mastery.current_score or 0) + score_delta
        mastery.current_level = mastery_level_for_score(mastery.current_score)
        mastery.last_rating = rating
        mastery.last_reviewed_at = now
        mastery.review_count = (mastery.review_count or 0) + 1
        mastery.updated_at = now
        session.flush()
        session.refresh(event)
        session.refresh(mastery)
        session.commit()

    return WordMasteryReviewResponse(
        event=serialize_mastery_event(event),
        mastery=serialize_mastery(mastery),
    )


@app.delete("/api/entries/{entry_id}")
def delete_entry(entry_id: int, session: Session = Depends(get_session)):
    with WRITE_LOCK:
        entry = session.get(VocabularyEntry, entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Entry not found")
        session.execute(text("DELETE FROM entry_search WHERE entry_id = :entry_id"), {"entry_id": entry_id})
        session.execute(delete(EntrySimilarity).where(or_(EntrySimilarity.source_entry_id == entry_id, EntrySimilarity.target_entry_id == entry_id)))
        session.delete(entry)
        session.commit()
    return {"deleted": True}


def json_word_to_payload(item: dict) -> EntryCreate:
    meanings = []
    for m in item.get("meaning", []):
        if m.get("zh"):
            meanings.append({"language": "zh", "gloss": m["zh"]})
        if m.get("en"):
            meanings.append({"language": "en", "gloss": m["en"]})
    forms = []
    if item.get("plural"):
        forms.append({"label": "plural", "value": item["plural"]})
    examples = [
        {"german_text": ex["de"], "chinese_text": ex.get("zh")}
        for ex in item.get("examples", [])
        if ex.get("de")
    ]
    collocations = [{"phrase": c} for c in item.get("collocations", []) if c]
    tags = [{"name": t} for t in item.get("tags", []) if t]
    pos_list = item.get("pos", [])
    return EntryCreate(
        lemma=item.get("lemma") or item.get("word", ""),
        language="de",
        part_of_speech=pos_list[0] if pos_list else None,
        gender=item.get("gender"),
        cefr_level=item.get("level"),
        source_type="json",
        meanings=meanings,
        forms=forms,
        collocations=collocations,
        examples=examples,
        tags=tags,
        raw_payload=item,
    )


@app.post("/api/import/json", response_model=ImportResult)
async def import_json(file: UploadFile = File(...), session: Session = Depends(get_session)):
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"无效 JSON: {exc}")
    if not isinstance(data, list):
        raise HTTPException(status_code=400, detail="JSON 必须是数组")
    payloads = []
    errors: list[str] = []
    for index, item in enumerate(data):
        try:
            payloads.append(json_word_to_payload(item))
        except Exception as exc:
            errors.append(f"Item {index}: {exc}")
    imported_count = upsert_entries(session, payloads)
    return ImportResult(imported_count=imported_count, errors=errors)


@app.post("/api/import/csv", response_model=ImportResult)
async def import_csv(file: UploadFile = File(...), session: Session = Depends(get_session)):
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    payloads = []
    errors: list[str] = []
    for index, row in enumerate(reader, start=2):
        try:
            payloads.append(csv_row_to_payload(row))
        except Exception as exc:  # pragma: no cover - defensive parsing
            errors.append(f"Line {index}: {exc}")
    imported_count = upsert_entries(session, payloads)
    return ImportResult(imported_count=imported_count, errors=errors)


@app.post("/api/import/normalize", response_model=EntryResponse)
def normalize_payload(payload: dict, session: Session = Depends(get_session)):
    if "lemma" not in payload:
        raise HTTPException(status_code=400, detail="Payload must include lemma")
    entry_payload = EntryCreate(**payload)
    entry = apply_payload(VocabularyEntry(lemma="", normalized_lemma=""), entry_payload)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    entry = session.scalars(entry_query().where(VocabularyEntry.id == entry.id)).first()
    return serialize_entry(entry)
