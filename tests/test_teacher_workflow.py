import sqlite3
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import Database
from app.demo_data import populate_demo_database
from app.models import Assignment, ComplementaryWorkload, SchoolClass, Teacher
from app.rules import RuleSet
from app.solver import PedagogicalSolver, SolverError
from app.teacher_import import extract_teacher_names_from_docx


def test_demo_database_is_complete_and_ready_to_preview(tmp_path):
    database = Database(tmp_path / "demo.db")
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    result = populate_demo_database(database, rules, replace=True, generate=True)

    assert len(database.classes()) == 9
    assert len(database.teachers()) == 12
    assert len(database.assignments()) > 0
    assert len(database.lessons()) > 0
    assert result is not None
    assert all(teacher.max_weekly_minutes == 1080 for teacher in database.teachers())
    assert all(set(teacher.subjects) == set(rules.all_subjects()) for teacher in database.teachers())
    assert any("طاقة المدرسين" in warning and "لا يمكن بلوغ الحجم المستهدف للجميع" in warning for warning in result.warnings)
    assert not any("دون أي إسناد" in warning for warning in result.warnings)
    database.close()


def test_manual_reassignment_uses_qualified_teacher_with_free_capacity_and_rebuilds(tmp_path):
    database = Database(tmp_path / "manual.db")
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    result = populate_demo_database(database, rules, replace=True, generate=True)
    loads = {teacher.id: 0 for teacher in database.teachers()}
    for item in result.assignments:
        loads[item.teacher_id] += item.weekly_minutes
    movable = next(
        item for item in result.assignments
        if item.weekly_minutes == 60 and loads[item.teacher_id] == 1080
    )
    receiver = next(
        teacher for teacher in database.teachers()
        if teacher.id != movable.teacher_id and loads[teacher.id] + movable.weekly_minutes <= teacher.max_weekly_minutes
    )
    revised = [
        Assignment(item.class_id, receiver.id if (item.class_id, item.subject) == (movable.class_id, movable.subject) else item.teacher_id,
                   item.subject, item.weekly_minutes)
        for item in result.assignments
    ]
    rebuilt = PedagogicalSolver(rules).rebuild(database.classes(), database.teachers(), revised)
    assert any(item.teacher_id == receiver.id and item.class_id == movable.class_id and item.subject == movable.subject for item in rebuilt.assignments)
    assert any(item.teacher_id == receiver.id and item.class_id == movable.class_id and item.subject == movable.subject for item in rebuilt.lessons)
    database.close()


def test_docx_teacher_import_reads_paragraphs_and_removes_duplicates(tmp_path):
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
      <w:p><w:r><w:t>قائمة المدرسين</w:t></w:r></w:p>
      <w:p><w:r><w:t>1. الأستاذ محمد بن سالم</w:t></w:r></w:p>
      <w:p><w:r><w:t>الأستاذة آمنة علي</w:t></w:r></w:p>
      <w:p><w:r><w:t>محمد بن سالم</w:t></w:r></w:p>
    </w:body></w:document>"""
    path = tmp_path / "teachers.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document.encode("utf-8"))
    assert extract_teacher_names_from_docx(path) == ["محمد بن سالم", "آمنة علي"]


def test_database_migrates_and_persists_teacher_guide_fields(tmp_path):
    path = tmp_path / "school.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE teachers(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,specialty TEXT NOT NULL DEFAULT '',max_weekly_minutes INTEGER NOT NULL DEFAULT 1080,subjects_json TEXT NOT NULL DEFAULT '[]')")
    connection.commit(); connection.close()
    database = Database(path)
    database.add_teacher("سلوى", "اللغة الفرنسية", 1080, ["الفرنسية"], "تكوين الفرنسية للسنة الثانية", 12)
    teacher = database.teachers()[0]
    assert teacher.training == "تكوين الفرنسية للسنة الثانية"
    assert teacher.experience_years == 12
    database.close()


def test_fixed_assignments_and_complementary_hours_survive_generated_clear(tmp_path):
    database = Database(tmp_path / "fixed.db")
    database.add_class("السنة الأولى أ", 1, "morning")
    database.add_teacher("المعلم", "اللغة العربية", 1080, ["العربية"])
    school_class = database.classes()[0]
    teacher = database.teachers()[0]
    fixed = [Assignment(school_class.id, teacher.id, "العربية", 540)]
    database.save_fixed_assignments(fixed)
    database.save_complementary_workloads([
        ComplementaryWorkload(None, teacher.id, 60, "تكميلية"),
        ComplementaryWorkload(None, teacher.id, 30, "دعم"),
    ])
    database.save_assignments(fixed)
    database.clear_generated()

    assert database.assignments() == []
    assert database.fixed_assignments() == fixed
    assert database.complementary_minutes() == {teacher.id: 90}
    database.close()


def test_database_migrates_existing_classes_without_guessing_their_shift(tmp_path):
    path = tmp_path / "old-classes.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE classes(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,grade INTEGER NOT NULL)"
    )
    connection.execute("INSERT INTO classes(name,grade) VALUES(?,?)", ("السنة الثانية أ", 2))
    connection.commit(); connection.close()

    database = Database(path)
    school_class = database.classes()[0]
    assert school_class.shift == "unassigned"
    assert school_class.shift_window is None
    database.update_class_shift(school_class.id, "afternoon")
    assert database.classes()[0].shift == "afternoon"
    assert database.classes()[0].shift_window == (720, 1020)
    database.close()


def test_class_shift_is_persisted_for_new_classes(tmp_path):
    database = Database(tmp_path / "shifts.db")
    database.add_class("السنة الأولى أ", 1, "morning")
    database.add_class("السنة الأولى ب", 1, "afternoon")
    assert [(item.name, item.shift) for item in database.classes()] == [
        ("السنة الأولى أ", "morning"),
        ("السنة الأولى ب", "afternoon"),
    ]
    database.close()


def test_timetable_respects_morning_and_afternoon_class_windows():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    subjects = list(rules.subjects(1))
    teacher = Teacher(1, "مدرس القسم", "متعدد الاختصاصات", 1200, subjects, "تكوين شامل", 10)

    for shift, lower, upper in (("morning", 480, 780), ("afternoon", 720, 1020)):
        school_class = SchoolClass(1, f"الأولى {shift}", 1, shift)
        assignments = [
            Assignment(school_class.id, teacher.id, subject, minutes)
            for subject, minutes in rules.subjects(1).items()
        ]
        lessons = PedagogicalSolver(rules)._build_timetable(
            [school_class], [teacher], assignments, variant=0
        )
        assert lessons
        assert all(lower <= lesson.start_minute for lesson in lessons)
        assert all(lesson.start_minute + lesson.duration <= upper for lesson in lessons)
        if shift == "morning":
            assert min(lesson.start_minute for lesson in lessons) == 480
        else:
            assert max(lesson.start_minute + lesson.duration for lesson in lessons) == 1020


def test_second_grade_french_uses_trained_specialist():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    subjects = list(rules.subjects(2))
    general = Teacher(1, "مدرس عام", "تعليم ابتدائي عام", 1800,
                      [s for s in subjects if s not in {"الفرنسية", "التربية البدنية"}],
                      "دون تكوين خاص", 15)
    french = Teacher(2, "مدرس فرنسية", "اللغة الفرنسية", 300, ["الفرنسية"], "تكوين الفرنسية للسنة الثانية", 5)
    sport = Teacher(3, "مدرس رياضة", "التربية البدنية", 300, ["التربية البدنية"], "دون تكوين خاص", 5)
    result = PedagogicalSolver(rules).solve([SchoolClass(1, "الثانية أ", 2)], [general, french, sport])
    french_assignment = next(item for item in result.assignments if item.subject == "الفرنسية")
    assert french_assignment.teacher_id == french.id
    assert len({item.teacher_id for item in result.assignments if item.subject not in {"الفرنسية", "الإنجليزية", "التربية البدنية", "التربية التكنولوجية"}}) <= 2


def test_physical_education_is_assigned_to_specialist_and_keeps_full_class_total():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    school_class = SchoolClass(1, "الأولى أ", 1)
    teachers = _teachers_for_grade(rules, 1)
    result = PedagogicalSolver(rules).solve([school_class], teachers)
    sport = next(item for item in result.assignments if item.subject == "التربية البدنية")
    sport_teacher = next(teacher for teacher in teachers if teacher.id == sport.teacher_id)

    assert sport.weekly_minutes == rules.subjects(1)["التربية البدنية"]
    assert PedagogicalSolver._has_subject_expertise(sport_teacher, "التربية البدنية")
    assert sum(item.weekly_minutes for item in result.assignments) == sum(rules.subjects(1).values())


def test_manual_physical_education_assignment_requires_specialist():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    school_class = SchoolClass(1, "الأولى أ", 1)
    teachers = _teachers_for_grade(rules, 1)
    general = next(item for item in teachers if item.specialty == "تعليم ابتدائي عام")
    result = PedagogicalSolver(rules).solve([school_class], teachers)
    assignments = [
        Assignment(item.class_id, general.id if item.subject == "التربية البدنية" else item.teacher_id,
                   item.subject, item.weekly_minutes)
        for item in result.assignments
    ]
    try:
        PedagogicalSolver(rules).rebuild([school_class], teachers, assignments, optimize=False)
    except SolverError as error:
        assert "التربية البدنية" in str(error)
    else:
        raise AssertionError("Physical education must require a specialist teacher")


def test_required_second_grade_french_is_reserved_before_other_work():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    subjects = list(rules.subjects(2))
    specialist = Teacher(
        1, "مختص الفرنسية", "اللغة الفرنسية", 300, subjects,
        "تكوين الفرنسية للسنة الثانية", 10,
    )
    general = Teacher(
        2, "مدرس عام", "تعليم ابتدائي عام", 3000,
        [subject for subject in subjects if subject not in {"الفرنسية", "التربية البدنية"}],
        "دون تكوين خاص", 15,
    )
    sport = Teacher(3, "مدرس رياضة", "التربية البدنية", 300, ["التربية البدنية"], "دون تكوين خاص", 5)
    result = PedagogicalSolver(rules).solve(
        [SchoolClass(1, "الثانية أ", 2)], [specialist, general, sport]
    )
    french = next(item for item in result.assignments if item.subject == "الفرنسية")
    assert french.teacher_id == specialist.id


def test_clear_error_when_total_teacher_capacity_is_insufficient():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    teacher = Teacher(
        1, "مدرس", "متعدد الاختصاصات", 60,
        list(rules.subjects(1)), "دون تكوين خاص", 10,
    )
    try:
        PedagogicalSolver(rules).solve([SchoolClass(1, "الأولى أ", 1)], [teacher])
    except SolverError as error:
        assert "يتجاوز طاقة المدرسين" in str(error)
    else:
        raise AssertionError("Insufficient total capacity must be rejected clearly")


def _teachers_for_grade(rules, grade):
    subjects = list(rules.subjects(grade))
    specialist_subjects = {"الفرنسية", "الإنجليزية", "التربية البدنية", "التربية التكنولوجية"}
    teachers = [
        Teacher(1, "مدرس القسم", "تعليم ابتدائي عام", 3000,
                [subject for subject in subjects if subject not in specialist_subjects],
                "دون تكوين خاص", 15)
    ]
    profiles = {
        "الفرنسية": ("اللغة الفرنسية", "تكوين الفرنسية للسنة الثانية"),
        "الإنجليزية": ("اللغة الإنجليزية", "تكوين اللغة الإنجليزية"),
        "التربية البدنية": ("التربية البدنية", "دون تكوين خاص"),
        "التربية التكنولوجية": ("التربية التكنولوجية", "دون تكوين خاص"),
    }
    for subject in specialist_subjects.intersection(subjects):
        specialty, training = profiles[subject]
        teachers.append(Teacher(len(teachers) + 1, f"مدرس {subject}", specialty, 1000, [subject], training, 6))
    return teachers


def test_all_grades_have_exact_minutes_no_overlap_and_required_distribution():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    for grade in range(1, 7):
        school_class = SchoolClass(grade, f"القسم {grade}", grade)
        result = PedagogicalSolver(rules).solve([school_class], _teachers_for_grade(rules, grade))
        totals = {}
        occupied = set()
        teacher_days = {}
        teacher_daily = {}
        for lesson in result.lessons:
            totals[lesson.subject] = totals.get(lesson.subject, 0) + lesson.duration
            teacher_days.setdefault(lesson.teacher_id, set()).add(lesson.day)
            teacher_daily[(lesson.teacher_id, lesson.day)] = teacher_daily.get((lesson.teacher_id, lesson.day), 0) + lesson.duration
            for unit in range(lesson.start_minute // 10, (lesson.start_minute + lesson.duration) // 10):
                slot = (lesson.class_id, lesson.day, unit)
                assert slot not in occupied
                occupied.add(slot)
        assert totals == rules.subjects(grade)
        assert all(len(days) <= rules.teacher_max_working_days() for days in teacher_days.values())
        assert all(minutes <= rules.teacher_daily_max() for minutes in teacher_daily.values())
        for subject, rule in rules.grade(grade).get("subject_day_rules", {}).items():
            if rule.get("min_days"):
                actual_days = {lesson.day for lesson in result.lessons if lesson.subject == subject}
                assert len(actual_days) >= rule["min_days"]
        assert not any(warning.startswith("خطأ:") for warning in result.warnings)


def test_first_and_second_grade_main_teacher_five_days_is_guide_compliant():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    for grade in (1, 2):
        school_class = SchoolClass(grade, f"القسم {grade}", grade)
        result = PedagogicalSolver(rules).solve(
            [school_class], _teachers_for_grade(rules, grade),
        )
        main_teacher_days = {
            lesson.day for lesson in result.lessons if lesson.teacher_id == 1
        }
        assert len(main_teacher_days) == 5
        assert not any(
            "مدرس القسم يعمل 5 أيام بدل الهدف 4" in warning
            for warning in result.warnings
        )


def test_second_grade_rejects_french_teacher_without_specialty_or_training():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    subjects = list(rules.subjects(2))
    teacher = Teacher(1, "مدرس عام", "تعليم ابتدائي عام", 3000, subjects, "دون تكوين خاص", 20)
    try:
        PedagogicalSolver(rules).solve([SchoolClass(1, "الثانية أ", 2)], [teacher])
    except SolverError as error:
        assert "الفرنسية" in str(error)
    else:
        raise AssertionError("Grade-two French must require matching specialty or training")


def test_standard_eighteen_hours_are_balanced_over_four_days():
    rules = RuleSet(ROOT / "config" / "rules_2026_2027.json")
    teacher = Teacher(1, "مدرس", "تعليم ابتدائي عام", 1080, [], "دون تكوين خاص", 10)
    school_class = SchoolClass(1, "قسم اختباري", 5)
    assignments = [Assignment(1, 1, f"مادة اختبار {index}", 60) for index in range(18)]
    solver = PedagogicalSolver(rules)
    lessons = solver._build_timetable([school_class], [teacher], assignments)
    daily = {}
    for lesson in lessons:
        daily[lesson.day] = daily.get(lesson.day, 0) + lesson.duration
    assert sorted(daily.values(), reverse=True) == [300, 300, 240, 240]
