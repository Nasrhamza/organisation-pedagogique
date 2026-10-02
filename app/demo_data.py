"""Realistic, reproducible test data for the development version."""

from .models import School
from .solver import PedagogicalSolver


DEMO_TEACHERS = (
    ("آمنة بن سالم", 16),
    ("سامي العيادي", 13),
    ("نجلاء التليلي", 11),
    ("منير الجلاصي", 18),
    ("سناء الوريمي", 9),
    ("حسام العبيدي", 14),
    ("ريم الفرجاني", 7),
    ("ليلى بن عمر", 15),
    ("محمد أمين القاسمي", 10),
    ("سارة الشابي", 8),
    ("وليد السالمي", 12),
    ("مروان الزواغي", 6),
)


def populate_demo_database(db, rules, replace=False, generate=True):
    """Populate a complete six-grade school and optionally generate its timetable.

    Existing data is never touched unless ``replace`` is explicitly true.
    Returns the solver result when a schedule is generated, otherwise ``None``.
    """
    if (db.classes() or db.teachers()) and not replace:
        return None
    if replace:
        db.clear_all()

    db.set_school(School(
        name="المدرسة الابتدائية النموذجية النجاح",
        delegation="المندوبية الجهوية للتربية بتونس 1",
        district="الدائرة الأولى للتعليم الابتدائي",
        director="رياض ماضي",
        academic_year=rules.academic_year,
    ))

    for grade in range(1, 7):
        db.add_class(f"{rules.grade(grade)['name']} أ", grade, "morning")
    # Three additional sections use the requested أ / ب / د labels and bring
    # the weekly demand close to the 216-hour target of twelve teachers.
    db.add_class(f"{rules.grade(1)['name']} ب", 1, "afternoon")
    db.add_class(f"{rules.grade(1)['name']} د", 1, "morning")
    db.add_class(f"{rules.grade(2)['name']} ب", 2, "afternoon")

    all_subjects = rules.all_subjects()
    comprehensive_training = (
        "تكوين شامل متعدد الاختصاصات: العربية، الفرنسية، الإنجليزية، الرياضيات، العلوم، "
        "التربية التكنولوجية، التربية البدنية، التربية الموسيقية، التربية التشكيلية"
    )
    teachers = [
        (name, "متعدد الاختصاصات", 1080, all_subjects, comprehensive_training, experience)
        for name, experience in DEMO_TEACHERS
    ]
    db.add_teachers(teachers)

    if not generate:
        return None
    result = PedagogicalSolver(rules).solve(db.classes(), db.teachers())
    # Demo generation is the only automatic-assignment shortcut.  Persist the
    # result as a director-owned fixed assignment so subsequent generations only
    # rebuild times and never silently change teachers.
    db.save_fixed_assignments(result.assignments)
    db.save_assignments(result.assignments)
    db.save_lessons(result.lessons)
    return result
