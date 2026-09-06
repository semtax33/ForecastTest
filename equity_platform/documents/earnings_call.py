from __future__ import annotations

from dataclasses import dataclass, replace
from collections import Counter
from datetime import datetime
from enum import StrEnum
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import string
from typing import Mapping

from equity_platform.ir import SourceRef

from .model import CanonicalDocument, DocumentMetadata, DocumentSentence


class TranscriptStatus(StrEnum):
    OK = "OK"
    NO_DATA = "NO_DATA"
    PARTIAL_CONTENT = "PARTIAL_CONTENT"
    EMPTY_CONTENT = "EMPTY_CONTENT"


class TranscriptSection(StrEnum):
    PREPARED_REMARKS = "IR_PREPARED_REMARKS"
    QA = "IR_QA"
    UNSPECIFIED = "IR_UNSPECIFIED"


class TranscriptBoundaryMethod(StrEnum):
    OPERATOR_QA_CUE = "OPERATOR_QA_CUE"
    ANALYST_ROLE = "ANALYST_ROLE"
    NOT_IDENTIFIED = "NOT_IDENTIFIED"


@dataclass(frozen=True)
class TranscriptTurn:
    turn_index: int
    speaker: str
    title: str
    content: str
    sentiment: float | None
    section: TranscriptSection

    def __post_init__(self) -> None:
        if self.turn_index < 0 or not self.content.strip():
            raise ValueError("transcript turns require an index and non-empty content")


@dataclass(frozen=True)
class EarningsCallTranscript:
    entity: str
    fiscal_year: int
    fiscal_quarter: int
    status: TranscriptStatus
    complete: bool
    source: SourceRef
    available_at_basis: str
    call_occurred_at: str | None
    boundary_method: TranscriptBoundaryMethod
    turns: tuple[TranscriptTurn, ...]
    empty_turn_count: int = 0

    @property
    def period(self) -> str:
        return f"{self.fiscal_year}Q{self.fiscal_quarter}"


@dataclass(frozen=True)
class AlphaVantageTranscriptCorpus:
    transcripts: tuple[EarningsCallTranscript, ...]
    selected_transcripts: tuple[EarningsCallTranscript, ...]
    missing_entities: tuple[str, ...]
    duplicate_source_hashes: tuple[str, ...]
    boundary_method_counts: dict[str, int]

    @property
    def ok_count(self) -> int:
        return sum(row.status is TranscriptStatus.OK for row in self.transcripts)

    @property
    def no_data_count(self) -> int:
        return sum(row.status is TranscriptStatus.NO_DATA for row in self.transcripts)

    @property
    def partial_content_count(self) -> int:
        return sum(
            row.status is TranscriptStatus.PARTIAL_CONTENT
            for row in self.transcripts
        )

    @property
    def empty_content_count(self) -> int:
        return sum(
            row.status is TranscriptStatus.EMPTY_CONTENT
            for row in self.transcripts
        )


_QA_START_CUES = (
    "question-and-answer session",
    "question and answer session",
    "first question",
    "questions at this time",
    "open the call for questions",
    "open the line for questions",
)
_QA_END_CUES = (
    "concludes the question-and-answer session",
    "concludes the question and answer session",
    "concludes our question-and-answer session",
    "no further questions",
)


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _partition_identity(path: Path) -> tuple[str, int, int]:
    try:
        ticker_part = path.parents[1].name
        year_part = path.parent.name
        quarter_part = path.stem
        if not ticker_part.startswith("ticker="):
            raise ValueError
        if not year_part.startswith("fiscal_year="):
            raise ValueError
        if not quarter_part.startswith("quarter=Q"):
            raise ValueError
        ticker = ticker_part.removeprefix("ticker=")
        year = int(year_part.removeprefix("fiscal_year="))
        quarter = int(quarter_part.removeprefix("quarter=Q"))
    except (IndexError, ValueError) as exc:
        raise ValueError(f"invalid Alpha Vantage transcript partition: {path}") from exc
    if not ticker or quarter not in {1, 2, 3, 4}:
        raise ValueError(f"invalid Alpha Vantage transcript partition: {path}")
    return ticker, year, quarter


def _required_text(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Alpha Vantage transcript field {field!r} is missing")
    return value.strip()


def _role_tokens(title: str) -> tuple[str, ...]:
    return tuple(
        token.strip(string.punctuation).casefold()
        for token in title.split()
        if token.strip(string.punctuation)
    )


def _is_analyst_role(title: str) -> bool:
    return "analyst" in _role_tokens(title)


def _is_operator(speaker: str, title: str) -> bool:
    return "operator" in {*_role_tokens(speaker), *_role_tokens(title)}


def _normalized_words(content: str) -> str:
    return " ".join(content.casefold().split())


def _has_qa_end_cue(content: str) -> bool:
    normalized = _normalized_words(content)
    return any(cue in normalized for cue in _QA_END_CUES)


def _has_qa_start_cue(content: str) -> bool:
    if _has_qa_end_cue(content):
        return False
    normalized = _normalized_words(content)
    return any(cue in normalized for cue in _QA_START_CUES)


def _section_turns(
    turns: tuple[TranscriptTurn, ...],
) -> tuple[tuple[TranscriptTurn, ...], TranscriptBoundaryMethod]:
    operator_start = next(
        (
            turn.turn_index
            for turn in turns
            if _is_operator(turn.speaker, turn.title)
            and _has_qa_start_cue(turn.content)
        ),
        None,
    )
    analyst_start = next(
        (turn.turn_index for turn in turns if _is_analyst_role(turn.title)),
        None,
    )
    candidates = tuple(
        value for value in (operator_start, analyst_start) if value is not None
    )
    if not candidates:
        return (
            tuple(replace(turn, section=TranscriptSection.UNSPECIFIED) for turn in turns),
            TranscriptBoundaryMethod.NOT_IDENTIFIED,
        )
    start = min(candidates)
    method = (
        TranscriptBoundaryMethod.OPERATOR_QA_CUE
        if operator_start is not None and operator_start == start
        else TranscriptBoundaryMethod.ANALYST_ROLE
    )
    end = next(
        (
            turn.turn_index
            for turn in turns
            if turn.turn_index >= start
            if _is_operator(turn.speaker, turn.title)
            and _has_qa_end_cue(turn.content)
        ),
        None,
    )
    sectioned = []
    for turn in turns:
        if turn.turn_index < start:
            section = TranscriptSection.PREPARED_REMARKS
        elif end is not None and turn.turn_index > end:
            section = TranscriptSection.UNSPECIFIED
        else:
            section = TranscriptSection.QA
        sectioned.append(replace(turn, section=section))
    return tuple(sectioned), method


def adapt_alpha_vantage_transcript(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> EarningsCallTranscript:
    """Load one immutable Alpha Vantage transcript envelope fail-closed.

    ``retrieved_at`` is a conservative archive-availability timestamp.  It is
    never represented as the date on which the earnings call occurred.
    """

    path = Path(path)
    actual_sha256 = _sha256(path)
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise ValueError(f"Alpha Vantage transcript hash mismatch: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Alpha Vantage transcript envelope must be an object")
    ticker, fiscal_year, fiscal_quarter = _partition_identity(path)
    if payload.get("provider") != "ALPHA_VANTAGE" or payload.get("dataset") != "EARNINGS_CALL_TRANSCRIPT":
        raise ValueError("unexpected Alpha Vantage transcript provider or dataset")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported Alpha Vantage transcript schema version")
    wrapper_identity = (
        str(payload.get("symbol", "")),
        int(payload.get("fiscal_year", -1)),
        int(payload.get("quarter", -1)),
    )
    if wrapper_identity != (ticker, fiscal_year, fiscal_quarter):
        raise ValueError("transcript payload and partition identity disagree")
    retrieved_at = _required_text(payload, "retrieved_at")
    try:
        parsed_retrieved_at = datetime.fromisoformat(retrieved_at)
    except ValueError as exc:
        raise ValueError("transcript retrieved_at must be ISO-8601") from exc
    if parsed_retrieved_at.tzinfo is None:
        raise ValueError("transcript retrieved_at must include a timezone")
    raw_status = str(payload.get("status", "")).casefold()
    if raw_status not in {"ok", "no_data"}:
        raise ValueError(f"unsupported Alpha Vantage transcript status: {raw_status}")
    complete = payload.get("complete") is True
    if raw_status == "ok" and not complete:
        raise ValueError("incomplete Alpha Vantage transcript cannot be adapted")
    source = SourceRef(
        source_type="ALPHA_VANTAGE_EARNINGS_CALL_TRANSCRIPT",
        uri=f"alpha-vantage://earnings-call/{ticker}/{fiscal_year}Q{fiscal_quarter}",
        local_path=path.as_posix(),
        sha256=actual_sha256,
        available_at=retrieved_at,
    )
    if raw_status == "no_data":
        return EarningsCallTranscript(
            entity=ticker,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            status=TranscriptStatus.NO_DATA,
            complete=complete,
            source=source,
            available_at_basis="ARCHIVE_RETRIEVED_AT",
            call_occurred_at=None,
            boundary_method=TranscriptBoundaryMethod.NOT_IDENTIFIED,
            turns=(),
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("ok transcript data must be an object")
    if data.get("symbol") != ticker or data.get("quarter") != f"{fiscal_year}Q{fiscal_quarter}":
        raise ValueError("transcript data and partition identity disagree")
    raw_turns = data.get("transcript")
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ValueError("ok transcript must contain non-empty transcript turns")
    turns = []
    empty_turn_count = 0
    for index, row in enumerate(raw_turns):
        if not isinstance(row, dict):
            raise ValueError("transcript turns must be objects")
        raw_content = row.get("content")
        if not isinstance(raw_content, str):
            raise ValueError(f"transcript turn {index} content must be text")
        content = raw_content.strip()
        if not content:
            empty_turn_count += 1
            continue
        sentiment = row.get("sentiment")
        try:
            parsed_sentiment = float(sentiment) if sentiment not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid sentiment in transcript turn {index}") from exc
        turns.append(TranscriptTurn(
            turn_index=index,
            speaker=str(row.get("speaker", "")).strip(),
            title=str(row.get("title", "")).strip(),
            content=content,
            sentiment=parsed_sentiment,
            section=TranscriptSection.UNSPECIFIED,
        ))
    if not turns:
        return EarningsCallTranscript(
            entity=ticker,
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            status=TranscriptStatus.EMPTY_CONTENT,
            complete=complete,
            source=source,
            available_at_basis="ARCHIVE_RETRIEVED_AT",
            call_occurred_at=None,
            boundary_method=TranscriptBoundaryMethod.NOT_IDENTIFIED,
            turns=(),
            empty_turn_count=empty_turn_count,
        )
    sectioned, boundary_method = _section_turns(tuple(turns))
    return EarningsCallTranscript(
        entity=ticker,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        status=(
            TranscriptStatus.PARTIAL_CONTENT
            if empty_turn_count
            else TranscriptStatus.OK
        ),
        complete=complete,
        source=source,
        available_at_basis="ARCHIVE_RETRIEVED_AT",
        call_occurred_at=None,
        boundary_method=boundary_method,
        turns=sectioned,
        empty_turn_count=empty_turn_count,
    )


@lru_cache(maxsize=1)
def _sentence_segmenter():
    import spacy

    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def _section_document(
    transcript: EarningsCallTranscript,
    section: TranscriptSection,
    turns: tuple[TranscriptTurn, ...],
) -> CanonicalDocument:
    text_parts = []
    sentence_rows = []
    cursor = 0
    sentence_index = 0
    nlp = _sentence_segmenter()
    for turn in turns:
        if text_parts:
            text_parts.append("\n\n")
            cursor += 2
        turn_start = cursor
        text_parts.append(turn.content)
        cursor += len(turn.content)
        heading = " — ".join(value for value in (turn.speaker, turn.title) if value)
        for sentence in nlp(turn.content).sents:
            literal = sentence.text.strip()
            if not literal:
                continue
            leading = len(sentence.text) - len(sentence.text.lstrip())
            start = turn_start + sentence.start_char + leading
            end = start + len(literal)
            sentence_rows.append(DocumentSentence(
                sentence_index=sentence_index,
                text=literal,
                char_start=start,
                char_end=end,
                heading=heading or None,
                section=section.value,
            ))
            sentence_index += 1
    text = "".join(text_parts)
    turn_location = f"turns={turns[0].turn_index}-{turns[-1].turn_index}"
    source = replace(
        transcript.source,
        location=f"section={section.value};{turn_location}",
    )
    return CanonicalDocument(
        metadata=DocumentMetadata(
            entity=transcript.entity,
            source_kind=source.source_type,
            document_kind={
                TranscriptSection.PREPARED_REMARKS: "EARNINGS_CALL_PREPARED_REMARKS",
                TranscriptSection.QA: "EARNINGS_CALL_QA",
                TranscriptSection.UNSPECIFIED: "EARNINGS_CALL_UNSPECIFIED",
            }[section],
            available_at=source.available_at,
            report_period=transcript.period,
        ),
        source=source,
        text=text,
        tables=(),
        inline_facts=(),
        sentences=tuple(sentence_rows),
    )


def transcript_canonical_documents(
    transcript: EarningsCallTranscript,
) -> tuple[CanonicalDocument, ...]:
    if transcript.status is not TranscriptStatus.OK:
        return ()
    documents = []
    for section in (
        TranscriptSection.PREPARED_REMARKS,
        TranscriptSection.QA,
        TranscriptSection.UNSPECIFIED,
    ):
        turns = tuple(turn for turn in transcript.turns if turn.section is section)
        if turns:
            documents.append(_section_document(transcript, section, turns))
    return tuple(documents)


def load_alpha_vantage_transcript_corpus(
    *,
    root: Path,
    entities: tuple[str, ...],
    maximum_ok_per_entity: int = 2,
) -> AlphaVantageTranscriptCorpus:
    """Audit all declared issuer partitions and select recent usable calls.

    Selection is deterministic and happens only after every discovered payload
    has passed the single-file adapter invariants.  Missing issuer partitions
    and provider ``no_data`` responses remain observable.
    """

    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Alpha Vantage transcript root does not exist: {root}")
    if maximum_ok_per_entity < 1:
        raise ValueError("maximum_ok_per_entity must be positive")
    normalized_entities = tuple(sorted({entity.strip().upper() for entity in entities if entity.strip()}))
    if not normalized_entities:
        raise ValueError("at least one transcript entity is required")
    transcripts = []
    missing = []
    for entity in normalized_entities:
        partition = root / f"ticker={entity}"
        paths = tuple(sorted(partition.glob("fiscal_year=*/quarter=Q*.json"))) if partition.is_dir() else ()
        if not paths:
            missing.append(entity)
            continue
        transcripts.extend(adapt_alpha_vantage_transcript(path) for path in paths)
    source_hashes = Counter(row.source.sha256 for row in transcripts)
    duplicates = tuple(sorted(digest for digest, count in source_hashes.items() if count > 1))
    selected = []
    for entity in normalized_entities:
        available = sorted(
            (
                row
                for row in transcripts
                if row.entity == entity and row.status is TranscriptStatus.OK
            ),
            key=lambda row: (row.fiscal_year, row.fiscal_quarter),
            reverse=True,
        )
        selected.extend(available[:maximum_ok_per_entity])
    boundary_counts = Counter(
        row.boundary_method.value
        for row in transcripts
        if row.status is TranscriptStatus.OK
    )
    return AlphaVantageTranscriptCorpus(
        transcripts=tuple(transcripts),
        selected_transcripts=tuple(sorted(
            selected,
            key=lambda row: (row.entity, row.fiscal_year, row.fiscal_quarter),
        )),
        missing_entities=tuple(missing),
        duplicate_source_hashes=duplicates,
        boundary_method_counts={
            method.value: boundary_counts[method.value]
            for method in TranscriptBoundaryMethod
        },
    )


__all__ = [
    "EarningsCallTranscript",
    "AlphaVantageTranscriptCorpus",
    "TranscriptBoundaryMethod",
    "TranscriptSection",
    "TranscriptStatus",
    "TranscriptTurn",
    "adapt_alpha_vantage_transcript",
    "load_alpha_vantage_transcript_corpus",
    "transcript_canonical_documents",
]
