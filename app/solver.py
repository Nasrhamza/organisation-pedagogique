from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable
from ortools.sat.python import cp_model
from .models import DAYS_AR, SchoolClass, Teacher, Assignment, Lesson
from .rules import RuleSet

SPECIALISTS = {"الفرنسية", "الإنجليزية", "التربية البدنية", "التربية التكنولوجية"}
SOCIAL_STUDIES = {"التاريخ", "الجغرافيا", "التربية المدنية"}

class SolverError(Exception):
    pass


class _PlacementError(SolverError):
    def __init__(self, message, assignment):
        super().__init__(message)
        self.assignment = assignment

@dataclass
class SolveResult:
    assignments: list[Assignment]
    lessons: list[Lesson]
    warnings: list[str]

class PedagogicalSolver:
    """Constraint optimizer for teacher assignment and weekly timetables.

    Hard constraints implemented:
    - every required subject gets its exact weekly duration
    - teacher must be authorized for the subject
    - teacher weekly load is not exceeded
    - no teacher/class overlap
    - grade daily maximum is respected
    - active-day count by grade
    - French/Arabic/Math distribution rules when feasible
    - English in grades 5/6 is split into two non-consecutive 60-min sessions
    - Math is not emitted as a 120-minute continuous block
    - technology/science are single weekly sessions where prescribed
    """

    def __init__(self, rules: RuleSet, policy: dict | None = None, preferred_rest_days=None):
        self.rules = rules
        self.policy = dict(policy or {})
        self.preferred_rest_days = {
            int(teacher_id): {int(day) for day in days}
            for teacher_id, days in (preferred_rest_days or {}).items()
        }
        self.warnings: list[str] = []

    def _policy(self, key: str, default=None):
        return self.policy.get(key, default)

    def _policy_minute(self, key: str, default: str) -> int:
        try:
            return self.rules.time_to_minute(str(self._policy(key, default)))
        except (TypeError, ValueError):
            return self.rules.time_to_minute(default)

    def _teacher_max_working_days(self) -> int:
        value = int(self._policy("max_teacher_working_days", self.rules.teacher_max_working_days()))
        return max(1, min(6, value))

    def _teacher_preferred_working_days(self) -> int:
        value = int(self._policy("preferred_teacher_working_days", self.rules.teacher_preferred_working_days()))
        return max(1, min(self._teacher_max_working_days(), value))

    def _teacher_daily_max(self) -> int:
        value = int(self._policy("teacher_daily_max_minutes", self.rules.teacher_daily_max()))
        return max(60, value)

    def _teacher_balanced_day(self) -> int:
        value = int(self._policy("teacher_balanced_day_minutes", self.rules.teacher_balanced_day()))
        return max(60, min(value, self._teacher_daily_max()))

    @staticmethod
    def _teacher_can_teach(teacher: Teacher, class_id: int, subject: str) -> bool:
        """A permission can be shared by any number of teachers."""
        return subject in teacher.subjects and (not teacher.class_ids or class_id in teacher.class_ids)

    @staticmethod
    def _format_minutes(minutes: int) -> str:
        hours, remainder = divmod(int(minutes), 60)
        if hours and remainder:
            return f"{hours} س و{remainder} دق"
        if hours:
            return "ساعة" if hours == 1 else f"{hours} س"
        return f"{remainder} دقيقة"

    def _validate_class_shifts(self, classes: list[SchoolClass]):
        missing = [school_class.name for school_class in classes if not school_class.shift_window]
        if missing:
            names = "، ".join(missing[:4])
            extra = f" و{len(missing) - 4} أقسام أخرى" if len(missing) > 4 else ""
            raise SolverError(
                f"حدّد الفترة الصباحية أو المسائية للأقسام التالية: {names}{extra}. "
                "اضغط على بطاقة القسم في صفحة الأقسام لاختيار الفترة."
            )
        for school_class in classes:
            weekly_capacity = sum(
                self._class_window(school_class, day)[1] - self._class_window(school_class, day)[0]
                for day in range(self.rules.active_days(school_class.grade))
            )
            weekly_required = sum(self.rules.subjects(school_class.grade).values())
            if weekly_required > weekly_capacity:
                raise SolverError(
                    f"الفترة المختارة للقسم «{school_class.name}» لا تتسع لحجمه الأسبوعي "
                    f"({self._format_minutes(weekly_required)})."
                )

    def _regular_room_capacity(self) -> int:
        rooms = self._policy("rooms", [])
        if rooms:
            return max(1, sum(
                1 for room in rooms
                if room.get("enabled", True) and room.get("kind") == "regular"
            ))
        return max(1, int(self._policy(
            "available_rooms", self.rules.assignment_rule("available_rooms", 6)
        )))

    def _room_capacity(self, day: int, minute: int) -> int:
        """Return usable rooms while keeping the preparatory room exceptional.

        The seventh room is occupied by preschool in weekday mornings.  It may
        only absorb overflow in the afternoon, or at any time on Saturday.
        """
        rooms = self._policy("rooms", [])
        if rooms:
            return sum(
                1 for room in rooms
                if room.get("enabled", True) and any(
                    int(start) <= minute < int(end)
                    for start, end in room.get("availability", {}).get(str(day), [])
                )
            )
        regular = self._regular_room_capacity()
        emergency = max(0, int(self._policy(
            "emergency_room_count", self.rules.assignment_rule("emergency_room_count", 1)
        )))
        all_saturday = bool(
            self._policy(
                "emergency_room_available_all_saturday",
                self.rules.assignment_rule("emergency_room_available_all_saturday", True),
            )
        )
        raw_start = str(
            self._policy(
                "emergency_room_available_from",
                self.rules.assignment_rule("emergency_room_available_from", "12:00"),
            )
        )
        try:
            hour, minute_part = (int(part) for part in raw_start.split(":", 1))
            afternoon_start = hour * 60 + minute_part
        except (TypeError, ValueError):
            afternoon_start = 12 * 60
        if (day == 5 and all_saturday) or minute >= afternoon_start:
            return regular + emergency
        return regular

    def solve(
        self, classes: list[SchoolClass], teachers: list[Teacher],
        complementary_minutes: dict[int, int] | None = None,
    ) -> SolveResult:
        self.warnings = []
        if not classes:
            raise SolverError("لا توجد أقسام. أضف الأقسام أولاً.")
        if not teachers:
            raise SolverError("لا يوجد مدرسون. أضف المدرسين أولاً.")
        self._validate_class_shifts(classes)
        assignments, lessons = self._solve_hybrid(classes, teachers)
        self._audit_result(classes, teachers, assignments, lessons, complementary_minutes)
        return SolveResult(assignments, lessons, self.warnings)

    def _build_timetable_with_repairs(self, classes, teachers, assignments):
        """Retry automatic generation by moving a blocking assignment safely.

        The greedy timetable can encounter a late cross-class activity after all
        teachers are nearly full.  Since automatic assignments are not user-locked,
        retry that whole subject with another qualified teacher before giving up.
        """
        tried_moves = set()
        for _attempt in range(max(12, len(assignments) * 2)):
            error = None
            for variant in range(12):
                try:
                    return self._build_timetable(classes, teachers, assignments, variant=variant)
                except _PlacementError as variant_error:
                    error = variant_error
            if error is not None:
                assignment = error.assignment
                loads = defaultdict(int)
                for item in assignments:
                    if item is not assignment:
                        loads[item.teacher_id] += item.weekly_minutes
                school_class = next(item for item in classes if item.id == assignment.class_id)
                core_subject = self._is_core_subject(school_class.grade, assignment.subject)
                core_teachers = {
                    item.teacher_id for item in assignments
                    if item is not assignment and item.class_id == assignment.class_id
                    and self._is_core_subject(school_class.grade, item.subject)
                }
                maximum_core = int(self.rules.assignment_rule("max_core_teachers_per_class", 2))
                candidates = []
                for teacher in teachers:
                    move_key = (assignment.class_id, assignment.subject, teacher.id)
                    if teacher.id == assignment.teacher_id or move_key in tried_moves:
                        continue
                    if not self._teacher_can_teach(teacher, assignment.class_id, assignment.subject):
                        continue
                    if loads[teacher.id] + assignment.weekly_minutes > teacher.max_weekly_minutes:
                        continue
                    if core_subject and len(core_teachers) >= maximum_core and teacher.id not in core_teachers:
                        continue
                    if (assignment.subject == "الفرنسية" and school_class.grade == 2
                            and self.rules.assignment_rule("french_year2_specialist_required", True)
                            and not self._has_subject_expertise(teacher, assignment.subject)):
                        continue
                    if (assignment.subject == "التربية البدنية"
                            and self.rules.assignment_rule("physical_education_specialist_required", True)
                            and not self._has_subject_expertise(teacher, assignment.subject)):
                        continue
                    candidates.append(teacher)
                if not candidates:
                    raise SolverError(str(error)) from error
                chosen = min(
                    candidates,
                    key=lambda teacher: (
                        loads[teacher.id] / max(1, teacher.max_weekly_minutes),
                        -teacher.experience_years,
                        teacher.name,
                    ),
                )
                tried_moves.add((assignment.class_id, assignment.subject, chosen.id))
                assignment.teacher_id = chosen.id
        raise SolverError("تعذر تركيب الجدول بعد تجربة البدائل المؤهلة. راجع الإسناد أو الأحجام الساعية.")

    def _build_fixed_timetable(self, classes, teachers, assignments):
        """Try several deterministic layouts without changing manual assignments."""
        last_error = None
        for variant in range(12):
            try:
                return self._build_timetable(classes, teachers, assignments, variant=variant)
            except _PlacementError as error:
                last_error = error
        raise SolverError(str(last_error) if last_error else "تعذر تركيب الجدول بالإسناد الحالي.")

    def rebuild(
        self, classes: list[SchoolClass], teachers: list[Teacher],
        assignments: list[Assignment], optimize: bool = True,
        complementary_minutes: dict[int, int] | None = None,
    ) -> SolveResult:
        """Validate manual assignments and rebuild a conflict-free timetable."""
        self.warnings = []
        self._validate_class_shifts(classes)
        class_by_id = {item.id: item for item in classes}
        teacher_by_id = {item.id: item for item in teachers}
        required_keys = {(item.id, subject): minutes for item in classes for subject, minutes in self.rules.subjects(item.grade).items()}
        seen = set()
        loads = defaultdict(int)
        for assignment in assignments:
            key = (assignment.class_id, assignment.subject)
            if key in seen:
                raise SolverError("يوجد إسناد مكرر لنفس المادة والقسم.")
            seen.add(key)
            school_class = class_by_id.get(assignment.class_id)
            teacher = teacher_by_id.get(assignment.teacher_id)
            if not school_class or not teacher or key not in required_keys:
                raise SolverError("الإسناد اليدوي يحتوي قسماً أو مادة أو مدرساً غير صالح.")
            if not self._teacher_can_teach(teacher, assignment.class_id, assignment.subject):
                raise SolverError(f"المدرس(ة) «{teacher.name}» غير مؤهل(ة) لمادة «{assignment.subject}».")
            if (assignment.subject == "التربية البدنية"
                    and self.rules.assignment_rule("physical_education_specialist_required", True)
                    and not self._has_subject_expertise(teacher, assignment.subject)):
                raise SolverError(
                    f"مادة «التربية البدنية» بالقسم «{school_class.name}» تتطلب مدرساً مختصاً حسب الدليل."
                )
            if assignment.weekly_minutes != required_keys[key]:
                raise SolverError(f"الحجم الساعي لمادة «{assignment.subject}» بالقسم «{school_class.name}» غير مطابق للدليل.")
            loads[teacher.id] += assignment.weekly_minutes
            if loads[teacher.id] > teacher.max_weekly_minutes:
                raise SolverError(f"الإسناد اليدوي يتجاوز الحجم الأقصى للمدرس(ة) «{teacher.name}».")
        missing = set(required_keys) - seen
        if missing:
            school_class = class_by_id[next(iter(missing))[0]]
            raise SolverError(f"الإسناد اليدوي ناقص في القسم «{school_class.name}».")
        # Candidate lists may validate many alternatives. They use the fast path;
        # only the accepted manual change gets the bounded CP-SAT refinement.
        variants = 180 if optimize else 54
        try:
            lessons = self._search_best_timetable(classes, teachers, assignments, variants=variants)
        except SolverError:
            if not optimize:
                raise
            # A director-locked real assignment can be perfectly feasible while
            # the fast greedy layout misses it.  Let CP-SAT build the timetable
            # directly before reporting a false conflict.
            lessons = self._optimize_timetable(
                classes, teachers, assignments, initial_lessons=[], time_limit=30.0,
            )
        if optimize:
            lessons = self._refine_timetable(classes, teachers, assignments, lessons)
        self._audit_result(classes, teachers, assignments, lessons, complementary_minutes)
        return SolveResult(list(assignments), lessons, self.warnings)

    def audit(self, classes, teachers, assignments, lessons, complementary_minutes=None):
        """Audit saved data without modifying or regenerating it."""
        self.warnings = []
        self._audit_result(classes, teachers, assignments, lessons, complementary_minutes)
        return list(self.warnings)

    def _solve_hybrid(self, classes, teachers):
        """Build a valid schedule quickly, then improve it with bounded CP-SAT.

        The deterministic phase is a guaranteed warm start and fallback. CP-SAT
        may replace it only with a strictly better valid timetable.
        """
        try:
            assignments, lessons = self._solve_internal_optimized(classes, teachers)
        except SolverError as greedy_error:
            # Morning/evening class windows can make an otherwise balanced
            # assignment impossible to place.  Ask the exact model to change the
            # assignment as well as the times before declaring the input invalid.
            try:
                return self._solve_optimized(classes, teachers)
            except SolverError as exact_error:
                raise SolverError(
                    "تعذر إيجاد إسناد وجدول يحترمان فترات الأقسام. "
                    f"التحقق السريع: {greedy_error}  •  التحقق الدقيق: {exact_error}"
                ) from exact_error
        return assignments, self._refine_timetable(classes, teachers, assignments, lessons)

    def _refine_timetable(self, classes, teachers, assignments, initial_lessons):
        class_by_id = {item.id: item for item in classes}
        initial_score = self._timetable_score(classes, teachers, initial_lessons)
        # Nothing can improve a timetable that already meets the four-day goal.
        # A single class is also completely governed by its mandatory subject-day
        # rules, so an exact search would only repeat the same answer.
        preferred_saturday_end = self._policy_minute(
            "preferred_saturday_end",
            str(self.rules.assignment_rule("preferred_saturday_end", "13:00")),
        )
        keep_saturday_afternoon_free = bool(self._policy("saturday_afternoon_free", True))
        saturday_is_good = (
            initial_score[2] <= preferred_saturday_end
            if keep_saturday_afternoon_free else True
        )
        if (initial_score[0] == 0 and saturday_is_good) or len(classes) == 1:
            return initial_lessons
        session_count = sum(
            len(self._split_subject(
                class_by_id[assignment.class_id].grade,
                assignment.subject,
                assignment.weekly_minutes,
            ))
            for assignment in assignments
        )
        # This school-size range (10-20 teachers) benefits more from a polished
        # four-day result than from returning a merely feasible layout instantly.
        time_limit = max(12.0, min(45.0, 10.0 + session_count / 6.0))
        try:
            try:
                optimized = self._optimize_timetable(
                    classes, teachers, assignments,
                    initial_lessons=initial_lessons, time_limit=time_limit,
                    saturday_deadline=(preferred_saturday_end if keep_saturday_afternoon_free else None),
                )
            except SolverError:
                optimized = self._optimize_timetable(
                    classes, teachers, assignments,
                    initial_lessons=initial_lessons, time_limit=time_limit,
                )
        except SolverError:
            return initial_lessons
        return optimized if self._timetable_score(classes, teachers, optimized) < initial_score else initial_lessons

    def _solve_internal_optimized(self, classes, teachers):
        """Explore many deterministic assignment/layout combinations without external engines."""
        total_demand = sum(sum(self.rules.subjects(item.grade).values()) for item in classes)
        total_capacity = sum(item.max_weekly_minutes for item in teachers)
        if total_demand > total_capacity:
            raise SolverError(
                f"الحجم المطلوب ({self._format_minutes(total_demand)}) يتجاوز طاقة المدرسين "
                f"({self._format_minutes(total_capacity)}). أضف مدرسين أو راجع الأقسام."
            )

        best = None
        last_error = None
        assignment_variants = max(16, min(40, len(teachers) * 3))
        timetable_variants = max(54, min(108, len(classes) * 12))
        for assignment_variant in range(assignment_variants):
            self.warnings = []
            try:
                assignments = self._assign_teachers(classes, teachers, variant=assignment_variant)
                assignment_warnings = list(self.warnings)
                lessons = self._search_best_timetable(
                    classes, teachers, assignments, variants=timetable_variants,
                    variant_offset=assignment_variant * timetable_variants,
                )
            except SolverError as error:
                last_error = error
                continue
            score = self._solution_score(classes, teachers, assignments, lessons)
            candidate = (score, assignments, lessons, assignment_warnings)
            if best is None or score < best[0]:
                best = candidate
            # Zero teachers above four days and at most one hour shortage is the
            # practical optimum for inputs whose total demand is below capacity.
            if score[0] <= 60 and score[2] == 0:
                break

        if best is None:
            # Final repair pass moves the assignment that blocked placement and
            # retries alternatives before declaring the input incompatible.
            self.warnings = []
            assignments = self._assign_teachers(classes, teachers, variant=assignment_variants + 1)
            try:
                lessons = self._build_timetable_with_repairs(classes, teachers, assignments)
            except SolverError:
                raise SolverError(
                    "تعذر إيجاد حل بعد فحص بدائل الإسناد والتوقيت. "
                    f"آخر سبب: {last_error or 'الاختصاصات أو الأحجام غير متوافقة.'}"
                ) from last_error
            return assignments, lessons

        _score, assignments, lessons, assignment_warnings = best
        self.warnings = assignment_warnings
        return assignments, lessons

    def _search_best_timetable(self, classes, teachers, assignments, variants=240, variant_offset=0):
        """Keep the best valid layout instead of accepting the first greedy layout."""
        base_warnings = list(self.warnings)
        best = None
        last_error = None
        for step in range(variants):
            self.warnings = list(base_warnings)
            try:
                lessons = self._build_timetable(
                    classes, teachers, assignments, variant=variant_offset + step
                )
            except _PlacementError as error:
                last_error = error
                continue
            score = self._timetable_score(classes, teachers, lessons)
            if best is None or score < best[0]:
                best = (score, lessons, list(self.warnings))
                preferred_end = self._policy_minute(
                    "preferred_saturday_end",
                    str(self.rules.assignment_rule("preferred_saturday_end", "13:00")),
                )
                if score[0] == 0 and score[2] <= preferred_end:
                    break
        if best is None:
            self.warnings = base_warnings
            raise SolverError(str(last_error) if last_error else "تعذر تركيب جدول صالح.")
        self.warnings = best[2]
        return best[1]

    def _solution_score(self, classes, teachers, assignments, lessons):
        loads = defaultdict(int)
        for assignment in assignments:
            loads[assignment.teacher_id] += assignment.weekly_minutes
        shortages = [max(0, teacher.max_weekly_minutes - loads[teacher.id]) for teacher in teachers]
        timetable = self._timetable_score(classes, teachers, lessons)
        return (
            max(shortages, default=0), sum(value * value for value in shortages),
            *timetable,
        )

    def _teacher_preferred_days(self, teacher_id, class_by_id, scheduled_items):
        """Return the guide-aware target number of working days for one teacher.

        Four days remains the general preference.  Some official subject
        distributions, notably first- and second-year mathematics, require five
        distinct teaching days.  A teacher carrying such a subject must not be
        penalized or warned for following the ministry distribution.
        """
        preferred = self._teacher_preferred_working_days()
        durations = []
        for item in scheduled_items:
            if item.teacher_id != teacher_id:
                continue
            school_class = class_by_id.get(item.class_id)
            if not school_class:
                continue
            rule = self.rules.subject_rule(school_class.grade, item.subject)
            preferred = max(preferred, int(rule.get("min_days", 0) or 0))
            if hasattr(item, "weekly_minutes"):
                durations.extend(self._split_subject(
                    school_class.grade, item.subject, item.weekly_minutes,
                ))
            else:
                durations.append(item.duration)
        preferred = max(preferred, self._minimum_days_for_sessions(durations))
        return min(preferred, self._teacher_max_working_days())

    def _minimum_days_for_sessions(self, durations):
        """Exact small bin-packing lower bound for the teacher daily maximum."""
        durations = tuple(sorted((int(value) for value in durations if value), reverse=True))
        if not durations:
            return 0
        capacity = self._teacher_daily_max()
        lower = max(1, (sum(durations) + capacity - 1) // capacity)

        def fits(day_count):
            used = [0] * day_count

            def place(index):
                if index == len(durations):
                    return True
                duration = durations[index]
                tried = set()
                for day in range(day_count):
                    if used[day] in tried or used[day] + duration > capacity:
                        continue
                    tried.add(used[day])
                    used[day] += duration
                    if place(index + 1):
                        return True
                    used[day] -= duration
                    if used[day] == 0:
                        break
                return False

            return place(0)

        for day_count in range(lower, self._teacher_max_working_days() + 1):
            if fits(day_count):
                return day_count
        return self._teacher_max_working_days()

    def _timetable_score(self, classes, teachers, lessons):
        class_by_id = {school_class.id: school_class for school_class in classes}
        workdays = {
            teacher.id: len({lesson.day for lesson in lessons if lesson.teacher_id == teacher.id})
            for teacher in teachers
        }
        over_preferred = sum(
            workdays[teacher.id] > self._teacher_preferred_days(
                teacher.id, class_by_id, lessons,
            )
            for teacher in teachers
        )
        alignment_gap = 0
        saturday_finish = 0
        occupied_rooms = defaultdict(int)
        for lesson in lessons:
            school_class = class_by_id.get(lesson.class_id)
            if not school_class or not school_class.shift_window:
                continue
            start, end = self._class_window(school_class, lesson.day)
            if school_class.shift == "afternoon" and lesson.day != 5:
                alignment_gap += max(0, end - (lesson.start_minute + lesson.duration))
            else:
                alignment_gap += max(0, lesson.start_minute - start)
            if lesson.day == 5:
                saturday_finish = max(saturday_finish, lesson.start_minute + lesson.duration)
            for unit in range(lesson.start_minute // 10, (lesson.start_minute + lesson.duration) // 10):
                occupied_rooms[(lesson.day, unit)] += 1
        emergency_slots = sum(
            count > self._regular_room_capacity()
            for (day, unit), count in occupied_rooms.items()
            if self._room_capacity(day, unit * 10) > self._regular_room_capacity()
        )
        return over_preferred, sum(workdays.values()), saturday_finish, emergency_slots, alignment_gap

    def _solve_optimized(self, classes, teachers):
        """Solve teacher assignment and timetable with exact CP-SAT constraints.

        Assignment solutions are optimized for balanced workload and competence.
        If the best assignment cannot be timetabled, it is excluded and the next
        best assignment is tried.  This is intentionally correctness-first.
        """
        total_demand = sum(sum(self.rules.subjects(item.grade).values()) for item in classes)
        total_capacity = sum(item.max_weekly_minutes for item in teachers)
        if total_demand > total_capacity:
            raise SolverError(
                f"الحجم المطلوب ({self._format_minutes(total_demand)}) يتجاوز طاقة المدرسين "
                f"({self._format_minutes(total_capacity)}). أضف مدرسين أو راجع الأقسام."
            )

        model, tasks, choices = self._assignment_model(classes, teachers)
        last_error = None
        for attempt in range(20):
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = max(4.0, min(20.0, len(tasks) / 5))
            solver.parameters.num_search_workers = 8
            solver.parameters.random_seed = 1729 + attempt
            status = solver.Solve(model)
            if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                if attempt == 0:
                    raise SolverError(
                        "لا يوجد إسناد يطابق الاختصاصات والأحجام المطلوبة. "
                        "راجع مواد تأهيل المدرسين أو أضف مدرساً مختصاً."
                    )
                break
            assignments = []
            selected = []
            for index, (school_class, subject, minutes) in enumerate(tasks):
                selected_var = None
                selected_teacher = None
                for teacher in teachers:
                    variable = choices.get((index, teacher.id))
                    if variable is not None and solver.Value(variable):
                        selected_var, selected_teacher = variable, teacher
                        break
                if selected_teacher is None:
                    raise SolverError("تعذر قراءة نتيجة الإسناد المحسوبة.")
                assignments.append(Assignment(school_class.id, selected_teacher.id, subject, minutes))
                selected.append(selected_var)
            try:
                # A deterministic valid timetable is enough to accept this exact
                # assignment immediately.  CP-SAT placement is reserved for
                # assignments the fast placer cannot fit; this avoids spending
                # 12 seconds re-proving an already valid schedule.
                lessons = self._build_fixed_timetable(classes, teachers, assignments)
                return assignments, lessons
            except SolverError as fast_error:
                try:
                    lessons = self._optimize_timetable(
                        classes, teachers, assignments, initial_lessons=[], time_limit=6.0
                    )
                    return assignments, lessons
                except SolverError as error:
                    last_error = SolverError(f"{fast_error} / {error}")
                    # Exclude this complete assignment and request the next best one.
                    model.Add(sum(selected) <= len(selected) - 1)
        raise SolverError(
            "وجد النظام إسنادات صحيحة، لكنه لم يجد جدولاً خالياً من التعارض بعد تجربة 20 بديلاً. "
            f"آخر سبب: {last_error or 'قيود التوقيت غير متوافقة.'}"
        )

    def _assignment_model(self, classes, teachers):
        model = cp_model.CpModel()
        tasks = [
            (school_class, subject, minutes)
            for school_class in classes
            for subject, minutes in self.rules.subjects(school_class.grade).items()
        ]
        choices = {}
        task_candidates = {}
        for index, (school_class, subject, _minutes) in enumerate(tasks):
            candidates = [teacher for teacher in teachers if self._teacher_can_teach(teacher, school_class.id, subject)]
            if (subject == "الفرنسية" and school_class.grade == 2
                    and self.rules.assignment_rule("french_year2_specialist_required", True)):
                candidates = [teacher for teacher in candidates if self._has_subject_expertise(teacher, subject)]
            if (subject == "التربية البدنية"
                    and self.rules.assignment_rule("physical_education_specialist_required", True)):
                candidates = [teacher for teacher in candidates if self._has_subject_expertise(teacher, subject)]
            if not candidates:
                raise SolverError(
                    f"لا يوجد مدرس مؤهل لمادة «{subject}» في القسم «{school_class.name}»."
                )
            variables = []
            for teacher in candidates:
                variable = model.NewBoolVar(f"assign_{index}_{teacher.id}")
                choices[(index, teacher.id)] = variable
                variables.append(variable)
            task_candidates[index] = candidates
            model.AddExactlyOne(variables)

        load_vars = {}
        shortage_squares = []
        max_shortfall = model.NewIntVar(0, max(item.max_weekly_minutes for item in teachers), "max_shortfall")
        for teacher in teachers:
            terms = [
                minutes * choices[(index, teacher.id)]
                for index, (_school_class, _subject, minutes) in enumerate(tasks)
                if (index, teacher.id) in choices
            ]
            load = model.NewIntVar(0, teacher.max_weekly_minutes, f"load_{teacher.id}")
            model.Add(load == sum(terms) if terms else load == 0)
            load_vars[teacher.id] = load
            shortfall = model.NewIntVar(0, teacher.max_weekly_minutes, f"shortfall_{teacher.id}")
            model.Add(shortfall == teacher.max_weekly_minutes - load)
            model.Add(max_shortfall >= shortfall)
            square = model.NewIntVar(0, teacher.max_weekly_minutes ** 2, f"shortfall_square_{teacher.id}")
            model.AddMultiplicationEquality(square, [shortfall, shortfall])
            shortage_squares.append(square)

        core_used = []
        maximum_core = int(self.rules.assignment_rule("max_core_teachers_per_class", 2))
        for school_class in classes:
            for teacher in teachers:
                variables = [
                    choices[(index, teacher.id)]
                    for index, (item_class, subject, _minutes) in enumerate(tasks)
                    if item_class.id == school_class.id and self._is_core_subject(item_class.grade, subject)
                    and (index, teacher.id) in choices
                ]
                if not variables:
                    continue
                used = model.NewBoolVar(f"core_{school_class.id}_{teacher.id}")
                model.Add(sum(variables) >= used)
                model.Add(sum(variables) <= len(variables) * used)
                core_used.append((school_class.id, used))
            relevant = [used for class_id, used in core_used if class_id == school_class.id]
            model.Add(sum(relevant) <= maximum_core)

        subject_teacher_used = []
        for subject in self.rules.all_subjects():
            for teacher in teachers:
                variables = [
                    choices[(index, teacher.id)]
                    for index, (_school_class, item_subject, _minutes) in enumerate(tasks)
                    if item_subject == subject and (index, teacher.id) in choices
                ]
                if not variables:
                    continue
                used = model.NewBoolVar(f"subject_{len(subject_teacher_used)}_{teacher.id}")
                model.Add(sum(variables) >= used)
                model.Add(sum(variables) <= len(variables) * used)
                subject_teacher_used.append(used)

        nonexpert_penalties = []
        experience_penalties = []
        for index, (_school_class, subject, _minutes) in enumerate(tasks):
            for teacher in task_candidates[index]:
                variable = choices[(index, teacher.id)]
                if subject in SPECIALISTS and not self._has_subject_expertise(teacher, subject):
                    nonexpert_penalties.append(variable)
                experience_penalties.append((50 - min(50, max(0, int(teacher.experience_years or 0)))) * variable)

        model.Minimize(
            max_shortfall * 1_000_000
            + sum(shortage_squares) * 100
            + sum(used for _class_id, used in core_used) * 10_000
            + sum(nonexpert_penalties) * 2_000
            + sum(subject_teacher_used) * 100
            + sum(experience_penalties)
        )
        return model, tasks, choices

    def _optimize_timetable(
        self, classes, teachers, assignments,
        initial_lessons=None, time_limit=12.0, saturday_deadline=None,
    ):
        """Create a conflict-free timetable and optimize teachers toward four days."""
        class_by_id = {item.id: item for item in classes}
        if initial_lessons is None:
            try:
                initial_lessons = self._build_fixed_timetable(classes, teachers, assignments)
            except SolverError:
                initial_lessons = []
        hint_slots = defaultdict(list)
        for lesson in sorted(initial_lessons, key=lambda item: (item.day, item.start_minute)):
            hint_slots[(lesson.class_id, lesson.teacher_id, lesson.subject, lesson.duration)].append(
                (lesson.day, lesson.start_minute)
            )
        model = cp_model.CpModel()
        saturday_finish = model.NewIntVar(0, 24 * 60, "saturday_finish")
        sessions = []
        for assignment in assignments:
            school_class = class_by_id[assignment.class_id]
            for sequence, duration in enumerate(
                    self._split_subject(school_class.grade, assignment.subject, assignment.weekly_minutes)):
                sessions.append((school_class, assignment, sequence, duration))

        class_intervals = defaultdict(list)
        teacher_intervals = defaultdict(list)
        room_slot_terms = defaultdict(list)
        class_day_terms = defaultdict(list)
        teacher_day_terms = defaultdict(list)
        teacher_shift_options = defaultdict(list)
        subject_day_terms = defaultdict(list)
        placement_vars = []
        session_options = []
        for index, (school_class, assignment, _sequence, duration) in enumerate(sessions):
            rule = self.rules.subject_rule(school_class.grade, assignment.subject)
            hints = hint_slots[(school_class.id, assignment.teacher_id, assignment.subject, duration)]
            hinted = hints.pop(0) if hints else None
            candidates = []
            options = []
            for day in range(self.rules.active_days(school_class.grade)):
                starts = set(self._optimized_candidate_starts(school_class, day, duration))
                if hinted and hinted[0] == day:
                    starts.add(hinted[1])
                for start in sorted(starts):
                    if self._avoid_window(rule, start, duration):
                        continue
                    presence = model.NewBoolVar(f"place_{index}_{day}_{start}")
                    model.AddHint(presence, int(hinted == (day, start)))
                    interval = model.NewOptionalIntervalVar(
                        start, duration, start + duration, presence, f"interval_{index}_{day}_{start}"
                    )
                    candidates.append(presence)
                    options.append((presence, day, start))
                    window_start, window_end = self._class_window(school_class, day)
                    if day == 5:
                        # Saturday is a short-day preference: use it only when the
                        # weekly volume requires it and finish as early as the
                        # class period permits.
                        alignment_penalty = 500 + max(0, start + duration - 12 * 60)
                        model.Add(saturday_finish >= start + duration).OnlyEnforceIf(presence)
                    else:
                        alignment_penalty = (
                            window_end - (start + duration)
                            if school_class.shift == "afternoon"
                            else start - window_start
                        )
                    placement_vars.append((presence, max(0, alignment_penalty)))
                    class_intervals[(school_class.id, day)].append(interval)
                    teacher_intervals[(assignment.teacher_id, day)].append(interval)
                    for unit in range(start // 10, (start + duration) // 10):
                        room_slot_terms[(day, unit)].append(presence)
                    class_day_terms[(school_class.id, day)].append((duration, presence))
                    teacher_day_terms[(assignment.teacher_id, day)].append((duration, presence))
                    teacher_shift_options[(assignment.teacher_id, day, school_class.shift)].append(
                        (presence, start, start + duration)
                    )
                    subject_day_terms[(school_class.id, assignment.subject, day)].append(presence)
            if not candidates:
                raise SolverError(
                    f"لا توجد فترة صالحة لحصة {assignment.subject} في {school_class.name}."
                )
            model.AddExactlyOne(candidates)
            session_options.append(options)

        for intervals in class_intervals.values():
            model.AddNoOverlap(intervals)
        for intervals in teacher_intervals.values():
            model.AddNoOverlap(intervals)
        transition = max(0, int(self._policy("teacher_transition_minutes", 0)))
        if transition:
            for teacher in teachers:
                for day in range(6):
                    morning = teacher_shift_options[(teacher.id, day, "morning")]
                    afternoon = teacher_shift_options[(teacher.id, day, "afternoon")]
                    for first, first_start, first_end in morning:
                        for second, second_start, second_end in afternoon:
                            separated = (
                                first_end + transition <= second_start
                                or second_end + transition <= first_start
                            )
                            if not separated:
                                model.Add(first + second <= 1)
        # Six ordinary rooms are always available.  The preparatory room is a
        # penalized overflow room: afternoon-only on weekdays and all Saturday.
        # Slot constraints express that time-varying capacity exactly.
        emergency_room_vars = []
        regular_room_limit = self._regular_room_capacity()
        for (day, unit), variables in room_slot_terms.items():
            capacity = self._room_capacity(day, unit * 10)
            if capacity > regular_room_limit:
                overflow = model.NewBoolVar(f"emergency_room_{day}_{unit}")
                model.Add(sum(variables) <= capacity)
                model.Add(sum(variables) <= regular_room_limit).OnlyEnforceIf(overflow.Not())
                emergency_room_vars.append(overflow)
            else:
                model.Add(sum(variables) <= capacity)

        for school_class in classes:
            at_limit = []
            maximum = self.rules.max_daily(school_class.grade)
            for day in range(self.rules.active_days(school_class.grade)):
                terms = class_day_terms[(school_class.id, day)]
                daily = sum(duration * variable for duration, variable in terms)
                model.Add(daily <= maximum)
                limit = self.rules.grade(school_class.grade).get("max_days_at_daily_limit")
                if limit is not None:
                    reached = model.NewBoolVar(f"class_limit_{school_class.id}_{day}")
                    model.Add(daily == maximum).OnlyEnforceIf(reached)
                    model.Add(daily <= maximum - 10).OnlyEnforceIf(reached.Not())
                    at_limit.append(reached)
            allowed = self.rules.grade(school_class.grade).get("max_days_at_daily_limit")
            if allowed is not None:
                model.Add(sum(at_limit) <= int(allowed))

            for subject, rule in self.rules.grade(school_class.grade).get("subject_day_rules", {}).items():
                day_vars = []
                for day in range(self.rules.active_days(school_class.grade)):
                    variables = subject_day_terms[(school_class.id, subject, day)]
                    used = model.NewBoolVar(f"subject_day_{school_class.id}_{len(day_vars)}_{day}")
                    if variables:
                        model.Add(sum(variables) >= used)
                        model.Add(sum(variables) <= len(variables) * used)
                    else:
                        model.Add(used == 0)
                    day_vars.append(used)
                minimum = int(rule.get("min_days", 0) or 0)
                if minimum:
                    model.Add(sum(day_vars) >= minimum)
                if rule.get("non_consecutive_days"):
                    for first, second in zip(day_vars, day_vars[1:]):
                        model.Add(first + second <= 1)

        day_used_vars = []
        over_preferred_vars = []
        preferred_rest_work_vars = []
        for teacher in teachers:
            teacher_days = []
            for day in range(6):
                terms = teacher_day_terms[(teacher.id, day)]
                used = model.NewBoolVar(f"teacher_day_{teacher.id}_{day}")
                variables = [variable for _duration, variable in terms]
                if variables:
                    model.Add(sum(variables) >= used)
                    model.Add(sum(variables) <= len(variables) * used)
                    model.Add(sum(duration * variable for duration, variable in terms) <= self._teacher_daily_max())
                else:
                    model.Add(used == 0)
                teacher_days.append(used)
                day_used_vars.append(used)
                if day in self.preferred_rest_days.get(int(teacher.id), set()):
                    preferred_rest_work_vars.append(used)
            days_count = sum(teacher_days)
            model.Add(days_count <= self._teacher_max_working_days())
            preferred_days = self._teacher_preferred_days(
                teacher.id, class_by_id, assignments,
            )
            over = model.NewBoolVar(f"over_preferred_{teacher.id}")
            model.Add(days_count <= preferred_days).OnlyEnforceIf(over.Not())
            model.Add(days_count >= preferred_days + 1).OnlyEnforceIf(over)
            over_preferred_vars.append(over)

        if saturday_deadline is not None:
            model.Add(saturday_finish <= int(saturday_deadline))

        model.Minimize(
            sum(over_preferred_vars) * 1_000_000_000
            + sum(day_used_vars) * 20_000_000
            + sum(preferred_rest_work_vars) * 1_000_000
            + saturday_finish * 10_000
            + sum(emergency_room_vars) * 1_000
            + sum((gap // 10) * variable for variable, gap in placement_vars)
        )
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = float(time_limit)
        solver.parameters.num_search_workers = 8
        solver.parameters.symmetry_level = 2
        status = solver.Solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise SolverError(
                "الإسناد المقترح لا يسمح بجدول يحترم التداخل والساعات وأيام الراحة."
            )

        lessons = []
        # Each presence name carries its session/day/start; iterate candidates again
        # through the model variables already stored in creation order.
        for (school_class, assignment, _sequence, duration), options in zip(sessions, session_options):
            found = False
            for variable, day, start in options:
                if solver.Value(variable):
                    lessons.append(Lesson(
                        school_class.id, assignment.teacher_id, assignment.subject, day, start, duration
                    ))
                    found = True
            if not found:
                raise SolverError("نتيجة التحسين ناقصة: توجد حصة دون توقيت.")
        return lessons

    def _optimized_candidate_starts(self, school_class: SchoolClass, day: int, duration: int):
        """Generate starts only inside the class's morning/evening period."""
        step = 60 if duration >= 60 else 10
        start, end = self._class_window(school_class, day)
        minute = start
        while minute + duration <= end:
            yield minute
            minute += step

    def _assign_teachers(self, classes, teachers, variant=0):
        loads = defaultdict(int)
        shift_loads = defaultdict(lambda: defaultdict(int))
        assignments = []
        subject_teachers = defaultdict(set)

        # Larger subjects are assigned first across the whole school. This avoids
        # fragmenting every teacher's remaining capacity with small activities and
        # then discovering too late that an 8- or 9-hour language block no longer fits.
        priority = ["العربية","الرياضيات","الإيقاظ العلمي","التربية الإسلامية","التربية الموسيقية","التربية التشكيلية",
                    "الفرنسية","الإنجليزية","التربية التكنولوجية","التربية البدنية","التاريخ","الجغرافيا","التربية المدنية"]
        priority_index = {subject: index for index, subject in enumerate(priority)}
        tasks = [
            (school_class, subject, minutes)
            for school_class in classes
            for subject, minutes in self.rules.subjects(school_class.grade).items()
        ]
        def eligible_count(task):
            school_class, subject, _minutes = task
            candidates = [teacher for teacher in teachers if self._teacher_can_teach(teacher, school_class.id, subject)]
            if (subject == "الفرنسية" and school_class.grade == 2
                    and self.rules.assignment_rule("french_year2_specialist_required", True)):
                candidates = [teacher for teacher in candidates if self._has_subject_expertise(teacher, subject)]
            return len(candidates)

        tasks.sort(key=lambda item: (
            0 if (item[1] == "الفرنسية" and item[0].grade == 2) else 1,
            eligible_count(item),
            0 if self._is_core_subject(item[0].grade, item[1]) else 1,
            -item[2], priority_index.get(item[1], len(priority)),
            (item[0].grade + variant) % 6,
            (item[0].id * 17 + variant * 13) % max(1, len(classes)),
        ))
        class_generalists = {school_class.id: None for school_class in classes}
        class_core_teachers = defaultdict(set)

        for cls, subject, minutes in tasks:
            core_teachers = class_core_teachers[cls.id]
            class_generalist = class_generalists[cls.id]
            candidates = [
                teacher for teacher in teachers
                if self._teacher_can_teach(teacher, cls.id, subject) and loads[teacher.id] + minutes <= teacher.max_weekly_minutes
            ]
            if subject == "الفرنسية" and cls.grade == 2 and self.rules.assignment_rule("french_year2_specialist_required", True):
                candidates = [teacher for teacher in candidates if self._has_subject_expertise(teacher, subject)]
                if not candidates:
                    raise SolverError(
                        f"مادة «الفرنسية» في السنة الثانية بالقسم «{cls.name}» تتطلب مدرساً مختصاً أو متكوّناً للغرض حسب الدليل."
                    )
            if subject == "التربية البدنية" and self.rules.assignment_rule("physical_education_specialist_required", True):
                candidates = [teacher for teacher in candidates if self._has_subject_expertise(teacher, subject)]
                if not candidates:
                    raise SolverError(
                        f"مادة «التربية البدنية» بالقسم «{cls.name}» تتطلب مدرساً مختصاً حسب الدليل."
                    )

            core_subject = self._is_core_subject(cls.grade, subject)
            maximum_core = int(self.rules.assignment_rule("max_core_teachers_per_class", 2))
            if core_subject and len(core_teachers) >= maximum_core:
                candidates = [teacher for teacher in candidates if teacher.id in core_teachers]
            if not candidates:
                detail = " مع احترام حدّ مدرسين اثنين للمواد الأساسية" if core_subject else ""
                raise SolverError(f"لا يوجد مدرس مؤهل ومتفرغ لمادة «{subject}» بالقسم «{cls.name}»{detail}.")

            chosen = min(
                candidates,
                key=lambda teacher: self._teacher_score(
                    teacher, subject, loads, shift_loads, cls.shift,
                    class_generalist, core_teachers, subject_teachers[subject], variant
                ),
            )

            if subject == "العربية" and class_generalist is None:
                class_generalists[cls.id] = chosen.id
            if core_subject:
                core_teachers.add(chosen.id)
            assignments.append(Assignment(cls.id, chosen.id, subject, minutes))
            loads[chosen.id] += minutes
            shift_loads[chosen.id][cls.shift] += minutes
            subject_teachers[subject].add(chosen.id)
            if not self._has_subject_expertise(chosen, subject) and subject in SPECIALISTS:
                self.warnings.append(
                    f"تنبيه: أُسندت مادة {subject} بالقسم {cls.name} إلى {chosen.name} دون اختصاص أو تكوين مطابق."
                )
        return assignments

    def _is_core_subject(self, grade: int, subject: str) -> bool:
        excluded = {"التربية البدنية", "التربية التكنولوجية"}
        if grade >= 2:
            excluded.update({"الفرنسية", "الإنجليزية"})
        return subject not in excluded

    @staticmethod
    def _has_subject_expertise(teacher: Teacher, subject: str) -> bool:
        # For manually reviewed files, the checked subject list is the director's
        # explicit authorization.  French in grade two and physical education
        # keep their stricter specialty checks elsewhere in the solver.
        # New teacher cards are explicitly reviewed by the director.  Legacy
        # and demo profiles keep their historical specialty ranking so existing
        # files continue to generate exactly as before.
        if (teacher.specialty == "إسناد يدوي" or subject in {"الإنجليزية", "التربية التكنولوجية"}) and subject in teacher.subjects:
            return True
        labels = f"{teacher.specialty} {teacher.training}".casefold()
        keywords = {
            "العربية": ("العربية",),
            "الفرنسية": ("الفرنسية", "français", "francais"),
            "الإنجليزية": ("الإنجليزية", "anglais", "english"),
            "الرياضيات": ("الرياضيات",),
            "الإيقاظ العلمي": ("العلوم", "علمي"),
            "التربية التكنولوجية": ("التكنولوجية", "تكنولوجيا"),
            "التربية البدنية": ("البدنية", "رياضة"),
            "التربية الموسيقية": ("الفنية", "الموسيقية"),
            "التربية التشكيلية": ("الفنية", "التشكيلية"),
        }.get(subject, (subject,))
        return any(keyword.casefold() in labels for keyword in keywords)

    def _teacher_score(
        self, teacher, subject, loads, shift_loads, class_shift,
        class_generalist, core_teachers, used_for_subject, variant=0,
    ):
        expertise = 0 if self._has_subject_expertise(teacher, subject) else 1
        if subject in SOCIAL_STUDIES and self.rules.assignment_rule("prefer_science_teacher_for_social_studies", True):
            expertise = 0 if any(word in teacher.specialty for word in ("علوم", "رياضيات")) else expertise
        same_generalist = 0 if class_generalist == teacher.id else 1
        same_core_team = 0 if teacher.id in core_teachers else 1
        consolidate_specialist = 0 if teacher.id in used_for_subject else 1
        experience = -max(0, int(teacher.experience_years or 0))
        load_ratio = loads[teacher.id] / max(1, teacher.max_weekly_minutes)
        same_shift_ratio = shift_loads[teacher.id][class_shift] / max(1, teacher.max_weekly_minutes)
        rotation = (int(teacher.id or 0) * 37 + variant * 19) % 97
        if subject in SPECIALISTS:
            # Keep competence first, then balance the load. Consolidation remains
            # a tie-breaker instead of filling one specialist while peers stay idle.
            return expertise, same_shift_ratio, load_ratio, consolidate_specialist, rotation, experience, teacher.name
        return same_generalist, same_core_team, expertise, same_shift_ratio, load_ratio, rotation, experience, teacher.name

    def _build_timetable(self, classes, teachers, assignments, variant=0):
        class_by_id = {school_class.id: school_class for school_class in classes}
        assigned_loads = defaultdict(int)
        for assignment in assignments:
            assigned_loads[assignment.teacher_id] += assignment.weekly_minutes
        teacher_busy = defaultdict(set)  # (day, ten-minute unit)
        teacher_days = defaultdict(set)
        teacher_daily_used = defaultdict(int)
        teacher_placed_lessons = defaultdict(list)
        class_busy = defaultdict(set)
        occupied_rooms = defaultdict(int)
        class_daily_used = {
            school_class.id: [0] * self.rules.active_days(school_class.grade)
            for school_class in classes
        }
        subject_days = defaultdict(set)
        lessons = []
        maximum_teacher_days = self._teacher_max_working_days()
        preferred_teacher_days = {
            teacher.id: self._teacher_preferred_days(
                teacher.id, class_by_id, assignments,
            )
            for teacher in teachers
        }
        teacher_daily_maximum = self._teacher_daily_max()
        balanced_teacher_day = self._teacher_balanced_day()

        items = []
        for assignment in assignments:
            school_class = class_by_id[assignment.class_id]
            for duration in self._split_subject(school_class.grade, assignment.subject, assignment.weekly_minutes):
                items.append((school_class, assignment, duration))
        # Reserve core and long sessions first across the whole school. Small
        # cross-class activities are added afterwards so they cannot block a
        # teacher's main class timetable.
        items.sort(
            key=lambda item: (
                -item[2],
                0 if self._is_core_subject(item[0].grade, item[1].subject) else 1,
                -assigned_loads[item[1].teacher_id],
                (item[0].grade + variant) % 6,
                item[0].name if variant % 2 == 0 else "".join(reversed(item[0].name)),
                item[1].subject,
            )
        )

        for cls, assignment, duration in items:
            grade = cls.grade
            active_days = self.rules.active_days(grade)
            daily_used = class_daily_used[cls.id]
            maximum_daily_minutes = self.rules.max_daily(grade)
            maximum_days_at_limit = self.rules.grade(grade).get("max_days_at_daily_limit")
            key = (cls.id, assignment.subject)
            placed = False
            rest_constraint_blocked = False
            rule = self.rules.subject_rule(grade, assignment.subject)
            day_order = sorted(
                range(active_days),
                key=lambda day: (
                    0 if day in teacher_days[assignment.teacher_id] and teacher_daily_used[(assignment.teacher_id, day)] < balanced_teacher_day
                    else 1 if day not in teacher_days[assignment.teacher_id] and len(teacher_days[assignment.teacher_id]) < preferred_teacher_days[assignment.teacher_id]
                    else 2 if day in teacher_days[assignment.teacher_id]
                    else 3,
                    day in self.preferred_rest_days.get(int(assignment.teacher_id), set()),
                    teacher_daily_used[(assignment.teacher_id, day)], daily_used[day],
                    (day - variant) % active_days,
                ),
            )
            minimum_days = int(rule.get("min_days", 0) or 0)
            if len(subject_days[key]) < minimum_days:
                day_order = [day for day in day_order if day not in subject_days[key]]
            for day in day_order:
                if not self._day_allowed(day, subject_days[key], rule):
                    continue
                if day not in teacher_days[assignment.teacher_id] and len(teacher_days[assignment.teacher_id]) >= maximum_teacher_days:
                    rest_constraint_blocked = True
                    continue
                if teacher_daily_used[(assignment.teacher_id, day)] + duration > teacher_daily_maximum:
                    continue
                for start in self._candidate_starts(cls, day, duration, variant):
                    next_daily_total = daily_used[day] + duration
                    if next_daily_total > maximum_daily_minutes:
                        continue
                    if (maximum_days_at_limit is not None and next_daily_total == maximum_daily_minutes
                            and daily_used[day] < maximum_daily_minutes
                            and sum(value >= maximum_daily_minutes for value in daily_used) >= maximum_days_at_limit):
                        continue
                    if self._conflict(class_busy[cls.id], teacher_busy[assignment.teacher_id], day, start, duration):
                        continue
                    transition = max(0, int(self._policy("teacher_transition_minutes", 0)))
                    if transition and any(
                        existing.day == day
                        and class_by_id[existing.class_id].shift != cls.shift
                        and not (
                            existing.start_minute + existing.duration + transition <= start
                            or start + duration + transition <= existing.start_minute
                        )
                        for existing in teacher_placed_lessons[assignment.teacher_id]
                    ):
                        continue
                    units = range(start // 10, (start + duration) // 10)
                    if any(
                        occupied_rooms[(day, unit)] >= self._room_capacity(day, unit * 10)
                        for unit in units
                    ):
                        continue
                    if self._avoid_window(rule, start, duration):
                        continue
                    self._reserve(class_busy[cls.id], teacher_busy[assignment.teacher_id], day, start, duration)
                    for unit in range(start // 10, (start + duration) // 10):
                        occupied_rooms[(day, unit)] += 1
                    lesson = Lesson(cls.id, assignment.teacher_id, assignment.subject, day, start, duration)
                    lessons.append(lesson)
                    teacher_placed_lessons[assignment.teacher_id].append(lesson)
                    daily_used[day] += duration
                    subject_days[key].add(day)
                    teacher_days[assignment.teacher_id].add(day)
                    teacher_daily_used[(assignment.teacher_id, day)] += duration
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                rest_detail = " مع ضمان يومي راحة أسبوعياً لكل مدرس" if rest_constraint_blocked else ""
                raise _PlacementError(
                    f"تعذر تركيب حصة «{assignment.subject}» ({duration} دق) للقسم «{cls.name}» دون تعارض"
                    f"{rest_detail}. راجع عدد المدرسين/أحجامهم أو القيود.",
                    assignment,
                )

        for cls in classes:
            self._validate_distribution(cls, lessons)
        return lessons

    def _split_subject(self, grade:int, subject:str, total:int) -> list[int]:
        rule=self.rules.subject_rule(grade,subject)
        if rule.get('sessions') and rule.get('block_minutes'):
            return [rule['block_minutes']]*rule['sessions']
        if subject in {"التاريخ","الجغرافيا","التربية المدنية"}:
            return [40]
        if subject in {"التربية الموسيقية","التربية التشكيلية"} and total==30:
            return [30]
        if subject=="الفرنسية" and grade==2:
            return [120]
        if subject=="الفرنسية" and total==480:
            return [120,120,120,120]
        if subject=="العربية":
            # 9h => 2h+2h+2h+2h+1h ; 6h => 2h+2h+1h+1h
            return [120,120,120,120,60] if total==540 else [120,120,60,60]
        if subject=="الرياضيات":
            return [60]*(total//60)
        if total % 60 == 0:
            return [60]*(total//60)
        # Generic 30/40/60 handling.
        parts=[]
        left=total
        for unit in (60,40,30,10):
            while left>=unit:
                parts.append(unit); left-=unit
        return parts

    def _candidate_starts(self, school_class: SchoolClass, day:int, duration:int, variant=0):
        # Morning classes are packed from 08:00 forward. Afternoon classes are
        # packed toward 17:00, so a four-hour day naturally becomes 13:00-17:00.
        a, b = self._class_window(school_class, day)
        starts = []
        s = a
        while s + duration <= b:
            starts.append(s)
            s += 10
        if starts:
            shift = variant % len(starts)
            starts = starts[shift:] + starts[:shift]
            if school_class.shift == "afternoon" and day != 5:
                starts.reverse()
        yield from starts

    def _class_window(self, school_class: SchoolClass, day: int):
        # During the week a class keeps the director-selected period.  Saturday
        # is flexible: the objective packs it into the morning, while the wider
        # window keeps a valid fallback when fixed assignments and six rooms make
        # a completely free afternoon impossible.
        if day == 5:
            return (
                self._policy_minute("school_start", "08:00"),
                self._policy_minute("school_end", "17:00"),
            )
        if school_class.shift == "morning":
            return (
                self._policy_minute("morning_start", "08:00"),
                self._policy_minute("morning_end", "13:00"),
            )
        if school_class.shift == "afternoon":
            return (
                self._policy_minute("afternoon_start", "12:00"),
                self._policy_minute("afternoon_end", "17:00"),
            )
        return school_class.shift_window

    def _day_allowed(self, day:int, used_days:set[int], rule:dict):
        if rule.get('non_consecutive_days') and used_days:
            if any(abs(day-d)==1 for d in used_days):
                return False
        return True

    def _avoid_window(self, rule:dict, start:int, duration:int):
        win=rule.get('avoid_window')
        if not win: return False
        def m(s):
            h,mi=map(int,s.split(':')); return h*60+mi
        a,b=map(m,win)
        return start < b and start+duration > a

    def _conflict(self, class_set, teacher_set, day, start, duration):
        units=range(start//10,(start+duration)//10)
        return any((day,u) in class_set or (day,u) in teacher_set for u in units)

    def _reserve(self, class_set, teacher_set, day, start, duration):
        for u in range(start//10,(start+duration)//10):
            class_set.add((day,u)); teacher_set.add((day,u))

    def _validate_distribution(self, cls, all_lessons):
        lessons=[l for l in all_lessons if l.class_id==cls.id]
        by_subject=defaultdict(set)
        for l in lessons: by_subject[l.subject].add(l.day)
        for subject,rule in self.rules.grade(cls.grade).get('subject_day_rules',{}).items():
            md=rule.get('min_days')
            if md and len(by_subject.get(subject,set())) < md:
                self.warnings.append(f"تنبيه: {cls.name} - مادة {subject} موزعة على {len(by_subject.get(subject,set()))} أيام بدل {md} أيام على الأقل.")
        daily = defaultdict(int)
        for lesson in lessons:
            daily[lesson.day] += lesson.duration
        maximum = self.rules.max_daily(cls.grade)
        allowed_max_days = self.rules.grade(cls.grade).get("max_days_at_daily_limit")
        if allowed_max_days is not None and sum(value >= maximum for value in daily.values()) > allowed_max_days:
            self.warnings.append(
                f"تنبيه: {cls.name} بلغ الحد اليومي الأقصى في أكثر من {allowed_max_days} يومين."
            )

    def _audit_result(self, classes, teachers, assignments, lessons, complementary_minutes=None):
        """Post-generation audit with actionable correction suggestions."""
        complementary_minutes = complementary_minutes or {}
        class_by_id = {item.id: item for item in classes}
        teacher_by_id = {item.id: item for item in teachers}
        assigned_by_teacher = defaultdict(list)
        lessons_by_teacher = defaultdict(list)
        lessons_by_class = defaultdict(list)
        assignment_loads = defaultdict(int)
        assignment_keys = defaultdict(list)
        for assignment in assignments:
            assignment_keys[(assignment.class_id, assignment.subject)].append(assignment)
            assigned_by_teacher[assignment.teacher_id].append(assignment)
            assignment_loads[assignment.teacher_id] += assignment.weekly_minutes
            teacher = teacher_by_id.get(assignment.teacher_id)
            school_class = class_by_id.get(assignment.class_id)
            if not teacher or not school_class:
                self._warn_once("خطأ: يوجد إسناد مرتبط بمدرس أو قسم محذوف. الاقتراح: أعد التوليد.")
                continue
            expected = self.rules.subjects(school_class.grade).get(assignment.subject)
            if expected is None:
                self._warn_once(
                    f"خطأ: مادة {assignment.subject} غير مطلوبة في {school_class.name}. الاقتراح: احذف الإسناد بإعادة التوليد."
                )
            elif assignment.weekly_minutes != expected:
                self._warn_once(
                    f"خطأ: حجم {assignment.subject} في {school_class.name} لا يطابق الدليل. الاقتراح: أعد التوليد."
                )
            if teacher and not self._teacher_can_teach(teacher, assignment.class_id, assignment.subject):
                self._warn_once(
                    f"خطأ: {teacher.name} غير مؤهل لمادة {assignment.subject}. الاقتراح: عدّل الإسناد يدوياً واختر مدرساً تظهر حالته «مؤهل»."
                )
            elif (teacher and assignment.subject == "التربية البدنية"
                  and self.rules.assignment_rule("physical_education_specialist_required", True)
                  and not self._has_subject_expertise(teacher, assignment.subject)):
                self._warn_once(
                    f"خطأ: {teacher.name} يدرّس التربية البدنية دون اختصاص مطابق. الاقتراح: اختر مدرس تربية بدنية مختصاً."
                )
            elif teacher and assignment.subject in SPECIALISTS and not self._has_subject_expertise(teacher, assignment.subject):
                self._warn_once(
                    f"تنبيه: {teacher.name} يدرّس {assignment.subject} دون اختصاص أو تكوين مطابق. الاقتراح: اختر مختصاً من تعديل الإسناد اليدوي."
                )
        for lesson in lessons:
            lessons_by_teacher[lesson.teacher_id].append(lesson)
            lessons_by_class[lesson.class_id].append(lesson)

        for school_class in classes:
            class_lessons = lessons_by_class[school_class.id]
            if not school_class.shift_window:
                self._warn_once(
                    f"خطأ: الفترة الدراسية للقسم {school_class.name} غير محددة. "
                    "الاقتراح: افتح صفحة الأقسام واختر صباحية أو مسائية."
                )
            if not class_lessons:
                self._warn_once(f"خطأ: القسم {school_class.name} دون جدول. الاقتراح: راجع الإسناد ثم أعد التوليد.")
                continue
            if school_class.shift_window:
                outside = []
                for lesson in class_lessons:
                    shift_start, shift_end = self._class_window(school_class, lesson.day)
                    if lesson.start_minute < shift_start or lesson.start_minute + lesson.duration > shift_end:
                        outside.append(lesson)
                if outside:
                    self._warn_once(
                        f"خطأ: توجد حصة للقسم {school_class.name} خارج فترته «{school_class.shift_label}». "
                        "الاقتراح: أعد توليد الجدول بعد تثبيت فترة القسم."
                    )
            for subject, minutes in self.rules.subjects(school_class.grade).items():
                key_assignments = assignment_keys.get((school_class.id, subject), [])
                if not key_assignments:
                    self._warn_once(
                        f"خطأ: لا يوجد إسناد لمادة {subject} في {school_class.name}. الاقتراح: أعد التوليد."
                    )
                elif len(key_assignments) > 1:
                    self._warn_once(
                        f"خطأ: إسناد {subject} في {school_class.name} مكرر. الاقتراح: أعد التوليد."
                    )
                scheduled = sum(item.duration for item in class_lessons if item.subject == subject)
                if scheduled != minutes:
                    self._warn_once(
                        f"خطأ: {school_class.name} / {subject}: المبرمج {scheduled} دق بدل {minutes} دق. الاقتراح: أعد التوليد أو عدّل الإسناد."
                    )
            daily = defaultdict(int)
            for lesson in class_lessons:
                daily[lesson.day] += lesson.duration
            for day, total in daily.items():
                if total > self.rules.max_daily(school_class.grade):
                    self._warn_once(
                        f"خطأ: {school_class.name} يتجاوز الحد اليومي في اليوم {day + 1}. الاقتراح: أعد توزيع الحصص."
                    )
            if self._has_overlap(class_lessons):
                self._warn_once(f"خطأ: يوجد تداخل حصص في {school_class.name}. الاقتراح: أعد التوليد فوراً.")
            for subject, rule in self.rules.grade(school_class.grade).get("subject_day_rules", {}).items():
                minimum_days = int(rule.get("min_days", 0) or 0)
                actual_days = {item.day for item in class_lessons if item.subject == subject}
                if minimum_days and len(actual_days) < minimum_days:
                    self._warn_once(
                        f"تنبيه: {school_class.name} - مادة {subject} موزعة على {len(actual_days)} أيام بدل {minimum_days} أيام على الأقل."
                    )

        occupied_rooms = defaultdict(int)
        for lesson in lessons:
            for unit in range(lesson.start_minute // 10, (lesson.start_minute + lesson.duration) // 10):
                occupied_rooms[(lesson.day, unit)] += 1
        invalid_room_slots = [
            (day, unit, count)
            for (day, unit), count in occupied_rooms.items()
            if count > self._room_capacity(day, unit * 10)
        ]
        if invalid_room_slots:
            regular = self._regular_room_capacity()
            emergency = max(
                self._room_capacity(5, self._policy_minute("school_start", "08:00")) - regular,
                0,
            )
            self._warn_once(
                "خطأ: عدد الأقسام المتزامنة يتجاوز القاعات المتاحة "
                f"({regular} عادية و{emergency} احتياطية حسب التوقيت). الاقتراح: أعد التوليد."
            )

        saturday_end = self._policy_minute(
            "preferred_saturday_end",
            str(self.rules.assignment_rule("preferred_saturday_end", "13:00")),
        )
        late_saturday = [
            lesson for lesson in lessons
            if lesson.day == 5 and lesson.start_minute + lesson.duration > saturday_end
        ]
        if late_saturday and bool(self._policy("saturday_afternoon_free", True)):
            self._warn_once(
                f"تنبيه: توجد {len(late_saturday)} حصة بعد نهاية السبت المطلوبة "
                f"({saturday_end // 60:02d}:{saturday_end % 60:02d}). الاقتراح: راجع القيود أو أعد التوليد."
            )

        maximum_days = self._teacher_max_working_days()
        required_total = sum(
            minutes for school_class in classes
            for minutes in self.rules.subjects(school_class.grade).values()
        )
        total_demand = sum(assignment.weekly_minutes for assignment in assignments)
        if total_demand != required_total:
            self._warn_once(
                f"خطأ: مجموع الساعات المسندة ({self._format_minutes(total_demand)}) لا يطابق مجموع التنظيم البيداغوجي "
                f"({self._format_minutes(required_total)}). الاقتراح: أعد التوليد لإكمال الساعات الناقصة."
            )
        total_capacity = sum(teacher.max_weekly_minutes for teacher in teachers)
        effective_total = total_demand + sum(complementary_minutes.values())
        if total_capacity > effective_total:
            gap = total_capacity - effective_total
            self._warn_once(
                f"تنبيه: طاقة المدرسين ({self._format_minutes(total_capacity)}) أكبر من حجم الأقسام الحالي "
                f"مع الساعات التكميلية ({self._format_minutes(effective_total)}) بفارق {self._format_minutes(gap)}. "
                "لذلك لا يمكن بلوغ الحجم المستهدف للجميع. "
                "الاقتراح: أضف الساعات التكميلية الحقيقية الناقصة أو راجع الأحجام المستهدفة."
            )
        for teacher in teachers:
            teacher_assignments = assigned_by_teacher[teacher.id]
            teacher_lessons = lessons_by_teacher[teacher.id]
            if not teacher_assignments:
                options = [item for item in assignments if self._teacher_can_teach(teacher, item.class_id, item.subject) and item.weekly_minutes <= teacher.max_weekly_minutes]
                options.sort(key=lambda item: (-assignment_loads[item.teacher_id], item.weekly_minutes, item.subject))
                if options:
                    option = options[0]
                    school_class = class_by_id[option.class_id]
                    current = teacher_by_id[option.teacher_id]
                    suggestion = f"يمكن تجربة تحويل «{option.subject} - {school_class.name}» من {current.name} إليه/إليها عبر تعديل الإسناد اليدوي."
                else:
                    suggestion = "لا توجد مادة مطابقة لاختصاصه حالياً؛ راجع مواد التأهيل أو عدد المدرسين."
                self._warn_once(f"تنبيه: المدرس(ة) {teacher.name} دون أي إسناد أو جدول. الاقتراح: {suggestion}")
                continue
            scheduled = sum(item.duration for item in teacher_lessons)
            assigned = assignment_loads[teacher.id]
            complementary = int(complementary_minutes.get(teacher.id, 0) or 0)
            effective_load = assigned + complementary
            if effective_load > teacher.max_weekly_minutes:
                self._warn_once(
                    f"خطأ: إسناد {teacher.name} مع الساعات التكميلية يتجاوز حجمه الأسبوعي الأقصى. "
                    "الاقتراح: راجع الساعات التكميلية أو انقل مادة إلى مدرس مؤهل أقل حملاً."
                )
            elif effective_load < teacher.max_weekly_minutes:
                shortage = teacher.max_weekly_minutes - effective_load
                compatible_demand = sum(
                    item.weekly_minutes for item in assignments if self._teacher_can_teach(teacher, item.class_id, item.subject)
                )
                if compatible_demand < teacher.max_weekly_minutes:
                    reason = "حجم المواد المطابقة لاختصاصه في الأقسام الحالية غير كافٍ"
                else:
                    reason = "الحصص المطابقة موزعة حالياً على مدرسين آخرين"
                self._warn_once(
                    f"تنبيه: {teacher.name} مسند له {self._format_minutes(effective_load)} من أصل "
                    f"{self._format_minutes(teacher.max_weekly_minutes)} (نقص {self._format_minutes(shortage)})؛ {reason}. "
                    "الاقتراح: راجع الإسناد أو أضف ساعات تكميلية حقيقية دون إنشاء حصص وهمية."
                )
            if scheduled != assigned:
                self._warn_once(
                    f"خطأ: حجم {teacher.name} المبرمج ({scheduled} دق) لا يطابق الإسناد ({assigned} دق). الاقتراح: أعد التوليد."
                )
            days = {item.day for item in teacher_lessons}
            preferred_rest = self.preferred_rest_days.get(int(teacher.id), set())
            used_preferred_rest = sorted(days & preferred_rest)
            if used_preferred_rest:
                labels = "، ".join(DAYS_AR[day] for day in used_preferred_rest)
                self._warn_once(
                    f"تنبيه: تعذر احترام كل أيام الراحة المفضلة لـ {teacher.name} ({labels}) بسبب بقية القيود."
                )
            preferred_days = self._teacher_preferred_days(
                teacher.id, class_by_id, teacher_assignments,
            )
            if len(days) > maximum_days:
                self._warn_once(
                    f"خطأ: {teacher.name} يعمل {len(days)} أيام. الاقتراح: عدّل الإسناد لتوفير يومي الراحة."
                )
            elif len(days) > preferred_days:
                self._warn_once(
                    f"تنبيه: {teacher.name} يعمل {len(days)} أيام بدل الهدف {preferred_days}. الاقتراح: جرّب نقل مادة مؤهل لها إلى مدرس أقل حملاً ثم أعد تركيب الجدول."
                )
            daily = defaultdict(int)
            for lesson in teacher_lessons:
                daily[lesson.day] += lesson.duration
            if any(total > self._teacher_daily_max() for total in daily.values()):
                self._warn_once(f"خطأ: {teacher.name} تجاوز الحد اليومي. الاقتراح: أعد توزيع الإسناد أو الحصص.")
            if self._has_overlap(teacher_lessons):
                self._warn_once(f"خطأ: يوجد تداخل في جدول {teacher.name}. الاقتراح: أعد التوليد فوراً.")
            transition = max(0, int(self._policy("teacher_transition_minutes", 0)))
            if transition:
                ordered = sorted(teacher_lessons, key=lambda item: (item.day, item.start_minute))
                for previous, current in zip(ordered, ordered[1:]):
                    if previous.day != current.day:
                        continue
                    previous_class = class_by_id.get(previous.class_id)
                    current_class = class_by_id.get(current.class_id)
                    if (previous_class and current_class
                            and previous_class.shift != current_class.shift
                            and current.start_minute - (previous.start_minute + previous.duration) < transition):
                        self._warn_once(
                            f"خطأ: مدة الانتقال بين الفترة الصباحية والمسائية غير محترمة في جدول {teacher.name}."
                        )
                        break

    def _warn_once(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    @staticmethod
    def _has_overlap(lessons):
        ordered = sorted(lessons, key=lambda item: (item.day, item.start_minute))
        return any(
            first.day == second.day and first.start_minute + first.duration > second.start_minute
            for first, second in zip(ordered, ordered[1:])
        )
