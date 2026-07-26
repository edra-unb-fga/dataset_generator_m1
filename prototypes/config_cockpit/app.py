from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from model import initial_state, reduce, summary  # noqa: E402


KEYS = {
    "a": "appearance",
    "e": "effect",
    "r": "receipt",
    "g": "start",
    "p": "pause",
    "d": "drained",
    "c": "continue",
    "s": "stop",
    "1": "section:summary",
    "2": "section:appearance",
    "3": "section:performance",
    "4": "section:run-control",
}


def render(state: dict) -> None:
    print("\033[2J\033[H", end="")
    print("\033[1mPROTOTYPE — configuration cockpit\033[0m")
    print(json.dumps(summary(state), indent=2))
    print("\n\033[2m[1-4] section [a] appearance [e] add fog [r] receipt")
    print("[g] start [p] pause [d] drained [c] continue [s] stop [q] quit\033[0m")


def main() -> None:
    state = initial_state()
    while True:
        render(state)
        key = input("> ").strip().lower()
        if key == "q":
            break
        state = reduce(state, KEYS.get(key, "noop"))


if __name__ == "__main__":
    main()
