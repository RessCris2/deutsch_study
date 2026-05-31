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
