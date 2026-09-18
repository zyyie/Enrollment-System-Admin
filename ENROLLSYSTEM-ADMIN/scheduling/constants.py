"""Scheduling constants — hard/soft constraint limits."""

# Maximum subject-section assignments per teacher per semester (G11+G12, A+B combined).
MAX_TEACHER_ASSIGNMENTS_PER_SEMESTER = 4

# Default enrollment cap per class section when room capacity is unknown.
DEFAULT_CLASS_MAX_SLOTS = 40

# Fallback room pool when Supabase has no rooms configured yet.
DEFAULT_SCHEDULER_ROOMS = [
    *[f"NB{num}" for num in range(101, 125)],
    "LAB1",
    "LAB2",
    "LAB3",
    "LAB4",
    "COOKERY-LAB1",
    "COOKERY-LAB2",
    "EIM-LAB1",
    "EIM-LAB2",
]

# Keep OR-Tools models small enough for ~20s solves on a single strand.
MAX_CANDIDATES_COLLECT = 320
MAX_CANDIDATES_PER_TASK = 128
MAX_PATTERNS_PER_TASK = 200
MAX_ROOMS_PER_PATTERN = 5
MAX_TEACHERS_PER_PATTERN = 4
ORTOOLS_FAST_TIME_LIMIT_SEC = 8.0
ORTOOLS_FAST_RETRY_ATTEMPTS = 2
ORTOOLS_RETRY_ATTEMPTS = 3
# Many saved strands (2nd sem) tighten the grid — need longer solves and more room options.
ORTOOLS_CONGESTED_TIME_LIMIT_SEC = 12.0
ORTOOLS_CONGESTED_RETRY_ATTEMPTS = 5
CONGESTED_EXISTING_THRESHOLD = 30
CONGESTED_OCCUPIED_KEYS_THRESHOLD = 280
