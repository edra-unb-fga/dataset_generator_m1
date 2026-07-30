from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import ResolvedProfile
from .performance import DEFAULT_OBSERVATION_PATH, environment_class
from .preflight import PreflightRequest, run_preflight


def _binding_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class PreparationRequest:
    resolved: ResolvedProfile
    output_dir: Path
    workers: int
    observation_path: Path = DEFAULT_OBSERVATION_PATH


@dataclass(frozen=True)
class PreparedGeneration:
    resolved: ResolvedProfile
    output_dir: Path
    workers: int
    environment: dict[str, Any]
    preflight: dict[str, Any]
    observation_path: Path
    binding_hash: str

    def require_compatible(self, resolved: ResolvedProfile, output_dir: str | Path, workers: int) -> None:
        current = _binding_hash(
            {
                "contract_hash": resolved.contract_hash,
                "output_dir": str(Path(output_dir).resolve()),
                "workers": workers,
                "environment": environment_class(),
            }
        )
        if current != self.binding_hash:
            raise ValueError("Prepared generation was invalidated by a contract, output, worker, or environment change")


def prepare_generation(
    request: PreparationRequest,
    *,
    probe_runner: Callable[[], list[dict[str, Any]]] | None = None,
) -> PreparedGeneration:
    environment = environment_class()
    output_dir = request.output_dir.resolve()
    preflight = run_preflight(
        PreflightRequest(request.resolved, output_dir, request.workers, request.observation_path),
        probe_runner=probe_runner,
    )
    binding = _binding_hash(
        {
            "contract_hash": request.resolved.contract_hash,
            "output_dir": str(output_dir),
            "workers": request.workers,
            "environment": environment,
        }
    )
    return PreparedGeneration(
        resolved=request.resolved,
        output_dir=output_dir,
        workers=request.workers,
        environment=environment,
        preflight=preflight,
        observation_path=request.observation_path,
        binding_hash=binding,
    )
