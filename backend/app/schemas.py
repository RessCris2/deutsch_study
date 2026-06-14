from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MeaningPayload(BaseModel):
    language: str = "zh"
    gloss: str
    detail: str | None = None


class FormPayload(BaseModel):
    label: str
    value: str
    note: str | None = None


class CollocationPayload(BaseModel):
    phrase: str
    kind: str | None = None
    meaning: str | None = None


class ExamplePayload(BaseModel):
    german_text: str
    chinese_text: str | None = None
    note: str | None = None


class TagPayload(BaseModel):
    name: str
    tag_type: str | None = None


class EntryImageResponse(BaseModel):
    id: int
    url: str
    source_url: str
    page_url: str | None = None
    title: str | None = None
    license: str | None = None
    attribution: str | None = None
    provider: str


class EntryImageCandidate(BaseModel):
    image_url: str
    source_url: str
    page_url: str | None = None
    title: str | None = None
    license: str | None = None
    attribution: str | None = None
    mime: str


class EntryImageSelectRequest(EntryImageCandidate):
    pass


class EntryBase(BaseModel):
    lemma: str
    language: str = "de"
    part_of_speech: str | None = None
    word_category: str | None = None
    gender: str | None = None
    article: str | None = None
    plural_form: str | None = None
    cefr_level: str | None = None
    pronunciation: str | None = None
    source_type: str | None = None
    source_ref: str | None = None
    notes: str | None = None
    extra_data: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    meanings: list[MeaningPayload] = Field(default_factory=list)
    forms: list[FormPayload] = Field(default_factory=list)
    collocations: list[CollocationPayload] = Field(default_factory=list)
    examples: list[ExamplePayload] = Field(default_factory=list)
    tags: list[TagPayload] = Field(default_factory=list)


class EntryCreate(EntryBase):
    pass


class EntryUpdate(EntryBase):
    pass


class EntryNotesUpdate(BaseModel):
    notes: str | None = None


class WordMasteryResponse(BaseModel):
    word_id: int
    current_score: int = 0
    current_level: str = "new / weak"
    last_rating: str | None = None
    last_reviewed_at: str | None = None
    review_count: int = 0


class WordMasteryEventResponse(BaseModel):
    id: int
    word_id: int
    rating: str
    score_delta: int
    source: str
    created_at: str


class WordMasteryReviewRequest(BaseModel):
    rating: str
    source: str = "detail_self_review"


class WordMasteryReviewResponse(BaseModel):
    event: WordMasteryEventResponse
    mastery: WordMasteryResponse


class NounGenderStatResponse(BaseModel):
    entry_id: int
    seen_count: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    current_streak: int = 0
    wrong_streak: int = 0
    error_rate: float = 0.0
    last_answered_at: str | None = None
    last_wrong_at: str | None = None
    next_due_at: str | None = None


class NounGenderQuizItemResponse(BaseModel):
    entry: "EntryResponse"
    correct_article: str
    choices: list[str] = Field(default_factory=lambda: ["der", "die", "das"])
    zh_meaning: str | None = None
    en_meaning: str | None = None
    plural_form: str | None = None
    frequency_hits: int | None = None
    frequency_level: int | None = None
    stat: NounGenderStatResponse | None = None
    reason: str | None = None


class NounGenderQuizAnswerRequest(BaseModel):
    entry_id: int
    chosen_article: str
    response_ms: int | None = None


class NounGenderQuizAnswerResponse(BaseModel):
    entry: "EntryResponse"
    chosen_article: str
    correct_article: str
    is_correct: bool
    stat: NounGenderStatResponse
    next_item: NounGenderQuizItemResponse | None = None


class NounGenderQuizSummaryResponse(BaseModel):
    total_nouns: int
    practiced_count: int
    unpracticed_count: int
    total_answers: int
    correct_answers: int
    wrong_answers: int
    accuracy: float
    due_count: int


class ReadingBookResponse(BaseModel):
    id: int
    title: str
    file_path: str
    page_count: int
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class ReadingMessageResponse(BaseModel):
    id: int
    page_id: int
    role: str
    content: str
    created_at: str


class ReadingPageResponse(BaseModel):
    id: int
    book_id: int
    page_number: int
    image_url: str | None = None
    ocr_text: str | None = None
    translation_zh: str | None = None
    keywords: list[dict[str, Any]] = Field(default_factory=list)
    grammar_notes: str | None = None
    notes: str | None = None
    status: str
    messages: list[ReadingMessageResponse] = Field(default_factory=list)


class ReadingPageNotesUpdate(BaseModel):
    notes: str | None = None


class ReadingPageTextUpdate(BaseModel):
    ocr_text: str | None = None
    translation_zh: str | None = None


class ReadingPageAskRequest(BaseModel):
    question: str


class ReadingPageAskResponse(BaseModel):
    message: ReadingMessageResponse


class WordFrequencyResponse(BaseModel):
    q: str
    lemma: str
    frequency: int | None = None
    hits: int | None = None
    total: str | None = None
    status: str | None = None
    attempt_count: int | None = None
    last_error: str | None = None


class EntryResponse(EntryBase):
    id: int
    images: list[EntryImageResponse] = Field(default_factory=list)
    frequency: WordFrequencyResponse | None = None
    mastery: WordMasteryResponse | None = None

    class Config:
        from_attributes = True



class EntryListResponse(BaseModel):
    items: list[EntryResponse]
    total: int
    limit: int
    offset: int


class SimilarEntryResponse(BaseModel):
    entry: EntryResponse
    score: float
    reasons: list[str] = Field(default_factory=list)


class EntryDraftRequest(BaseModel):
    lemma: str


class EntryResolveRequest(BaseModel):
    lemma: str


class EntryResolveResponse(BaseModel):
    lemma: str
    resolved_lemma: str | None = None
    reason: str | None = None
    entry: EntryResponse | None = None


class ImportResult(BaseModel):
    imported_count: int
    errors: list[str] = Field(default_factory=list)


class IrregularVerbResponse(BaseModel):
    id: int
    infinitive: str
    present: str | None = None
    preterite: str
    participle_ii: str
    imperative: str | None = None
    subjunctive_ii: str | None = None
    auxiliary: str | None = None
    meaning_zh: str | None = None
    source_ref: str | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


class IrregularVerbListResponse(BaseModel):
    items: list[IrregularVerbResponse]
    total: int


class IrregularVerbQuizItem(BaseModel):
    id: int
    prompt_field: str
    prompt_value: str
    infinitive: str
    present: str | None = None
    preterite: str
    participle_ii: str
    auxiliary: str | None = None
    meaning_zh: str | None = None
