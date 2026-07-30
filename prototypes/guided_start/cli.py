from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from model import SessionState, available_actions, initial_state, reduce


def render(state: SessionState, console: Console) -> None:
    console.clear()
    table = Table(title="PROTOTYPE — guided start", expand=True)
    table.add_column("Field", style="bold")
    table.add_column("Current value")
    for field in (
        "step", "source", "family", "composer", "output", "image_count", "appearance", "workers",
        "warnings", "required_acknowledgements", "warnings_acknowledged", "final_confirmation", "run_state", "accepted", "selected_result_action",
    ):
        table.add_row(field.replace("_", " ").title(), str(getattr(state, field)))
    console.print(table)
    console.print(
        Panel.fit(
            "  ".join(f"[bold]{action}[/]" for action in available_actions(state)) or "Session ended",
            title="Available actions",
        )
    )


def interactive() -> None:
    console = Console()
    state = initial_state()
    while state.step != "exit":
        render(state, console)
        action = Prompt.ask("Action", choices=list(available_actions(state)))
        state = reduce(state, action)
    render(state, console)


def demo() -> None:
    console = Console()
    state = initial_state()
    for action in ("example", "advanced", "risky", "review", "preflight", "acknowledge", "continue", "confirm", "tick", "pause", "continue", "tick", "tick", "tick", "qa", "inspect"):
        state = reduce(state, action)
        render(state, console)
        console.print(f"[dim]Applied: {action}[/]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    demo() if args.demo else interactive()
