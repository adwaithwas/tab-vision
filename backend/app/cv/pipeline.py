"""Computer vision pipeline.

Deliberately a *stub* for this milestone: the application foundation is
built, but no inference code exists yet. This module declares the intended
pipeline stages and where the future implementation will live, and raises a
clear ``NotImplementedError`` if anything tries to run analysis.

No predictions, accuracy metrics, or processing results are fabricated.
"""

from __future__ import annotations

from app.schemas.common import CapabilityStage

STAGES: list[CapabilityStage] = [
    CapabilityStage(
        key="preprocess",
        label="Video pre-processing",
        implemented=True,
        status="implemented",
        description=(
            "OpenCV decoding and interval-based frame extraction are implemented "
            "(one frame per second by default). Frame extraction only — no note "
            "detection is performed yet."
        ),
    ),
    CapabilityStage(
        key="fretboard_detection",
        label="Fretboard detection",
        implemented=False,
        status="planned",
        description="Locate the fretboard and frets in the camera frame.",
    ),
    CapabilityStage(
        key="string_fret_mapping",
        label="String / fret mapping",
        implemented=False,
        status="planned",
        description="Map observed geometry to string numbers and fret positions.",
    ),
    CapabilityStage(
        key="hand_detection",
        label="Hand / finger detection",
        implemented=False,
        status="planned",
        description="Detect fretting-hand position as a cue for note changes.",
    ),
    CapabilityStage(
        key="temporal_tracking",
        label="Temporal note tracking",
        implemented=False,
        status="planned",
        description="Track note candidates across frames and deduplicate events.",
    ),
    CapabilityStage(
        key="note_extraction",
        label="Note-event extraction",
        implemented=False,
        status="planned",
        description="Emit discrete note events with onset/duration estimates.",
    ),
    CapabilityStage(
        key="tab_generation",
        label="Tablature generation",
        implemented=False,
        status="planned",
        description="Render note events as six-string guitar tablature.",
    ),
]


def describe_pipeline() -> list[CapabilityStage]:
    """Public capability metadata for ``GET /api/capabilities``."""
    return STAGES


def run_pipeline(job_id: str) -> object:
    """Run the CV pipeline for a job.

    Raises
    ------
    NotImplementedError
        Always. The CV pipeline is intentionally not implemented in this
        milestone; nothing may pretend otherwise.
    """
    raise NotImplementedError(
        f"The CV pipeline is not implemented yet (job_id={job_id!r}). "
        "See docs/architecture.md for the planned implementation."
    )