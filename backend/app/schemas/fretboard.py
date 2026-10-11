"""Schemas for fretboard localization results and debugging."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FretboardPoint(BaseModel):
    """A 2D coordinate on the frame in pixels."""

    x: float = Field(description="X coordinate in pixels from left edge.")
    y: float = Field(description="Y coordinate in pixels from top edge.")


class FretboardGeometrySchema(BaseModel):
    """Geometric attributes of a localized fretboard candidate."""

    orientation_deg: float = Field(
        description="Orientation angle of the longitudinal axis in degrees relative to the horizontal (-90 to +90)."
    )
    estimated_length: float = Field(description="Estimated visible length of the neck corridor in pixels.")
    estimated_width: float = Field(description="Estimated width (thickness) of the fretboard in pixels.")
    aspect_ratio: float = Field(description="Aspect ratio (length to width ratio). Plausible necks are >= 2.2:1.")
    fret_count_estimate: int = Field(description="Estimated number of transverse frets detected.")
    transverse_edge_density: float = Field(description="Density of transverse edge transitions within the neck corridor.")


class FretboardDetectionResponse(BaseModel):
    """Response payload for frame fretboard localization."""

    job_id: str
    frame_index: int
    detected: bool = Field(description="True if a credible fretboard was localized; False otherwise.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.00 to 1.00). Credible detections have confidence >= 0.35 and fret evidence.",
    )
    polygon: list[FretboardPoint] | None = Field(
        default=None,
        description="4-corner bounding quadrilateral in image pixel coordinates [C0, C1, C2, C3], or null if not detected.",
    )
    geometry: FretboardGeometrySchema | None = Field(
        default=None,
        description="Geometric properties of the detected fretboard corridor, or null if not detected.",
    )
    failure_reason: str | None = Field(
        default=None,
        description="Diagnostic explanation when detection was rejected or failed.",
    )
    diagnostics: dict[str, Any] = Field(
        default_factory=dict,
        description="Diagnostic metrics and candidate evaluation details.",
    )
