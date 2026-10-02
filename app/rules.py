import json
from pathlib import Path

class RuleSet:
    def __init__(self, json_path: str | Path):
        self.path = Path(json_path)
        self.data = json.loads(self.path.read_text(encoding='utf-8'))

    @property
    def academic_year(self):
        return self.data['academic_year']

    def grade(self, grade: int):
        return self.data['grades'][str(grade)]

    def subjects(self, grade: int):
        return self.grade(grade)['subjects']

    def active_days(self, grade: int):
        return self.grade(grade)['active_days']

    def max_daily(self, grade: int):
        return self.grade(grade)['max_daily_minutes']

    def subject_rule(self, grade: int, subject: str):
        return self.grade(grade).get('subject_day_rules', {}).get(subject, {})

    def all_subjects(self):
        ordered = []
        for grade in range(1, 7):
            for subject in self.subjects(grade):
                if subject not in ordered:
                    ordered.append(subject)
        return ordered

    def teacher_profiles(self):
        return self.data.get('teacher_profiles', {})

    def specialties(self):
        return list(self.teacher_profiles())

    def training_profiles(self):
        return self.data.get('training_profiles', {})

    def trainings(self):
        return list(self.training_profiles())

    def recommended_subjects(self, specialty: str, training: str = ""):
        recommended = []
        for source, key in ((self.teacher_profiles(), specialty), (self.training_profiles(), training)):
            for subject in source.get(key, {}).get('subjects', []):
                if subject not in recommended:
                    recommended.append(subject)
        return recommended

    def assignment_rule(self, key: str, default=None):
        return self.data.get('assignment_rules', {}).get(key, default)

    @staticmethod
    def time_to_minute(value: str):
        hour, minute = map(int, value.split(':'))
        return hour * 60 + minute

    def breaks(self):
        return [
            tuple(map(self.time_to_minute, self.data[name]))
            for name in ('morning_break', 'afternoon_break')
            if name in self.data
        ]

    def teacher_rest_days(self):
        return int(self.data.get('teacher_rest_days_per_week', 2))

    def teacher_max_working_days(self):
        calendar_days = int(self.data.get('calendar_days_per_week', 7))
        return max(1, calendar_days - self.teacher_rest_days())

    def teacher_preferred_working_days(self):
        preferred = int(self.data.get('teacher_preferred_working_days', 4))
        return min(preferred, self.teacher_max_working_days())

    def teacher_daily_max(self):
        return int(self.data.get('teacher_daily_max_minutes', 300))

    def teacher_balanced_day(self):
        return min(int(self.data.get('teacher_balanced_day_minutes', 240)), self.teacher_daily_max())
