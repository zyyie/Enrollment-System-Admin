"""Free local smart scheduler — greedy-first when fast, OR-Tools with limited retries."""

from __future__ import annotations

import time

from .conflict_validator import validate_schedule
from .constants import (
    CONGESTED_EXISTING_THRESHOLD,
    ORTOOLS_CONGESTED_RETRY_ATTEMPTS,
    ORTOOLS_CONGESTED_TIME_LIMIT_SEC,
    ORTOOLS_FAST_RETRY_ATTEMPTS,
    ORTOOLS_FAST_TIME_LIMIT_SEC,
    ORTOOLS_RETRY_ATTEMPTS,
)
from .greedy_scheduler import GreedyScheduler
from .models import ScheduleAssignment, SchedulerInput
from .ortools_scheduler import OrtoolsScheduler


class SmartScheduler:
    """Greedy-first for speed; OR-Tools when greedy alone is not enough."""

    def __init__(self):
        self._ortools = OrtoolsScheduler()
        self._greedy = GreedyScheduler()

    def generate(
        self,
        scheduler_input: SchedulerInput,
        *,
        existing_assignments: list[ScheduleAssignment] | None = None,
        teachers: list[dict] | None = None,
        scheduling_context: dict | None = None,
        prefer_fast: bool = False,
    ) -> list[ScheduleAssignment]:
        existing = list(existing_assignments or [])
        congested = len(existing) >= CONGESTED_EXISTING_THRESHOLD
        fast_mode = (prefer_fast or len(existing) <= 120) and not congested

        greedy_strategies = [
            {},
            {"reverse_patterns": True, "shuffle_subjects": True},
            {"reverse_subjects": True, "reverse_rooms": True},
            {"shuffle_subjects": True, "shuffle_patterns": True},
            {"shuffle_subjects": True, "shuffle_rooms": True},
            {"reverse_rooms": True, "reverse_subjects": True, "shuffle_patterns": True},
        ]

        def _validate(assignments: list[ScheduleAssignment]) -> bool:
            grade = scheduler_input.grade_level or ""
            for assignment in assignments:
                if grade and not assignment.grade_level:
                    assignment.grade_level = grade
            result = validate_schedule(assignments, teachers=teachers, require_faculty=False)
            return result.valid

        def _try_greedy(
            strategies: list[dict] | None = None,
            *,
            placement_teachers: list[dict] | None = None,
        ) -> list[ScheduleAssignment]:
            last_error: RuntimeError | None = None
            teacher_pool = teachers if placement_teachers is None else placement_teachers
            for strategy in strategies or greedy_strategies:
                try:
                    assignments = self._greedy.generate(
                        scheduler_input,
                        existing_assignments=existing,
                        teachers=teacher_pool,
                        scheduling_context=scheduling_context,
                        **strategy,
                    )
                    if _validate(assignments):
                        return assignments
                    last_error = RuntimeError("Greedy schedule had section/time overlaps")
                except RuntimeError as err:
                    last_error = err
            raise RuntimeError(
                str(last_error) if last_error else "Could not build a conflict-free schedule"
            )

        def _try_ortools(
            seed: int,
            *,
            time_limit_sec: float,
            teacher_pool: list[dict] | None = None,
        ) -> list[ScheduleAssignment]:
            assignments = self._ortools.generate(
                scheduler_input,
                existing_assignments=existing,
                teachers=teacher_pool if teacher_pool is not None else teachers,
                scheduling_context=scheduling_context,
                time_limit_sec=time_limit_sec,
                random_seed=seed,
            )
            if not _validate(assignments):
                raise RuntimeError("OR-Tools schedule had section/time overlaps")
            return assignments

        def _ortools_sweep(
            *,
            retries: int,
            time_limit_sec: float,
            teacher_pool: list[dict] | None = None,
        ) -> list[ScheduleAssignment]:
            base_seed = int(time.time() * 1000) % 1_000_000
            last_error: RuntimeError | None = None
            for attempt in range(retries):
                seed = base_seed + attempt * 7919
                try:
                    return _try_ortools(
                        seed,
                        time_limit_sec=time_limit_sec,
                        teacher_pool=teacher_pool,
                    )
                except RuntimeError as err:
                    last_error = err
            raise RuntimeError(
                str(last_error) if last_error else "Could not build a conflict-free schedule"
            ) from last_error

        base_seed = int(time.time() * 1000) % 1_000_000
        subject_count = len(scheduler_input.subjects or [])
        heavy_strand = subject_count >= 12
        heavy_greedy_strategies = [
            {"reverse_patterns": True, "shuffle_subjects": True},
            {"shuffle_subjects": True, "shuffle_patterns": True},
            {"reverse_rooms": True, "shuffle_subjects": True},
            {},
        ]

        if heavy_strand or congested:
            last_error: RuntimeError | None = None
            try:
                return _try_greedy(
                    heavy_greedy_strategies if heavy_strand else greedy_strategies[:4],
                    placement_teachers=[] if heavy_strand else None,
                )
            except RuntimeError as err:
                last_error = err

            ortools_retries = (
                ORTOOLS_CONGESTED_RETRY_ATTEMPTS
                if congested
                else ORTOOLS_FAST_RETRY_ATTEMPTS + 1
            )
            ortools_limit = (
                ORTOOLS_CONGESTED_TIME_LIMIT_SEC
                if congested
                else ORTOOLS_FAST_TIME_LIMIT_SEC
            )
            try:
                return _ortools_sweep(
                    retries=ortools_retries,
                    time_limit_sec=ortools_limit,
                    teacher_pool=[],
                )
            except RuntimeError as err:
                last_error = err

            raise RuntimeError(
                str(last_error) if last_error else "Could not build a conflict-free schedule"
            ) from last_error

        if fast_mode:
            last_error: RuntimeError | None = None

            try:
                return _try_greedy([{}])
            except RuntimeError as err:
                last_error = err

            for attempt in range(ORTOOLS_FAST_RETRY_ATTEMPTS + 1):
                seed = base_seed + attempt * 7919
                pools: list[list[dict]] = []
                if teachers:
                    pools.append(teachers)
                pools.append([])
                for pool in pools:
                    try:
                        return _try_ortools(
                            seed,
                            time_limit_sec=ORTOOLS_FAST_TIME_LIMIT_SEC,
                            teacher_pool=pool,
                        )
                    except RuntimeError as err:
                        last_error = err

            try:
                return _try_greedy(greedy_strategies[1:])
            except RuntimeError as greedy_error:
                message = str(last_error or greedy_error)
                if last_error and str(greedy_error) not in message:
                    message = f"{message} Greedy: {greedy_error}"
                raise RuntimeError(message) from greedy_error

        last_error = None
        for attempt in range(ORTOOLS_RETRY_ATTEMPTS):
            try:
                return _try_ortools(
                    base_seed + attempt * 7919,
                    time_limit_sec=ORTOOLS_FAST_TIME_LIMIT_SEC,
                )
            except RuntimeError as err:
                last_error = err

        if teachers:
            try:
                return _try_ortools(
                    base_seed + 9973,
                    time_limit_sec=ORTOOLS_FAST_TIME_LIMIT_SEC,
                    teacher_pool=[],
                )
            except RuntimeError as err:
                last_error = err

        try:
            return _try_greedy()
        except RuntimeError as greedy_error:
            message = str(last_error or greedy_error)
            if last_error and str(greedy_error) not in message:
                message = f"{message} Greedy: {greedy_error}"
            raise RuntimeError(message) from greedy_error
