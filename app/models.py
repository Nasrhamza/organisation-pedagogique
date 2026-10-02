from dataclasses import dataclass, field
from typing import List, Dict, Tuple

CLASS_SHIFT_WINDOWS = {
    "morning": (8 * 60, 13 * 60),
    "afternoon": (12 * 60, 17 * 60),
}

CLASS_SHIFT_LABELS = {
    "morning": "صباحية 08:00–13:00",
    "afternoon": "مسائية 12:00–17:00",
    "unassigned": "الفترة غير محددة",
}

@dataclass
class School:
    name: str = ""
    delegation: str = ""
    district: str = ""
    director: str = ""
    academic_year: str = "2026-2027"

@dataclass
class SchoolClass:
    id: int | None
    name: str
    grade: int
    shift: str = "morning"

    @property
    def shift_window(self) -> tuple[int, int] | None:
        return CLASS_SHIFT_WINDOWS.get(self.shift)

    @property
    def shift_label(self) -> str:
        return CLASS_SHIFT_LABELS.get(self.shift, CLASS_SHIFT_LABELS["unassigned"])

@dataclass
class Teacher:
    id: int | None
    name: str
    specialty: str
    max_weekly_minutes: int
    subjects: List[str] = field(default_factory=list)
    training: str = ""
    experience_years: int = 0
    class_ids: List[int] = field(default_factory=list)

@dataclass
class Room:
    id: int | None
    name: str
    kind: str = "regular"
    enabled: bool = True
    availability: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)

@dataclass
class Assignment:
    class_id: int
    teacher_id: int
    subject: str
    weekly_minutes: int

@dataclass
class ComplementaryWorkload:
    id: int | None
    teacher_id: int
    weekly_minutes: int
    note: str = "ساعات تكميلية"

@dataclass
class Lesson:
    class_id: int
    teacher_id: int
    subject: str
    day: int
    start_minute: int
    duration: int

DAYS_AR = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]

def minute_to_hhmm(minute: int) -> str:
    h = minute // 60
    m = minute % 60
    return f"{h:02d}:{m:02d}"
