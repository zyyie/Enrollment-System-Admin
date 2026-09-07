"""Free cloud AI models for schedule generation (Groq primary, Gemini/OpenRouter fallback)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .gemini_client import call_gemini_json
from .prompt_builder import SYSTEM_PROMPT, build_user_prompt
from .rate_limit_queue import RateLimitQueue

DEFAULT_USER_AGENT = "Geranova-EMS/1.0 (Python; scheduling)"
SECTION_LABELS = ["A", "B"]
SECTION_CALL_DELAY_SEC = 1.5
GROQ_SECTION_CALL_DELAY_SEC = 0.35
STRAND_CALL_DELAY_SEC = 0.5
SUBJECT_CHUNK_SIZE = 20
GROQ_SUBJECT_CHUNK_SIZE = 4
# Groq 413s on multi-section prompts — always schedule Section A, then Section B separately.
MAX_COMBINED_SECTION_ENTRIES = 0
SCHEDULER_AI_BUILD = "groq-section-first-v3"
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"

ProgressCallback = Callable[[str, str], None]


@dataclass
class StrandGenerationResult:
    strand: str
    section: str
    provider: str | None = None
    count: int = 0
    expected: int = 0
    error: str | None = None


@dataclass
class GenerationReport:
    schedules: list[dict] = field(default_factory=list)
    provider: str | None = None
    results: list[StrandGenerationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    progress: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class AIProvider:
    name: str
    label: str
    model: str
    configured: bool


class CloudAIClient:
    """Generates schedules strand-by-strand, section-by-section, subject-chunk-by-chunk."""

    def __init__(
        self,
        *,
        groq_api_key: str = "",
        groq_model: str = "llama-3.1-8b-instant",
        openrouter_api_key: str = "",
        openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free",
        gemini_api_key: str = "",
        gemini_model: str = "gemini-2.0-flash",
    ):
        self.groq_api_key = (groq_api_key or "").strip()
        self.groq_model = groq_model or GROQ_FALLBACK_MODEL
        self.openrouter_api_key = (openrouter_api_key or "").strip()
        self.openrouter_model = openrouter_model or "meta-llama/llama-3.3-70b-instruct:free"
        self.gemini_api_key = (gemini_api_key or "").strip()
        self.gemini_model = gemini_model or "gemini-2.0-flash"
        self._queue = RateLimitQueue(
            min_delay_sec=GROQ_SECTION_CALL_DELAY_SEC if groq_api_key else SECTION_CALL_DELAY_SEC
        )

    @property
    def configured(self) -> bool:
        return bool(self.groq_api_key or self.openrouter_api_key or self.gemini_api_key)

    @property
    def primary_provider(self) -> AIProvider | None:
        if self.groq_api_key:
            return AIProvider("groq", "Groq", self.groq_model, True)
        if self.gemini_api_key:
            return AIProvider("gemini", "Google Gemini", self.gemini_model, True)
        if self.openrouter_api_key:
            return AIProvider("openrouter", "OpenRouter", self.openrouter_model, True)
        return None

    def list_providers(self) -> list[AIProvider]:
        providers: list[AIProvider] = []
        if self.groq_api_key:
            providers.append(AIProvider("groq", "Groq", self.groq_model, True))
        if self.gemini_api_key:
            providers.append(AIProvider("gemini", "Google Gemini", self.gemini_model, True))
        if self.openrouter_api_key:
            providers.append(AIProvider("openrouter", "OpenRouter", self.openrouter_model, True))
        return providers

    def _subject_chunk_size(self) -> int:
        if self.groq_api_key:
            return GROQ_SUBJECT_CHUNK_SIZE
        return SUBJECT_CHUNK_SIZE

    def _use_combined_section_call(self, combined_entries: int, total_sections: int) -> bool:
        if total_sections <= 1 or MAX_COMBINED_SECTION_ENTRIES <= 0:
            return False
        if self.groq_api_key:
            return False
        return combined_entries <= MAX_COMBINED_SECTION_ENTRIES

    def _new_queue(self, on_progress: ProgressCallback | None = None) -> RateLimitQueue:
        delay = GROQ_SECTION_CALL_DELAY_SEC if self.groq_api_key else SECTION_CALL_DELAY_SEC
        return RateLimitQueue(
            min_delay_sec=delay,
            max_retries=3 if self.groq_api_key else 4,
            base_backoff_sec=4.0 if self.groq_api_key else 6.0,
            on_progress=on_progress,
        )

    def generate_one_strand(
        self,
        payload: dict,
        strand: str,
        *,
        already_scheduled: list[dict] | None = None,
        timeout: int = 120,
        on_progress: ProgressCallback | None = None,
        scheduling_context: dict | None = None,
        conflict_hints: list[str] | None = None,
    ) -> GenerationReport:
        single_payload = {**payload, "strands": [strand.upper()]}
        report = GenerationReport()
        queue = self._new_queue(on_progress)
        strand_code = strand.upper()
        subjects = subjects_for_strand_from_payload(single_payload, strand_code)
        sections_per_strand = max(1, min(int(payload.get("sections_per_strand") or 2), 2))
        sections = SECTION_LABELS[:sections_per_strand]
        booked = list(already_scheduled or [])
        total_sections = len(sections)

        queue.log("info", f"Processing {strand_code} strand ({total_sections} section(s))...")

        combined_entries = len(subjects) * total_sections
        chunk_size = self._subject_chunk_size()
        if self._use_combined_section_call(combined_entries, total_sections):
            combined_payload = {
                **single_payload,
                "strands": [strand_code],
                "subjects": subjects,
                "target_sections": sections,
            }
            queue.log(
                "info",
                f"{strand_code} — scheduling {total_sections} section(s) in one AI call "
                f"({combined_entries} entries)...",
            )
            parsed, err, provider, _attempts = self._generate_with_retries(
                queue,
                combined_payload,
                target_section=None,
                target_sections=sections,
                already_scheduled=booked,
                timeout=timeout,
                expected_count=combined_entries,
                label=f"{strand_code} all sections",
                scheduling_context=scheduling_context or payload.get("scheduling_context"),
                conflict_hints=conflict_hints,
                strand=strand_code,
                sections=sections,
                subjects=subjects,
            )
            if parsed and isinstance(parsed.get("schedules"), list):
                normalized = _normalize_schedules(parsed["schedules"], strand_code, sections[0])
                normalized = sanitize_ai_schedules(
                    normalized,
                    strand=strand_code,
                    sections=sections,
                    subjects=subjects,
                )
                report.schedules.extend(normalized)
                report.provider = provider or report.provider
                booked.extend(normalized)
                if len(normalized) < combined_entries:
                    report.errors.append(
                        f"{strand_code}: incomplete after cleanup ({len(normalized)}/{combined_entries})"
                    )
                else:
                    queue.log(
                        "success",
                        f"{strand_code} strand complete ({len(normalized)}/{combined_entries} entries "
                        f"via {report.provider or 'cloud AI'}).",
                    )
            elif err:
                report.errors.append(f"{strand_code}: {err}")
                queue.log("error", f"{strand_code} combined call failed — trying section-by-section...")
            else:
                queue.log("warn", f"{strand_code} combined call incomplete — trying section-by-section...")

            if report.schedules and len(report.schedules) == combined_entries:
                report.progress = queue.logs
                return report

            if report.schedules:
                report.schedules.clear()
                booked = list(already_scheduled or [])

        if total_sections > 1 and not self._use_combined_section_call(combined_entries, total_sections):
            queue.log(
                "info",
                f"{strand_code} — Groq-safe mode: Section A first, then B "
                f"({chunk_size} subjects per AI call)...",
            )

        for section_index, section in enumerate(sections, start=1):
            queue.log(
                "info",
                f"{strand_code} Section {section} ({section_index}/{total_sections}) — "
                f"{len(subjects)} subjects in chunks of {chunk_size}...",
            )
            section_schedules: list[dict] = []
            subject_chunks = _chunk_list(subjects, chunk_size)

            for chunk_index, chunk in enumerate(subject_chunks, start=1):
                if len(subject_chunks) > 1:
                    queue.log(
                        "info",
                        f"{strand_code} Section {section}: chunk {chunk_index}/{len(subject_chunks)} "
                        f"({len(chunk)} subjects)...",
                    )
                section_payload = _payload_for_strand_section(
                    single_payload, strand_code, section, chunk
                )
                chunk_schedules, err, provider = self._generate_chunk_with_split_fallback(
                    queue,
                    section_payload,
                    strand_code=strand_code,
                    section=section,
                    chunk=chunk,
                    booked=booked,
                    section_schedules=section_schedules,
                    timeout=timeout,
                    chunk_index=chunk_index,
                    chunk_total=len(subject_chunks),
                    scheduling_context=scheduling_context or payload.get("scheduling_context"),
                    conflict_hints=conflict_hints,
                )
                if chunk_schedules:
                    section_schedules.extend(chunk_schedules)
                    report.provider = provider or report.provider
                elif err:
                    report.errors.append(f"{strand_code} Section {section} chunk {chunk_index}: {err}")

            result = StrandGenerationResult(
                strand=strand_code,
                section=section,
                provider=report.provider,
                expected=len(subjects),
            )
            if section_schedules:
                result.count = len(section_schedules)
                report.schedules.extend(section_schedules)
                booked.extend(section_schedules)
                if result.count >= result.expected:
                    queue.log(
                        "success",
                        f"{strand_code} Section {section} scheduled successfully "
                        f"({result.count} entries via {report.provider or 'cloud AI'}).",
                    )
                else:
                    msg = f"{strand_code} Section {section}: incomplete ({result.count}/{result.expected})"
                    result.error = msg
                    report.errors.append(msg)
            else:
                result.error = "No schedules returned"
                report.errors.append(f"{strand_code} Section {section}: failed after retries")
                queue.log("error", f"{strand_code} Section {section} failed.")

            report.results.append(result)

        report.progress = queue.logs
        if report.schedules and not report.errors:
            queue.log("success", f"{strand_code} strand complete ({len(report.schedules)} entries).")
        return report

    def generate_with_report(
        self,
        payload: dict,
        timeout: int = 120,
        on_progress: ProgressCallback | None = None,
    ) -> GenerationReport:
        strands = [str(s).upper() for s in (payload.get("strands") or []) if str(s).strip()]
        merged = GenerationReport()
        already_scheduled: list[dict] = []
        total = len(strands)

        for index, strand in enumerate(strands, start=1):
            if on_progress:
                on_progress("info", f"Strand {index}/{total}: {strand}...")
            single = self.generate_one_strand(
                payload,
                strand,
                already_scheduled=already_scheduled,
                timeout=timeout,
                on_progress=on_progress,
            )
            merged.schedules.extend(single.schedules)
            merged.results.extend(single.results)
            merged.errors.extend(single.errors)
            merged.progress.extend(single.progress)
            merged.provider = single.provider or merged.provider
            already_scheduled.extend(single.schedules)
            if index < total:
                time.sleep(STRAND_CALL_DELAY_SEC)

        return merged

    def _generate_chunk_with_split_fallback(
        self,
        queue: RateLimitQueue,
        section_payload: dict,
        *,
        strand_code: str,
        section: str,
        chunk: list[dict],
        booked: list[dict],
        section_schedules: list[dict],
        timeout: int,
        chunk_index: int,
        chunk_total: int,
        scheduling_context: dict | None,
        conflict_hints: list[str] | None,
    ) -> tuple[list[dict], str | None, str | None]:
        label = f"{strand_code} {section} chunk {chunk_index}"
        if chunk_total > 1:
            label += f"/{chunk_total}"

        parsed, err, provider, _ = self._generate_with_retries(
            queue,
            section_payload,
            target_section=section,
            already_scheduled=booked + section_schedules,
            timeout=timeout,
            expected_count=len(chunk),
            label=label,
            scheduling_context=scheduling_context,
            conflict_hints=conflict_hints,
            strand=strand_code,
            sections=[section],
            subjects=chunk,
        )
        if parsed and isinstance(parsed.get("schedules"), list):
            normalized = sanitize_ai_schedules(
                _normalize_schedules(parsed["schedules"], strand_code, section),
                strand=strand_code,
                sections=[section],
                subjects=chunk,
            )
            return normalized, None, provider

        if err and "413" in err and len(chunk) > 1:
            queue.log(
                "warn",
                f"{strand_code} Section {section}: request too large — splitting "
                f"{len(chunk)} subjects into smaller batches...",
            )
            combined: list[dict] = []
            last_err: str | None = err
            last_provider = provider
            mid = max(1, len(chunk) // 2)
            for part_index, sub_chunk in enumerate([chunk[:mid], chunk[mid:]], start=1):
                if not sub_chunk:
                    continue
                sub_payload = {
                    **section_payload,
                    "subjects": sub_chunk,
                }
                part_schedules, part_err, part_provider = self._generate_chunk_with_split_fallback(
                    queue,
                    sub_payload,
                    strand_code=strand_code,
                    section=section,
                    chunk=sub_chunk,
                    booked=booked,
                    section_schedules=section_schedules + combined,
                    timeout=timeout,
                    chunk_index=chunk_index,
                    chunk_total=chunk_total,
                    scheduling_context=scheduling_context,
                    conflict_hints=conflict_hints,
                )
                if part_schedules:
                    combined.extend(part_schedules)
                    last_provider = part_provider or last_provider
                elif part_err:
                    last_err = part_err
            if combined:
                return combined, None, last_provider
            return [], last_err, None

        return [], err, provider

    def _generate_with_retries(
        self,
        queue: RateLimitQueue,
        payload: dict,
        *,
        target_section: str | None,
        already_scheduled: list[dict],
        timeout: int,
        expected_count: int,
        label: str,
        scheduling_context: dict | None = None,
        conflict_hints: list[str] | None = None,
        target_sections: list[str] | None = None,
        strand: str | None = None,
        sections: list[str] | None = None,
        subjects: list[dict] | None = None,
    ) -> tuple[dict | None, str | None, str | None, int]:
        last_err: str | None = None
        for attempt in range(queue.max_retries):
            queue.wait_turn(label)
            parsed, err, provider, retry_after = self._generate_once(
                payload,
                target_section=target_section,
                target_sections=target_sections,
                already_scheduled=already_scheduled,
                timeout=timeout,
                scheduling_context=scheduling_context,
                conflict_hints=conflict_hints,
            )
            queue.mark_sent()

            if parsed and isinstance(parsed.get("schedules"), list):
                schedules = parsed["schedules"]
                if strand and sections is not None and subjects is not None:
                    default_section = (target_section or (sections[0] if sections else "")).upper()
                    schedules = sanitize_ai_schedules(
                        _normalize_schedules(schedules, strand.upper(), default_section),
                        strand=strand,
                        sections=sections,
                        subjects=subjects,
                    )
                    parsed = {**parsed, "schedules": schedules}
                count = len(schedules)
                if count == expected_count:
                    return parsed, None, provider, attempt + 1
                if count > expected_count:
                    last_err = f"AI returned {count} entries; trimmed to {len(schedules)} (expected {expected_count})"
                else:
                    last_err = f"Only {count}/{expected_count} subjects scheduled"

            if err:
                last_err = err
                is_rate_limit = "429" in err or "rate limit" in err.lower()
                if is_rate_limit and attempt < queue.max_retries - 1:
                    queue.backoff(attempt, retry_after, provider or "Cloud AI")
                    continue
                if not is_rate_limit and attempt < 1:
                    time.sleep(0.25 if self.groq_api_key else 1)
                    continue

            time.sleep(0.25 if self.groq_api_key else 1)

        return None, last_err, None, queue.max_retries

    def _generate_once(
        self,
        payload: dict,
        *,
        target_section: str | None,
        already_scheduled: list[dict] | None,
        timeout: int,
        scheduling_context: dict | None = None,
        conflict_hints: list[str] | None = None,
        target_sections: list[str] | None = None,
    ) -> tuple[dict | None, str | None, str | None, int | None]:
        user_prompt = build_user_prompt(
            payload,
            target_section=target_section,
            target_sections=target_sections or payload.get("target_sections"),
            already_scheduled=already_scheduled,
            scheduling_context=scheduling_context,
            conflict_hints=conflict_hints,
            lightweight=bool(self.groq_api_key),
        )
        errors: list[str] = []
        last_retry_after: int | None = None

        if self.groq_api_key:
            groq_models = [self.groq_model]
            if self.groq_model != GROQ_FALLBACK_MODEL:
                groq_models.append(GROQ_FALLBACK_MODEL)
            for model in groq_models:
                parsed, err, retry_after = _call_openai_compatible(
                url="https://api.groq.com/openai/v1/chat/completions",
                api_key=self.groq_api_key,
                    model=model,
                    system_prompt=SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    provider_label="Groq",
                    timeout=timeout,
                    max_tokens=2048 if url.endswith("groq.com/openai/v1/chat/completions") else 4096,
                )
                if parsed:
                    return parsed, None, "groq", None
                if err:
                    errors.append(err)
                    last_retry_after = retry_after or last_retry_after
                    if "429" not in err and model == self.groq_model:
                        break

        if self.gemini_api_key:
            parsed, err, retry_after = call_gemini_json(
                api_key=self.gemini_api_key,
                model=self.gemini_model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                timeout=timeout,
            )
            if parsed:
                return parsed, None, "gemini", None
            if err:
                errors.append(err)
                last_retry_after = retry_after or last_retry_after

        # OpenRouter disabled by default (free tier removed). Server passes a key only when
        # AI_ENABLE_OPENROUTER=1 is set in .env for paid models.
        if self.openrouter_api_key:
            parsed, err, retry_after = _call_openai_compatible(
                url="https://openrouter.ai/api/v1/chat/completions",
                api_key=self.openrouter_api_key,
                model=self.openrouter_model,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
                provider_label="OpenRouter",
                timeout=timeout,
                max_tokens=4096,
                extra_headers={
                    "HTTP-Referer": "https://geranova-ems.local",
                    "X-Title": "Geranova EMS Scheduler",
                },
            )
            if parsed:
                return parsed, None, "openrouter", None
            if err:
                errors.append(err)
                last_retry_after = retry_after or last_retry_after

        if not errors:
            return None, "No cloud AI configured. Add GROQ_API_KEY to .env.", None, None
        return None, " | ".join(errors), None, last_retry_after


def subjects_for_strand_from_payload(payload: dict, strand: str) -> list[dict]:
    strand_code = strand.upper()
    subjects: list[dict] = []
    for subject in payload.get("subjects") or []:
        sub_strand = subject.get("strand")
        if sub_strand is None or str(sub_strand).upper() == strand_code:
            subjects.append(subject)
    return subjects


def _payload_for_strand_section(
    payload: dict,
    strand: str,
    section: str,
    subjects: list[dict],
) -> dict:
    return {
        **payload,
        "strands": [strand.upper()],
        "subjects": subjects,
        "sections_per_strand": 1,
        "target_section": section.upper(),
    }


def sanitize_ai_schedules(
    schedules: list[dict],
    *,
    strand: str,
    sections: list[str],
    subjects: list[dict],
) -> list[dict]:
    """Keep one entry per strand/section/subject; drop extras from over-eager AI output."""
    strand_code = strand.upper()
    section_set = [str(section).upper() for section in sections if str(section).strip()]
    expected_order: list[tuple[str, str, str]] = []
    for section in section_set:
        for subject in subjects:
            code = (subject.get("code") or subject.get("subject_code") or "").upper()
            if code:
                expected_order.append((strand_code, section, code))

    by_key: dict[tuple[str, str, str], dict] = {}
    for item in schedules:
        if not isinstance(item, dict):
            continue
        item_strand = (item.get("strand") or strand_code).upper()
        section = (item.get("section") or "").upper()
        code = (item.get("subject_code") or item.get("subject") or "").upper()
        if item_strand != strand_code or section not in section_set or not code:
            continue
        key = (item_strand, section, code)
        if key not in by_key:
            by_key[key] = item

    return [by_key[key] for key in expected_order if key in by_key]


def _normalize_schedules(schedules: list[dict], strand: str, section: str) -> list[dict]:
    normalized: list[dict] = []
    for item in schedules:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                **item,
                "strand": (item.get("strand") or strand).upper(),
                "section": (item.get("section") or section).upper(),
            }
        )
    return normalized


def _chunk_list(items: list, size: int) -> list[list]:
    if size <= 0:
        return [items]
    return [items[i : i + size] for i in range(0, len(items), size)]


def _shorten_api_error(provider_label: str, code: int, detail: str) -> str:
    if code == 429:
        return f"{provider_label} rate limit (429)"
    if code == 403:
        return f"{provider_label} access denied (403)"
    if code == 413:
        return f"{provider_label} request too large (413)"
    try:
        payload = json.loads(detail)
        message = (payload.get("error") or {}).get("message")
        if message:
            return f"{provider_label} HTTP {code}: {message[:120]}"
    except json.JSONDecodeError:
        pass
    return f"{provider_label} HTTP {code}: {detail[:120]}"


def _parse_retry_after(err: HTTPError) -> int | None:
    if not err.headers:
        return None
    value = err.headers.get("Retry-After")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _call_openai_compatible(
    *,
    url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    provider_label: str,
    timeout: int,
    max_tokens: int = 4096,
    extra_headers: dict[str, str] | None = None,
) -> tuple[dict | None, str | None, int | None]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": DEFAULT_USER_AGENT,
    }
    if extra_headers:
        headers.update(extra_headers)

    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except HTTPError as err:
        retry_after = _parse_retry_after(err)
        detail = err.read().decode("utf-8", errors="replace")
        return None, _shorten_api_error(provider_label, err.code, detail), retry_after
    except URLError as err:
        return None, f"{provider_label} network error: {err.reason}", None
    except json.JSONDecodeError:
        return None, f"{provider_label} returned invalid JSON envelope", None

    text = _extract_openai_text(raw)
    if not text:
        return None, f"{provider_label} returned an empty response", None

    parsed = _parse_json_from_text(text)
    if parsed is None:
        return None, f"Could not parse JSON from {provider_label} response: {text[:300]}", None
    return parsed, None, None


def _extract_openai_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


def _parse_json_from_text(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
