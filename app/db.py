import json
import sqlite3
from pathlib import Path
from .models import SchoolClass, Teacher, Assignment, ComplementaryWorkload, Lesson, School, Room

class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        # SQLite does not enforce declared foreign keys unless explicitly enabled.
        # This keeps generated lessons and assignments consistent after deletions.
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS classes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            grade INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 6),
            shift TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS teachers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            specialty TEXT NOT NULL DEFAULT '',
            max_weekly_minutes INTEGER NOT NULL DEFAULT 1080,
            subjects_json TEXT NOT NULL DEFAULT '[]',
            training TEXT NOT NULL DEFAULT '',
            experience_years INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS assignments(
            class_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            weekly_minutes INTEGER NOT NULL,
            PRIMARY KEY(class_id, subject),
            FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS fixed_assignments(
            class_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            weekly_minutes INTEGER NOT NULL,
            PRIMARY KEY(class_id, subject),
            FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS complementary_workloads(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            weekly_minutes INTEGER NOT NULL CHECK(weekly_minutes > 0),
            note TEXT NOT NULL DEFAULT 'ساعات تكميلية',
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS teacher_unavailability(
            teacher_id INTEGER NOT NULL,
            day INTEGER NOT NULL CHECK(day BETWEEN 0 AND 5),
            PRIMARY KEY(teacher_id, day),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS teacher_class_permissions(
            teacher_id INTEGER NOT NULL,
            class_id INTEGER NOT NULL,
            PRIMARY KEY(teacher_id,class_id),
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
            FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS rooms(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL DEFAULT 'regular',
            enabled INTEGER NOT NULL DEFAULT 1,
            availability_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS lessons(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            subject TEXT NOT NULL,
            day INTEGER NOT NULL,
            start_minute INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
            FOREIGN KEY(teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        );
        ''')
        teacher_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(teachers)")}
        if "training" not in teacher_columns:
            self.conn.execute("ALTER TABLE teachers ADD COLUMN training TEXT NOT NULL DEFAULT ''")
        if "experience_years" not in teacher_columns:
            self.conn.execute("ALTER TABLE teachers ADD COLUMN experience_years INTEGER NOT NULL DEFAULT 0")
        class_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(classes)")}
        if "shift" not in class_columns:
            # Do not guess the period of existing classes.  The director chooses
            # it explicitly from the class card after the upgrade.
            self.conn.execute("ALTER TABLE classes ADD COLUMN shift TEXT NOT NULL DEFAULT ''")
        self.conn.commit()
        if not self.conn.execute("SELECT 1 FROM rooms LIMIT 1").fetchone():
            default_availability = json.dumps(
                {str(day): [[480, 1020]] for day in range(6)}, ensure_ascii=False
            )
            for index in range(1, 7):
                self.conn.execute(
                    "INSERT INTO rooms(name,kind,enabled,availability_json) VALUES(?,?,1,?)",
                    (f"قاعة {index}", "regular", default_availability),
                )
            preparatory = {str(day): [[720, 1020]] for day in range(5)}
            preparatory["5"] = [[480, 1020]]
            self.conn.execute(
                "INSERT INTO rooms(name,kind,enabled,availability_json) VALUES(?,?,1,?)",
                ("قاعة التحضيري", "emergency", json.dumps(preparatory, ensure_ascii=False)),
            )
            self.conn.commit()
        if (self.conn.execute("SELECT 1 FROM teachers LIMIT 1").fetchone()
                and self.conn.execute("SELECT 1 FROM classes LIMIT 1").fetchone()
                and not self.conn.execute("SELECT 1 FROM teacher_class_permissions LIMIT 1").fetchone()):
            self.conn.execute(
                "INSERT OR IGNORE INTO teacher_class_permissions(teacher_id,class_id) SELECT teachers.id,classes.id FROM teachers CROSS JOIN classes"
            )
            self.conn.commit()

    def close(self):
        self.conn.close()

    def clear_all(self):
        """Clear the working school data while keeping the database structure."""
        self.conn.execute("DELETE FROM lessons")
        self.conn.execute("DELETE FROM assignments")
        self.conn.execute("DELETE FROM fixed_assignments")
        self.conn.execute("DELETE FROM complementary_workloads")
        self.conn.execute("DELETE FROM teacher_unavailability")
        self.conn.execute("DELETE FROM classes")
        self.conn.execute("DELETE FROM teachers")
        self.conn.execute("DELETE FROM settings")
        self.conn.commit()

    def set_school(self, school: School):
        for k, v in school.__dict__.items():
            self.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (f"school.{k}", str(v)))
        self.conn.commit()

    def get_school(self) -> School:
        vals = {}
        for row in self.conn.execute("SELECT key,value FROM settings WHERE key LIKE 'school.%'"):
            vals[row['key'].split('.',1)[1]] = row['value']
        return School(**{k: vals.get(k, getattr(School(), k)) for k in School().__dict__.keys()})

    def set_json_setting(self, key: str, value):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def get_json_setting(self, key: str, default=None):
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return default

    def save_schedule_policy(self, policy: dict):
        self.set_json_setting("schedule.policy", policy)

    def schedule_policy(self) -> dict:
        value = self.get_json_setting("schedule.policy", {})
        return value if isinstance(value, dict) else {}

    def set_teacher_unavailable_days(self, teacher_id: int, days):
        normalized = sorted({int(day) for day in days if 0 <= int(day) <= 5})
        with self.conn:
            self.conn.execute("DELETE FROM teacher_unavailability WHERE teacher_id=?", (teacher_id,))
            self.conn.executemany(
                "INSERT INTO teacher_unavailability(teacher_id,day) VALUES(?,?)",
                [(teacher_id, day) for day in normalized],
            )

    def teacher_unavailable_days(self) -> dict[int, set[int]]:
        result = {}
        for row in self.conn.execute(
            "SELECT teacher_id,day FROM teacher_unavailability ORDER BY teacher_id,day"
        ):
            result.setdefault(row["teacher_id"], set()).add(row["day"])
        return result

    # Stored in the original compatibility table, but treated by the solver as
    # soft preferred rest days rather than hard unavailability.
    def set_teacher_preferred_rest_days(self, teacher_id: int, days):
        self.set_teacher_unavailable_days(teacher_id, days)

    def teacher_preferred_rest_days(self) -> dict[int, set[int]]:
        return self.teacher_unavailable_days()

    def add_class(self, name: str, grade: int, shift: str = "morning"):
        if shift not in {"morning", "afternoon"}:
            raise ValueError("Invalid class shift")
        self.conn.execute("INSERT INTO classes(name,grade,shift) VALUES(?,?,?)", (name, grade, shift))
        self.conn.commit()

    def update_class_shift(self, class_id: int, shift: str):
        if shift not in {"morning", "afternoon"}:
            raise ValueError("Invalid class shift")
        self.conn.execute("UPDATE classes SET shift=? WHERE id=?", (shift, class_id))
        self.conn.commit()

    def delete_class(self, class_id: int):
        self.conn.execute("DELETE FROM classes WHERE id=?", (class_id,))
        self.conn.commit()

    def classes(self):
        return [
            SchoolClass(r['id'], r['name'], r['grade'], r['shift'] or "unassigned")
            for r in self.conn.execute("SELECT * FROM classes ORDER BY grade,name")
        ]

    def add_teacher(self, name: str, specialty: str, max_weekly_minutes: int, subjects: list[str], training: str = "", experience_years: int = 0):
        cursor = self.conn.execute(
            "INSERT INTO teachers(name,specialty,max_weekly_minutes,subjects_json,training,experience_years) VALUES(?,?,?,?,?,?)",
            (name, specialty, max_weekly_minutes, json.dumps(subjects, ensure_ascii=False), training, experience_years),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_teacher(self, teacher_id: int, name: str, specialty: str, max_weekly_minutes: int, subjects: list[str], training: str = "", experience_years: int = 0):
        self.conn.execute(
            "UPDATE teachers SET name=?,specialty=?,max_weekly_minutes=?,subjects_json=?,training=?,experience_years=? WHERE id=?",
            (name, specialty, max_weekly_minutes, json.dumps(subjects, ensure_ascii=False), training, experience_years, teacher_id),
        )
        self.conn.commit()

    def add_teachers(self, rows):
        self.conn.executemany(
            "INSERT INTO teachers(name,specialty,max_weekly_minutes,subjects_json,training,experience_years) VALUES(?,?,?,?,?,?)",
            [(name, specialty, minutes, json.dumps(subjects, ensure_ascii=False), training, experience)
             for name, specialty, minutes, subjects, training, experience in rows],
        )
        self.conn.commit()

    def delete_teacher(self, teacher_id: int):
        self.conn.execute("DELETE FROM teachers WHERE id=?", (teacher_id,))
        self.conn.commit()

    def teachers(self):
        permissions = self.teacher_class_ids()
        out=[]
        for r in self.conn.execute("SELECT * FROM teachers ORDER BY name"):
            out.append(Teacher(r['id'], r['name'], r['specialty'], r['max_weekly_minutes'], json.loads(r['subjects_json']),
                               r['training'], r['experience_years'], sorted(permissions.get(r['id'], set()))))
        return out

    def set_teacher_classes(self, teacher_id: int, class_ids):
        normalized = sorted({int(class_id) for class_id in class_ids})
        with self.conn:
            self.conn.execute("DELETE FROM teacher_class_permissions WHERE teacher_id=?", (teacher_id,))
            self.conn.executemany(
                "INSERT INTO teacher_class_permissions(teacher_id,class_id) VALUES(?,?)",
                [(teacher_id, class_id) for class_id in normalized],
            )

    def teacher_class_ids(self):
        result = {}
        for row in self.conn.execute("SELECT teacher_id,class_id FROM teacher_class_permissions ORDER BY teacher_id,class_id"):
            result.setdefault(row['teacher_id'], set()).add(row['class_id'])
        return result

    def rooms(self):
        result = []
        for row in self.conn.execute("SELECT * FROM rooms ORDER BY kind,name"):
            raw = json.loads(row["availability_json"] or "{}")
            availability = {
                str(day): [tuple(map(int, interval)) for interval in intervals]
                for day, intervals in raw.items()
            }
            result.append(Room(row["id"], row["name"], row["kind"], bool(row["enabled"]), availability))
        return result

    def add_room(self, name: str, kind: str = "regular", availability=None):
        availability = availability or {str(day): [[480, 1020]] for day in range(6)}
        cursor = self.conn.execute(
            "INSERT INTO rooms(name,kind,enabled,availability_json) VALUES(?,?,1,?)",
            (name, kind, json.dumps(availability, ensure_ascii=False)),
        )
        self.conn.commit()
        return cursor.lastrowid

    def update_room(self, room_id: int, name: str, kind: str, enabled: bool, availability):
        self.conn.execute(
            "UPDATE rooms SET name=?,kind=?,enabled=?,availability_json=? WHERE id=?",
            (name, kind, int(bool(enabled)), json.dumps(availability, ensure_ascii=False), room_id),
        )
        self.conn.commit()

    def delete_room(self, room_id: int):
        self.conn.execute("DELETE FROM rooms WHERE id=?", (room_id,))
        self.conn.commit()

    def clear_generated(self):
        self.conn.execute("DELETE FROM assignments")
        self.conn.execute("DELETE FROM lessons")
        self.conn.commit()

    def save_assignments(self, assignments: list[Assignment]):
        self.conn.execute("DELETE FROM assignments")
        self.conn.executemany("INSERT INTO assignments(class_id,teacher_id,subject,weekly_minutes) VALUES(?,?,?,?)",
                              [(a.class_id,a.teacher_id,a.subject,a.weekly_minutes) for a in assignments])
        self.conn.commit()

    def assignments(self):
        return [Assignment(r['class_id'],r['teacher_id'],r['subject'],r['weekly_minutes']) for r in self.conn.execute("SELECT * FROM assignments ORDER BY class_id,subject")]

    def save_fixed_assignments(self, assignments: list[Assignment]):
        """Persist the director's real assignment independently of generated times."""
        with self.conn:
            self.conn.execute("DELETE FROM fixed_assignments")
            self.conn.executemany(
                "INSERT INTO fixed_assignments(class_id,teacher_id,subject,weekly_minutes) VALUES(?,?,?,?)",
                [(a.class_id, a.teacher_id, a.subject, a.weekly_minutes) for a in assignments],
            )

    def fixed_assignments(self):
        return [
            Assignment(r['class_id'], r['teacher_id'], r['subject'], r['weekly_minutes'])
            for r in self.conn.execute("SELECT * FROM fixed_assignments ORDER BY class_id,subject")
        ]

    def save_complementary_workloads(self, workloads: list[ComplementaryWorkload]):
        with self.conn:
            self.conn.execute("DELETE FROM complementary_workloads")
            self.conn.executemany(
                "INSERT INTO complementary_workloads(teacher_id,weekly_minutes,note) VALUES(?,?,?)",
                [(item.teacher_id, item.weekly_minutes, item.note) for item in workloads],
            )

    def complementary_workloads(self):
        return [
            ComplementaryWorkload(r['id'], r['teacher_id'], r['weekly_minutes'], r['note'])
            for r in self.conn.execute("SELECT * FROM complementary_workloads ORDER BY teacher_id,id")
        ]

    def complementary_minutes(self):
        return {
            row['teacher_id']: row['minutes']
            for row in self.conn.execute(
                "SELECT teacher_id,SUM(weekly_minutes) AS minutes FROM complementary_workloads GROUP BY teacher_id"
            )
        }

    def save_lessons(self, lessons: list[Lesson]):
        self.conn.execute("DELETE FROM lessons")
        self.conn.executemany("INSERT INTO lessons(class_id,teacher_id,subject,day,start_minute,duration) VALUES(?,?,?,?,?,?)",
                              [(l.class_id,l.teacher_id,l.subject,l.day,l.start_minute,l.duration) for l in lessons])
        self.conn.commit()

    def lessons(self):
        return [Lesson(r['class_id'],r['teacher_id'],r['subject'],r['day'],r['start_minute'],r['duration']) for r in self.conn.execute("SELECT * FROM lessons ORDER BY day,start_minute")]
