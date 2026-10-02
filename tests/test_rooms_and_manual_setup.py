from pathlib import Path

from app.db import Database
from app.models import Assignment, Teacher
from app.rules import RuleSet
from app.solver import PedagogicalSolver


ROOT = Path(__file__).resolve().parents[1]


def test_new_database_has_real_configurable_rooms(tmp_path):
    database = Database(tmp_path / "school.db")
    rooms = database.rooms()
    assert len(rooms) == 7
    assert sum(room.kind == "regular" for room in rooms) == 6
    preparatory = next(room for room in rooms if room.kind == "emergency")
    assert preparatory.availability["0"] == [(720, 1020)]
    assert preparatory.availability["5"] == [(480, 1020)]


def test_room_availability_drives_solver_capacity(tmp_path):
    database = Database(tmp_path / "school.db")
    first = next(room for room in database.rooms() if room.kind == "regular")
    database.update_room(first.id, first.name, first.kind, True, {"0": [[480, 600]]})
    policy = {"rooms": [
        {"name": room.name, "kind": room.kind, "enabled": room.enabled,
         "availability": room.availability}
        for room in database.rooms()
    ]}
    solver = PedagogicalSolver(RuleSet(ROOT / "config" / "rules_2026_2027.json"), policy=policy)
    assert solver._room_capacity(0, 500) == 6
    assert solver._room_capacity(0, 700) == 5
    assert solver._room_capacity(0, 800) == 6


def test_director_reviewed_teacher_is_authorized_by_checked_subjects():
    teacher = Teacher(1, "مدرس", "إسناد يدوي", 1080, ["التربية البدنية"])
    assert PedagogicalSolver._has_subject_expertise(teacher, "التربية البدنية")


def test_multiple_teachers_can_share_subject_and_class_permissions(tmp_path):
    database = Database(tmp_path / "school.db")
    database.add_class("السنة الأولى أ", 1, "morning")
    class_id = database.classes()[0].id
    first_id = database.add_teacher("الأول", "إسناد يدوي", 1080, ["العربية"])
    second_id = database.add_teacher("الثاني", "إسناد يدوي", 1080, ["العربية"])
    database.set_teacher_classes(first_id, [class_id])
    database.set_teacher_classes(second_id, [class_id])
    teachers = {teacher.id: teacher for teacher in database.teachers()}
    solver = PedagogicalSolver(RuleSet(ROOT / "config" / "rules_2026_2027.json"))
    assert solver._teacher_can_teach(teachers[first_id], class_id, "العربية")
    assert solver._teacher_can_teach(teachers[second_id], class_id, "العربية")
    assert not solver._teacher_can_teach(teachers[first_id], class_id, "الفرنسية")
