from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


_TRIGGER_LOCK = Lock()


@dataclass
class TriggerDecision:
    show: bool
    reason: str


def evaluate_trigger(
    db,
    ch,
    n,
    state_key,
):
    """
    Evaluate immediate boundary triggers only.

    Responsibilities:

      - first observation
      - channel tune/new playback session
      - program change
      - duplicate boundary suppression
      - persistent session/program state

    Percentage elapsed/remaining timing is handled by timeline.py.
    """

    with _TRIGGER_LOCK:
        state = db.get_runtime_trigger_state(
            state_key
        )

        session_key = (
            n.session_key
            or (
                state["session_key"]
                if state
                else "unknown-session"
            )
        )

        program_key = (
            n.program_key
            or (
                state["program_key"]
                if state
                else (
                    n.current_title
                    or "unknown-program"
                )
            )
        )

        current = n.elapsed_percent

        #
        # First observation establishes the baseline.
        #
        if state is None:
            fire = bool(
                ch.trigger_policy.show_on_tune
            )

            reason = (
                "channel-tune"
                if fire
                else "baseline"
            )

            db.set_runtime_trigger_state(
                state_key,
                ch.id,
                n.channel_id,
                session_key=
                    session_key,
                program_key=
                    program_key,
                last_elapsed_percent=
                    current,
                fired_tune=
                    fire,
                fired_program_change=
                    False,
                fired_position=
                    False,
                last_decision=(
                    "show"
                    if fire
                    else "suppress"
                ),
                last_reason=
                    reason,
            )

            return TriggerDecision(
                fire,
                reason,
            )

        #
        # New Channel_StartTime = new tune/playback session.
        #
        if (
            session_key
            != state["session_key"]
        ):
            fire = bool(
                ch.trigger_policy.show_on_tune
            )

            reason = (
                "channel-tune"
                if fire
                else "new-session"
            )

            db.set_runtime_trigger_state(
                state_key,
                ch.id,
                n.channel_id,
                session_key=
                    session_key,
                program_key=
                    program_key,
                last_elapsed_percent=
                    current,
                fired_tune=
                    fire,
                fired_program_change=
                    False,
                fired_position=
                    False,
                last_decision=(
                    "show"
                    if fire
                    else "suppress"
                ),
                last_reason=
                    reason,
            )

            return TriggerDecision(
                fire,
                reason,
            )

        #
        # Program changed inside the existing playback session.
        #
        if (
            program_key
            != state["program_key"]
        ):
            fire = bool(
                ch.trigger_policy.show_on_program_change
            )

            reason = (
                "program-change"
                if fire
                else "program-change-suppressed"
            )

            db.set_runtime_trigger_state(
                state_key,
                ch.id,
                n.channel_id,
                session_key=
                    session_key,
                program_key=
                    program_key,
                last_elapsed_percent=
                    current,
                fired_tune=
                    state["fired_tune"],
                fired_program_change=
                    fire,
                fired_position=
                    False,
                last_decision=(
                    "show"
                    if fire
                    else "suppress"
                ),
                last_reason=
                    reason,
            )

            return TriggerDecision(
                fire,
                reason,
            )

        #
        # Same session and program. No immediate boundary event.
        #
        db.set_runtime_trigger_state(
            state_key,
            ch.id,
            n.channel_id,
            session_key=
                session_key,
            program_key=
                program_key,
            last_elapsed_percent=(
                current
                if current is not None
                else state[
                    "last_elapsed_percent"
                ]
            ),
            fired_tune=
                state["fired_tune"],
            fired_program_change=
                state[
                    "fired_program_change"
                ],
            fired_position=
                state["fired_position"],
            last_decision=
                "suppress",
            last_reason=
                "no-trigger",
        )

        return TriggerDecision(
            False,
            "no-trigger",
        )


def claim_position_schedule(
    db,
    state_key,
    style_id,
    channel_id,
    schedule_reason,
):
    """
    Claim the future percentage event once its Packet timeline has
    been emitted.

    This prevents repeated ErsatzTV Script invocations for the same
    program from scheduling duplicate percentage overlays.
    """

    with _TRIGGER_LOCK:
        state = db.get_runtime_trigger_state(
            state_key
        )

        if not state:
            return

        previous_reason = (
            state.get(
                "last_reason"
            )
            or ""
        )

        combined_reason = (
            f"{previous_reason}+{schedule_reason}"
            if previous_reason
            else schedule_reason
        )

        db.set_runtime_trigger_state(
            state_key,
            style_id,
            channel_id,
            session_key=(
                state.get(
                    "session_key"
                )
                or ""
            ),
            program_key=(
                state.get(
                    "program_key"
                )
                or ""
            ),
            last_elapsed_percent=
                state.get(
                    "last_elapsed_percent"
                ),
            fired_tune=
                bool(
                    state.get(
                        "fired_tune"
                    )
                ),
            fired_program_change=
                bool(
                    state.get(
                        "fired_program_change"
                    )
                ),
            fired_position=
                True,
            last_decision=
                "timeline",
            last_reason=
                combined_reason,
        )
