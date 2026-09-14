"""Synthetic, evidence-gated LangGraph smoke workflow for NeuroLab."""

from typing import Literal, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class WorkflowState(TypedDict, total=False):
    task: str
    kind: Literal["research", "engineering"]
    evidence_trace: bool
    cancelled: bool
    max_steps: int
    steps: int
    status: Literal["planned", "blocked", "cancelled", "validated"]
    audit: list[str]
    report: str


def _plan(state: WorkflowState) -> WorkflowState:
    return {"steps": 1, "status": "planned", "audit": ["plan"]}


def _after_plan(state: WorkflowState) -> str:
    if state.get("cancelled"):
        return "cancel"
    if state["steps"] >= state.get("max_steps", 3):
        return "limit"
    if state["kind"] == "research" and not state.get("evidence_trace"):
        return "missing_evidence"
    return "execute"


def _cancel(state: WorkflowState) -> WorkflowState:
    return {"status": "cancelled", "audit": state["audit"] + ["cancel"]}


def _block(state: WorkflowState) -> WorkflowState:
    return {"status": "blocked", "audit": state["audit"] + ["blocked:no-evidence-trace"]}


def _execute(state: WorkflowState) -> WorkflowState:
    return {"steps": state["steps"] + 1, "audit": state["audit"] + ["execute"]}


def _validate(state: WorkflowState) -> WorkflowState:
    return {"status": "validated", "audit": state["audit"] + ["validate"]}


def _report(state: WorkflowState) -> WorkflowState:
    return {"report": f"{state['status']}: {' → '.join(state['audit'])}", "audit": state["audit"] + ["report"]}


def build_smoke_graph():
    builder = StateGraph(WorkflowState)
    builder.add_node("plan", _plan)
    builder.add_node("cancel", _cancel)
    builder.add_node("block", _block)
    builder.add_node("execute", _execute)
    builder.add_node("validate", _validate)
    builder.add_node("report", _report)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", _after_plan, {"cancel": "cancel", "limit": "block", "missing_evidence": "block", "execute": "execute"})
    builder.add_edge("cancel", "report")
    builder.add_edge("block", "report")
    builder.add_edge("execute", "validate")
    builder.add_edge("validate", "report")
    builder.add_edge("report", END)
    return builder.compile(checkpointer=InMemorySaver())


def run_smoke_task(task: str, kind: Literal["research", "engineering"], *, thread_id: str, evidence_trace: bool = False, cancelled: bool = False, max_steps: int = 3) -> WorkflowState:
    graph = build_smoke_graph()
    return graph.invoke({"task": task, "kind": kind, "evidence_trace": evidence_trace, "cancelled": cancelled, "max_steps": max_steps}, {"configurable": {"thread_id": thread_id}})
