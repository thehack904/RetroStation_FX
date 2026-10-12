from __future__ import annotations

import math

from dataclasses import asdict, dataclass
from typing import Optional

from .packet import clear_packet, repeat_packet
from .renderer import render_boundary_packet_stream, render_packet_stream


@dataclass
class PositionPlan:
    """
    Plan for one program-position trigger.

    Percentage events are represented inside the Packet timeline
    returned to ErsatzTV. No later HTTP callback is required.
    """

    status: str
    mode: str
    configured_percent: Optional[float]

    target_elapsed_percent: Optional[float] = None
    target_elapsed_seconds: Optional[float] = None
    target_frame: Optional[int] = None

    invocation_elapsed_seconds: Optional[float] = None
    delay_seconds: Optional[float] = None
    delay_frames: Optional[int] = None

    fps: Optional[float] = None

    reason: Optional[str] = None
    skip_reason: Optional[str] = None

    @property
    def scheduled(self):
        return self.status == "scheduled"

    def to_dict(self):
        return asdict(self)


@dataclass
class TimelineResult:
    payload: bytes
    total_frames: int
    region: tuple[int, int, int, int]
    schedule_reason: str


def plan_position_trigger(ch, n, state):
    """
    Build a timing plan for elapsed/remaining percentage mode.

    Important semantics:

      - no catch-up for thresholds already reached/passed
      - only one percentage event per program
      - remaining percentage converts to an elapsed target
      - ceil() is used so a trigger is never intentionally emitted
        before the calculated target frame
    """

    policy = ch.trigger_policy
    mode = policy.position_mode

    if mode == "off":
        return PositionPlan(
            status="off",
            mode="off",
            configured_percent=None,
            skip_reason="position-trigger-off",
        )

    configured = float(
        policy.position_percent
    )

    if state and state.get("fired_position"):
        return PositionPlan(
            status="already-claimed",
            mode=mode,
            configured_percent=configured,
            invocation_elapsed_seconds=n.elapsed_seconds,
            fps=n.fps,
            skip_reason="position-already-claimed",
        )

    if (
        n.elapsed_seconds is None
        or n.duration_seconds is None
        or n.duration_seconds <= 0
        or n.fps <= 0
    ):
        return PositionPlan(
            status="unavailable",
            mode=mode,
            configured_percent=configured,
            invocation_elapsed_seconds=n.elapsed_seconds,
            fps=n.fps,
            skip_reason="position-timing-unavailable",
        )

    if mode == "elapsed":
        target_elapsed_percent = configured

        reason = (
            "position-elapsed-"
            f"{configured:g}"
        )

    elif mode == "remaining":
        target_elapsed_percent = (
            100.0 - configured
        )

        reason = (
            "position-remaining-"
            f"{configured:g}"
        )

    else:
        return PositionPlan(
            status="unsupported",
            mode=str(mode),
            configured_percent=configured,
            invocation_elapsed_seconds=n.elapsed_seconds,
            fps=n.fps,
            skip_reason="position-mode-unsupported",
        )

    target_seconds = (
        n.duration_seconds
        * target_elapsed_percent
        / 100.0
    )

    delay_seconds = (
        target_seconds
        - n.elapsed_seconds
    )

    target_frame = max(
        0,
        int(
            math.ceil(
                target_seconds
                * n.fps
            )
        ),
    )

    if delay_seconds <= 0:
        return PositionPlan(
            status="missed",
            mode=mode,
            configured_percent=configured,
            target_elapsed_percent=
                target_elapsed_percent,
            target_elapsed_seconds=
                target_seconds,
            target_frame=
                target_frame,
            invocation_elapsed_seconds=
                n.elapsed_seconds,
            delay_seconds=
                delay_seconds,
            delay_frames=0,
            fps=n.fps,
            reason=reason,
            skip_reason=
                "threshold-already-reached",
        )

    delay_frames = max(
        1,
        int(
            math.ceil(
                delay_seconds
                * n.fps
            )
        ),
    )

    return PositionPlan(
        status="scheduled",
        mode=mode,
        configured_percent=configured,
        target_elapsed_percent=
            target_elapsed_percent,
        target_elapsed_seconds=
            target_seconds,
        target_frame=
            target_frame,
        invocation_elapsed_seconds=
            n.elapsed_seconds,
        delay_seconds=
            delay_seconds,
        delay_frames=
            delay_frames,
        fps=n.fps,
        reason=reason,
    )


def build_position_timeline(
    ch,
    n,
    boundary_show,
    plan,
    boundary_reason="",
):
    """
    Build the Packet stream for a scheduled percentage event.

    Existing renderer semantics are preserved:

      overlay frames
      Clear packet

    When there is an immediate tune/program-change overlay, its final
    Clear establishes the transparent canvas which Repeat then holds
    until the percentage event.
    """

    if not plan.scheduled:
        raise ValueError(
            "timeline requires a scheduled PositionPlan"
        )

    position_frames = int(
        plan.delay_frames
    )

    #
    # Immediate tune/program-change overlay plus future position event.
    #
    if boundary_show:
        first_payload, first_stats, _ = (
            render_boundary_packet_stream(
                ch,
                n,
                boundary_reason,
            )
        )

        #
        # The immediate overlay already spans the requested target.
        #
        if (
            position_frames
            <= first_stats.frames
        ):
            return TimelineResult(
                payload=
                    first_payload,
                total_frames=
                    first_stats.frames,
                region=
                    first_stats.region,
                schedule_reason=(
                    plan.reason
                    + "-covered-by-current-overlay"
                ),
            )

        second_payload, second_stats = (
            render_packet_stream(
                ch,
                n,
            )
        )

        gap_frames = (
            position_frames
            - first_stats.frames
        )

        payload = (
            first_payload
            + repeat_packet(
                gap_frames
            )
            + second_payload
        )

        return TimelineResult(
            payload=
                payload,
            total_frames=(
                first_stats.frames
                + gap_frames
                + second_stats.frames
            ),
            region=
                first_stats.region,
            schedule_reason=(
                plan.reason
                + "-scheduled"
            ),
        )

    #
    # Percentage event only. Begin on a transparent canvas.
    #
    overlay_payload, stats = (
        render_packet_stream(
            ch,
            n,
        )
    )

    if position_frames <= 1:
        prefix = clear_packet()

    else:
        prefix = (
            clear_packet()
            + repeat_packet(
                position_frames - 1
            )
        )

    payload = (
        prefix
        + overlay_payload
    )

    return TimelineResult(
        payload=
            payload,
        total_frames=(
            position_frames
            + stats.frames
        ),
        region=
            stats.region,
        schedule_reason=(
            plan.reason
            + "-scheduled"
        ),
    )
