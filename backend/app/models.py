from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .db import Base


class VocabularyEntry(Base):
    __tablename__ = "vocabulary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lemma: Mapped[str] = mapped_column(String(255), index=True)
    normalized_lemma: Mapped[str] = mapped_column(String(255), index=True)
    language: Mapped[str] = mapped_column(String(32), default="de")
    part_of_speech: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    word_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True)
    article: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plural_form: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cefr_level: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    pronunciation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    searchable_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_data: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    meanings: Mapped[list["Meaning"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="Meaning.sort_order",
    )
    forms: Mapped[list["EntryForm"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )
    collocations: Mapped[list["Collocation"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )
    examples: Mapped[list["ExampleSentence"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["EntryTag"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )
    images: Mapped[list["EntryImage"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="EntryImage.created_at.desc()",
    )


class Meaning(Base):
    __tablename__ = "meanings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(32), default="zh")
    gloss: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    entry: Mapped["VocabularyEntry"] = relationship(back_populates="meanings")


class EntryForm(Base):
    __tablename__ = "entry_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[str] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entry: Mapped["VocabularyEntry"] = relationship(back_populates="forms")


class Collocation(Base):
    __tablename__ = "collocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"))
    kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phrase: Mapped[str] = mapped_column(String(255))
    meaning: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entry: Mapped["VocabularyEntry"] = relationship(back_populates="collocations")


class ExampleSentence(Base):
    __tablename__ = "example_sentences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"))
    german_text: Mapped[str] = mapped_column(Text)
    chinese_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    entry: Mapped["VocabularyEntry"] = relationship(back_populates="examples")


class EntryTag(Base):
    __tablename__ = "entry_tags"
    __table_args__ = (UniqueConstraint("entry_id", "name", name="uq_entry_tag_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64), index=True)
    tag_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    entry: Mapped["VocabularyEntry"] = relationship(back_populates="tags")


class EntryImage(Base):
    __tablename__ = "entry_images"
    __table_args__ = (UniqueConstraint("entry_id", "source_url", name="uq_entry_image_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), index=True)
    local_path: Mapped[str] = mapped_column(String(512))
    source_url: Mapped[str] = mapped_column(String(1024))
    page_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    license: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="wikimedia_commons")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    entry: Mapped["VocabularyEntry"] = relationship(back_populates="images")


class EntrySimilarity(Base):
    __tablename__ = "entry_similarities"
    __table_args__ = (UniqueConstraint("source_entry_id", "target_entry_id", name="uq_entry_similarity_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), index=True)
    target_entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), index=True)
    score: Mapped[int] = mapped_column(Integer, index=True)
    reasons: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WordFrequency(Base):
    __tablename__ = "word_frequencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), index=True, unique=True)
    q: Mapped[str] = mapped_column(String(255))
    lemma: Mapped[str] = mapped_column(String(255))
    frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    entry: Mapped["VocabularyEntry"] = relationship()


class IrregularVerb(Base):

    __tablename__ = "irregular_verbs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    infinitive: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    present: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preterite: Mapped[str] = mapped_column(String(255))
    participle_ii: Mapped[str] = mapped_column(String(255))
    imperative: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subjunctive_ii: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auxiliary: Mapped[str | None] = mapped_column(String(32), nullable=True)
    meaning_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
