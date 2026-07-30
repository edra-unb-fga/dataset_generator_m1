from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal


Step = Literal["home", "essentials", "advanced", "review", "preflight", "confirm", "running", "results", "exit"]
RunState = Literal["not-started", "running", "paused", "interrupted", "complete"]


@dataclass(frozen=True)
class SessionState:
    step: Step = "home"
    source: str = "none"
    family: str = "landing"
    composer: str = "configs/landing-standard.yaml"
    output: str = "outputs/runs/landing-standard/20260730-120000"
    image_count: int = 20
    appearance: str = "realistic-heavy"
    workers: int = 2
    warnings: tuple[str, ...] = ()
    required_acknowledgements: tuple[str, ...] = ()
    warnings_acknowledged: bool = False
    final_confirmation: bool = False
    run_state: RunState = "not-started"
    accepted: int = 0
    selected_result_action: str = "none"
    history: tuple[Step, ...] = ()


def initial_state() -> SessionState:
    return SessionState()


def _move(state: SessionState, step: Step, **changes: object) -> SessionState:
    return replace(state, step=step, history=(*state.history, state.step), **changes)


def reduce(state: SessionState, action: str) -> SessionState:
    if action == "quit":
        return _move(state, "exit")
    if action == "back" and state.history:
        return replace(state, step=state.history[-1], history=state.history[:-1])
    if state.step == "home" and action in {"new", "saved", "example", "resume"}:
        source = {"new": "new composer", "saved": "saved composer", "example": "copied shipped example", "resume": "interrupted pool"}[action]
        if action == "resume":
            return _move(state, "review", source=source, run_state="interrupted", accepted=7)
        return _move(state, "essentials", source=source)
    if state.step == "essentials" and action == "advanced":
        return _move(state, "advanced")
    if state.step == "advanced" and action == "risky":
        return replace(state, appearance="random-fog-heavy")
    if state.step in {"essentials", "advanced"} and action == "review":
        return _move(state, "review")
    if state.step == "review" and action == "preflight":
        required = ("RANDOM_FOG_HIGH_COST",) if state.appearance == "random-fog-heavy" else ()
        warnings = required or ("REALISTIC_HEAVY_COST",)
        return _move(state, "preflight", warnings=warnings, required_acknowledgements=required)
    if state.step == "preflight" and action == "acknowledge":
        return replace(state, warnings_acknowledged=True)
    if state.step == "preflight" and action == "continue":
        if state.required_acknowledgements and not state.warnings_acknowledged:
            return state
        return _move(state, "confirm")
    if state.step == "confirm" and action == "confirm":
        return _move(state, "running", final_confirmation=True, run_state="running")
    if state.step == "running" and action == "tick":
        accepted = min(state.image_count, state.accepted + 5)
        if accepted == state.image_count:
            return _move(state, "results", accepted=accepted, run_state="complete")
        return replace(state, accepted=accepted)
    if state.step == "running" and action == "pause":
        return replace(state, run_state="paused")
    if state.step == "running" and action == "continue":
        return replace(state, run_state="running")
    if state.step == "running" and action == "stop":
        return _move(state, "results", run_state="interrupted")
    if state.step == "results" and action in {"qa", "inspect", "export"}:
        return replace(state, selected_result_action=action)
    if state.step == "results" and action == "again":
        return _move(state, "home", run_state="not-started", accepted=0, final_confirmation=False)
    return state


def available_actions(state: SessionState) -> tuple[str, ...]:
    actions = {
        "home": ("new", "saved", "example", "resume", "quit"),
        "essentials": ("advanced", "review", "back", "quit"),
        "advanced": ("risky", "review", "back", "quit"),
        "review": ("preflight", "back", "quit"),
        "preflight": ("acknowledge", "continue", "back", "quit"),
        "confirm": ("confirm", "back", "quit"),
        "running": ("tick", "pause", "continue", "stop"),
        "results": ("qa", "inspect", "export", "again", "quit"),
        "exit": (),
    }
    return actions[state.step]
