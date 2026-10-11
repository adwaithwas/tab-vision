"""Schemas for the isolated fretboard-vision endpoints (experimental).

These schemas describe a *new*, additive vision API surface. No existing
audio-pipeline schema or response field is modified or redefined here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class VisionPoint(BaseModel):
    """A 2D coordinate on the frame in pixels."""

    x: float = Field(description="X coordinate in pixels from the left edge.")
    y: float = Field(description="Y coordinate in pixels from the top edge.")


class VisionString(BaseModel):
    """One measured string row (geometric position only, no pitch identity)."""

    position: int = Field(description="Row index in the rectified crop, 0 = topmost.")
    y_in_rectified: float = Field(description="Row position in rectified-crop pixels.")
    strength: float = Field(description="Relative peak strength, 0..1.")
    start: VisionPoint = Field(description="String start point in original frame coordinates.")
    end: VisionPoint = Field(description="String end point in original frame coordinates.")


class VisionFret(BaseModel):
    """One measured fret wire (geometric position only, no fret numbering)."""

    index: int = Field(description="Fret-wire index along the crop, 0 = nearest x=0 edge.")
    x_in_rectified: float = Field(description="Column position in rectified-crop pixels.")
    strength: float = Field(description="Relative peak strength, 0..1.")
    start: VisionPoint = Field(description="Wire start point in original frame coordinates.")
    end: VisionPoint = Field(description="Wire end point in original frame coordinates.")


class RectifiedSize(BaseModel):
    """Pixel dimensions of the rectified fretboard crop."""

    width: int
    height: int


class VisionAnalysisResponse(BaseModel):
    """Full geometry analysis of one extracted frame (vision-only, opt-in)."""

    job_id: str
    frame_index: int
    detected: bool = Field(
        description="True if the upstream detector localized a credible fretboard region."
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Upstream detection confidence (0.00-1.00)."
    )
    detection_source: str | None = Field(
        default=None,
        description="Which detector produced the polygon (ml / classical / hybrid variant).",
    )
    polygon: list[VisionPoint] | None = Field(
        default=None,
        description="Ordered 4-corner quadrilateral of the fretboard corridor, or null.",
    )
    rectified: RectifiedSize | None = Field(
        default=None,
        description="Size of the perspective-rectified crop, or null when not detected.",
    )
    strings: list[VisionString] = Field(
        default_factory=list,
        description=(
            "String rows measured from image evidence. Fewer than six entries means "
            "six evenly spaced strings could not be resolved — nothing is fabricated."
        ),
    )
    strings_detected: int = Field(
        description=(
            "Number of measured string rows. May be below 6 when six evenly "
            "spaced strings could not be resolved, or above 6 when candidate "
            "rows existed but no credible six-string fit was found (see limitations)."
        ),
    )
    frets: list[VisionFret] = Field(
        default_factory=list,
        description="Fret wires measured from image evidence (may be empty).",
    )
    frets_detected: int = Field(description="Number of measured fret wires.")
    failure_reason: str | None = Field(
        default=None, description="Diagnostic reason when detection was rejected."
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Plain-language caveats about this specific analysis.",
    )
    diagnostics: dict[str, Any] = Field(
        default_factory=dict, description="Raw diagnostic metrics from the detectors."
    )
    images: dict[str, str | None] = Field(
        default_factory=dict,
        description="URLs of generated images (annotated / rectified), or null if unavailable.",
    )
