"""Task-specific lexical selection, not scientific or semantic verification.

Source text is data, never executable policy. Trusted missions bound all
queries and decisions. Unknowns are retained, not treated as irrelevant.
"""
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from neurolab.document_cards import DocumentCard
from neurolab.it_research import ResearchItem
from neurolab.research_corpus import canonical_source_key

VERSION = "research-selection-v1"
MissionId = Literal["architecture", "workflow", "evaluation", "provenance", "contracts", "theory"]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


@dataclass(frozen=True)
class Mission:
    mission_id: str
    layer: str
    goal: str
    topic: str
    arxiv_terms: tuple[str, ...]
    context: tuple[str, ...]
    problem: tuple[str, ...]
    lane: str = "implementation_evidence_search"


MISSIONS = (
    Mission("architecture", "global_architecture", "Coordinate bounded research and coding agents",
            "LLM multi-agent orchestration architecture workflow failure recovery", ("agent", "orchestration", "workflow"),
            ("agent", "llm", "langgraph", "агент", "нейролаб"), ("orchestrat", "supervisor", "multi-agent", "оркестр", "диспетчер")),
    Mission("workflow", "subsystem", "Retrieve, retain and synthesize research evidence",
            "research agent evidence retrieval memory literature synthesis", ("agent", "retrieval", "memory"),
            ("agent", "llm", "research", "агент", "исследован"), ("retrieval", "memory", "literature", "памят", "извлечен", "публикац")),
    Mission("evaluation", "component", "Evaluate research-agent evidence and citation fidelity",
            "research agent citation verification factuality evidence evaluation", ("agent", "citation", "evaluation"),
            ("agent", "llm", "research", "агент", "модел"), ("citation", "factual", "faithful", "evidence", "цитирован", "достовер", "доказатель")),
    Mission("provenance", "feature", "Track workflow lineage and artifact dependencies; selectively resume failures",
            "workflow provenance traceability artifact dependencies failure recovery", ("workflow", "provenance", "tracing"),
            ("workflow", "artifact", "provenance", "lineage", "артефакт", "происхожден", "граф"),
            ("dependenc", "re-execution", "recovery", "failure", "traceab", "downstream", "зависим", "восстанов", "сбой", "повторн", "отслеж", "трассиров")),
    Mission("contracts", "component", "Constrain agent tools and independently test code changes",
            "LLM agent tool contracts permissions sandbox testing verification", ("agent", "tool", "verification"),
            ("agent", "llm", "tool", "mcp", "агент", "инструмент"),
            ("contract", "permission", "sandbox", "guardrail", "testing", "контракт", "разрешен", "изоляц", "тестир")),
    Mission("theory", "global_architecture", "Explore formal safety and verification of agent workflows",
            "formal verification model checking LLM agent workflow safety", ("agent", "formal", "verification"),
            ("agent", "llm", "workflow", "агент", "процесс"), ("formal", "theorem", "model checking", "формаль", "теорем"), "exploration"),
)
_OUTSIDE = ("kalibench", "kali linux", "nl-to-cli", "penetration testing", "protein folding", "molecular dynamics")
_INJECTION = ("ignore previous", "ignore all", "system prompt", "игнорируй инструкц")


def digest(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def mission_for(identity: str) -> Mission:
    return next((m for m in MISSIONS if m.mission_id == identity), None) or _unknown_mission()


def _unknown_mission():
    raise ValueError("unknown trusted research mission")


def _has(text: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(term), text.casefold()) for term in terms)


def _fits(text: str, mission: Mission) -> bool:
    # A conservative lexical guard: a negated list of topics is not positive
    # task support. This is not a general negation/entailment parser.
    text = re.sub(r"\b(?:without|no|not|без|не)\b[^.;\n]{0,160}", " ", text, flags=re.IGNORECASE)
    return _has(text, mission.context) and _has(text, mission.problem)


class SelectionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_version: Literal["research-selection-v1"] = VERSION
    stage: Literal["metadata", "content"]
    mission_id: MissionId
    mission_sha256: Digest
    source_key: Digest
    input_sha256: Digest
    title_sha256: Digest | None = None
    abstract_sha256: Digest | None = None
    document_sha256: Digest | None = None
    card_sha256: Digest | None = None
    decision: Literal["admit", "explore", "hold", "reject", "useful_experimental", "insufficient"]
    reasons: Annotated[list[Literal["task_match", "outside_current_scope", "abstract_required", "unclear_task_fit",
            "theory_retained", "untrusted_instruction_detected", "page_anchor_match", "page_anchor_missing",
            "metadata_gate_closed", "no_concrete_finding", "limitations_required"]], Field(max_length=8)]
    finding_pages: Annotated[list[tuple[Annotated[int, Field(strict=True, ge=1, le=100)],
                                       Annotated[int, Field(strict=True, ge=1, le=100)]]], Field(max_length=20)] = []
    semantic_verification: Literal["not_performed"] = "not_performed"
    independent_reproduction: Literal["not_performed"] = "not_performed"
    full_spec_allowed: Literal[False] = False
    new_model_calls: Literal[0] = 0


def screen_metadata(item: ResearchItem, mission_id: str, *, source_key: str | None = None) -> SelectionReceipt:
    mission = mission_for(mission_id)
    if not isinstance(item.title, str) or not 1 <= len(item.title) <= 500 or len(item.abstract) > 20000:
        raise ValueError("metadata selection input outside boundary")
    decision, reasons = "hold", ["unclear_task_fit"]
    primary = item.title.casefold()
    combined = item.title + "\n" + item.abstract
    if any(term in combined.casefold() for term in _INJECTION):
        reasons = ["untrusted_instruction_detected"]
    elif any(term in primary for term in _OUTSIDE):
        decision, reasons = "reject", ["outside_current_scope"]
    elif len(item.abstract.strip()) < 80:
        reasons = ["abstract_required"]
    elif _fits(item.abstract, mission):
        decision, reasons = ("explore", ["task_match", "theory_retained"]) if mission.lane == "exploration" else ("admit", ["task_match"])
    title_hash = sha256(item.title.encode()).hexdigest()
    abstract_hash = sha256(item.abstract.encode()).hexdigest() if item.abstract else None
    mission_hash = digest(asdict(mission))
    return SelectionReceipt(stage="metadata", mission_id=mission_id, mission_sha256=mission_hash,
        source_key=source_key or canonical_source_key(item), title_sha256=title_hash, abstract_sha256=abstract_hash,
        input_sha256=digest({"title": title_hash, "abstract": abstract_hash, "mission": mission_hash}), decision=decision, reasons=reasons)


def metadata_matches(receipt: SelectionReceipt, *, source_key: str, title: str, abstract_sha256: str | None) -> bool:
    return (receipt.stage == "metadata" and receipt.source_key == source_key
            and receipt.mission_sha256 == digest(asdict(mission_for(receipt.mission_id)))
            and receipt.title_sha256 == sha256(title.encode()).hexdigest()
            and receipt.abstract_sha256 == abstract_sha256
            and receipt.input_sha256 == digest({"title": receipt.title_sha256, "abstract": receipt.abstract_sha256, "mission": receipt.mission_sha256})
            and receipt.decision in {"admit", "explore"})


def assess_content(card: DocumentCard, metadata: SelectionReceipt, page_texts: tuple[str, ...]) -> SelectionReceipt:
    """Utility baseline requires exact-source metadata and cited-page signals.

    The caller verifies PDF hash before passing ephemeral extracted pages.
    Matching words on a page do NOT prove entailment or scientific truth.
    """
    mission = mission_for(metadata.mission_id)
    if not 1 <= len(page_texts) <= 100 or sum(map(len, page_texts)) > 1000000:
        raise ValueError("content selection input outside boundary")
    reasons, pages, decision = [], [], "insufficient"
    if (metadata.stage != "metadata" or metadata.source_key != card.source_key
            or metadata.mission_sha256 != digest(asdict(mission))
            or metadata.input_sha256 != digest({"title": metadata.title_sha256, "abstract": metadata.abstract_sha256, "mission": metadata.mission_sha256})
            or metadata.decision not in {"admit", "explore"}):
        reasons = ["metadata_gate_closed"]
    elif any(t in (card.document_summary + " " + card.research_problem).casefold() for t in _OUTSIDE):
        decision, reasons = "reject", ["outside_current_scope"]
    elif not card.limitations:
        reasons = ["limitations_required"]
    else:
        for finding in card.findings:
            if finding.page_end > len(page_texts):
                raise ValueError("content finding outside document")
            source = "\n".join(page_texts[finding.page_start - 1:finding.page_end])
            if finding.kind != "limitation" and _fits(finding.summary, mission) and _fits(source, mission):
                pages.append((finding.page_start, finding.page_end))
        if pages:
            decision = "explore" if metadata.decision == "explore" else "useful_experimental"
            reasons = ["page_anchor_match"] + (["theory_retained"] if decision == "explore" else [])
        else:
            reasons = ["page_anchor_missing"]
    return SelectionReceipt(stage="content", source_key=card.source_key, mission_id=metadata.mission_id,
        mission_sha256=digest(asdict(mission)), input_sha256=digest({"card": card.card_sha256,
            "pdf": card.document_sha256, "metadata": digest(metadata)}), document_sha256=card.document_sha256,
        card_sha256=card.card_sha256, decision=decision, reasons=reasons, finding_pages=pages)
