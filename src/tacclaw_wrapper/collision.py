"""Validated loading for TacClaw tool-frame collision sphere profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Dict, List, Optional, TextIO, Tuple, Union

import yaml


@dataclass(frozen=True)
class CollisionSphere:
    center_m: Tuple[float, float, float]
    radius_m: float

    def __post_init__(self) -> None:
        if len(self.center_m) != 3 or not all(math.isfinite(value) for value in self.center_m):
            raise ValueError("collision sphere center must contain three finite values")
        if not math.isfinite(self.radius_m) or self.radius_m <= 0.0:
            raise ValueError("collision sphere radius must be finite and positive")


@dataclass(frozen=True)
class ToolCollisionModel:
    frame: str
    geometry_source: str
    measured_or_cad_validated: bool
    assumptions: Tuple[str, ...]
    spheres: Tuple[CollisionSphere, ...]

    def __post_init__(self) -> None:
        if self.frame != "tcp_link":
            raise ValueError("TacClaw collision model frame must be tcp_link")
        if not self.geometry_source:
            raise ValueError("geometry_source must not be empty")
        if not self.spheres:
            raise ValueError("collision model must contain at least one sphere")

    def as_curobo_spheres(self) -> List[Dict[str, object]]:
        return [
            {"center": list(sphere.center_m), "radius": sphere.radius_m}
            for sphere in self.spheres
        ]


def _load_document(stream: TextIO, source: str) -> ToolCollisionModel:
    document = yaml.safe_load(stream)
    try:
        raw = document["collision_model"]
        spheres = tuple(
            CollisionSphere(
                center_m=tuple(float(value) for value in sphere["center"]),
                radius_m=float(sphere["radius"]),
            )
            for sphere in raw["collision_spheres"]
        )
        model = ToolCollisionModel(
            frame=str(raw["frame"]),
            geometry_source=str(raw["geometry_source"]),
            measured_or_cad_validated=bool(raw["measured_or_cad_validated"]),
            assumptions=tuple(str(value) for value in raw.get("assumptions", ())),
            spheres=spheres,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid TacClaw collision model {source}: {exc}") from exc
    return model


def load_tool_collision_model(
    path: Optional[Union[str, Path]] = None,
) -> ToolCollisionModel:
    """Load an explicit profile, or the packaged unvalidated estimate by default."""

    if path is None:
        source = "tacclaw_wrapper.data/tacclaw_estimated_collision.yaml"
        with resources.open_text(
            "tacclaw_wrapper.data",
            "tacclaw_estimated_collision.yaml",
            encoding="utf-8",
        ) as stream:
            return _load_document(stream, source)

    model_path = Path(path).expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    with model_path.open("r", encoding="utf-8") as stream:
        return _load_document(stream, str(model_path))
