"""Self-contained Arabic PDF export without Windows GTK/Pango dependencies."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import DAYS_AR, minute_to_hhmm

_ARABIC = re.compile(r"[\u0600-\u06FF]")
_FONT_NAME = "TanzimNotoArabic"
_NAVY = colors.HexColor("#12304A")
_TEAL = colors.HexColor("#0D8A82")
_ORANGE = colors.HexColor("#F59E0B")
_REST = colors.HexColor("#D1E7DD")
_PALE = colors.HexColor("#F3F6FA")
_LINE = colors.HexColor("#CBD7E1")
_TEXT = colors.HexColor("#17324A")


def _rtl(value: object) -> str:
    text = str(value or "")
    if not _ARABIC.search(text):
        return text
    return get_display(arabic_reshaper.reshape(text), base_dir="R")


class PDFExporter:
    def __init__(self, template_dir: str | Path):
        root = Path(template_dir).resolve().parent
        self.font_path = root / "assets" / "fonts" / "NotoNaskhArabic-Regular.ttf"

    def export(self, out_path, school, classes, teachers, assignments, lessons, rules, warnings):
        if not self.font_path.exists():
            raise FileNotFoundError(f"Arabic PDF font is missing: {self.font_path}")
        if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(self.font_path)))

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        document = SimpleDocTemplate(
            str(out_path), pagesize=A4, rightMargin=12*mm, leftMargin=12*mm,
            topMargin=14*mm, bottomMargin=15*mm, title="التنظيم البيداغوجي",
            author=school.name or "المؤسسة التربوية",
            subject=f"التنظيم البيداغوجي {school.academic_year}",
        )
        document.school_name = school.name or "المؤسسة التربوية"
        styles = self._styles()
        story = []
        class_by_id = {c.id: c for c in classes}
        teacher_by_id = {t.id: t for t in teachers}

        banner = Table([[self._heading("الجمهورية التونسية  •  وزارة التربية", styles["banner"]) ]], colWidths=[186*mm], rowHeights=[18*mm])
        banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), _NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [banner, Spacer(1, 9*mm), self._heading("التنظيم البيداغوجي", styles["title"]),
                  self._heading("السنة الدراسية", styles["subtitle"]),
                  self._heading(school.academic_year, styles["year"]), Spacer(1, 8*mm)]

        meta_rows = [
            [f"المؤسسة: {school.name or '—'}", f"المندوبية الجهوية: {school.delegation or '—'}"],
            [f"الدائرة: {school.district or '—'}", f"المدير(ة): {school.director or '—'}"],
        ]
        story += [self._info_table(meta_rows, styles), Spacer(1, 7*mm)]

        stats = [
            [str(len(classes)), str(len(teachers)), str(len(assignments)), str(len(lessons))],
            ["الأقسام", "المدرسون", "الإسنادات", "الحصص الأسبوعية"],
        ]
        story += [self._stats_table(stats, styles), Spacer(1, 8*mm)]

        validation_text = "جاهز للمراجعة: لم يسجل المحرك أي تنبيه." if not warnings else f"يتطلب المراجعة: {len(warnings)} تنبيه قبل المصادقة."
        validation = Table([[self._paragraph(validation_text, styles["validation"])]], colWidths=[186*mm])
        validation.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E7F5F2") if not warnings else colors.HexColor("#FFF4DE")),
            ("BOX", (0, 0), (-1, -1), .7, _TEAL if not warnings else colors.HexColor("#C7892C")),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        generated_at = datetime.now().strftime("%d/%m/%Y  %H:%M")
        date_line = Table([
            [self._paragraph(generated_at, styles["date"]), self._paragraph("تاريخ إعداد الوثيقة", styles["meta"])]
        ], colWidths=[45*mm, 141*mm])
        date_line.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [validation, Spacer(1, 12*mm), date_line]

        teacher_rows = [["المدرس(ة)", "الحجم المستهدف", "المواد المسموح بها"]]
        for teacher in teachers:
            teacher_rows.append([
                teacher.name, self._duration_label(teacher.max_weekly_minutes), "، ".join(teacher.subjects) or "—",
            ])
        story += [PageBreak(), self._heading("المدرسون والمواد المسموح بها", styles["section"]),
                  self._paragraph("المواد مثبتة يدوياً من المدير وهي المرجع المعتمد للإسناد.", styles["meta"]),
                  Spacer(1, 3*mm), self._table(teacher_rows, [45*mm, 35*mm, 104*mm], styles)]

        assignment_rows = [["القسم", "المادة", "المدرس(ة)", "الحجم الأسبوعي"]]
        for assignment in assignments:
            assignment_rows.append([class_by_id[assignment.class_id].name, assignment.subject,
                                    teacher_by_id[assignment.teacher_id].name, self._duration_label(assignment.weekly_minutes)])
        story += [Spacer(1, 7*mm), self._heading("إسناد المواد والأقسام", styles["section"]),
                  self._table(assignment_rows, [37*mm, 46*mm, 62*mm, 39*mm], styles)]
        if warnings:
            story += [Spacer(1, 3*mm), self._heading("ملاحظات التحقق", styles["section"])]
            story.extend(self._paragraph(warning, styles["warning"]) for warning in warnings)

        for school_class in classes:
            rows = [["اليوم", "من", "إلى", "المادة", "المدرس(ة)", "المدة"]]
            for lesson in sorted((x for x in lessons if x.class_id == school_class.id), key=lambda x: (x.day, x.start_minute)):
                rows.append([DAYS_AR[lesson.day], minute_to_hhmm(lesson.start_minute),
                             minute_to_hhmm(lesson.start_minute + lesson.duration), lesson.subject,
                             teacher_by_id[lesson.teacher_id].name, self._duration_label(lesson.duration)])
            story += [PageBreak(), self._heading(f"جدول أوقات القسم: {school_class.name}", styles["section"]),
                      self._heading(
                          f"{rules.grade(school_class.grade)['name']}  •  {school_class.shift_label}",
                          styles["subtitle"],
                      ), Spacer(1, 2*mm),
                      self._table(rows, [29*mm, 22*mm, 22*mm, 41*mm, 50*mm, 20*mm], styles)]

        for teacher in teachers:
            teacher_lessons = sorted((x for x in lessons if x.teacher_id == teacher.id), key=lambda x: (x.day, x.start_minute))
            # Unassigned teachers remain visible in the competency roster and audit warnings,
            # but do not receive a misleading empty timetable page.
            if not teacher_lessons:
                continue
            profile = f"المواد المسموح بها: {'، '.join(teacher.subjects) or '—'}"
            active_days = {lesson.day for lesson in teacher_lessons}
            rest_days = ["الأحد", *[DAYS_AR[day] for day in range(6) if day not in active_days]]
            daily_totals = []
            scheduled_total = sum(lesson.duration for lesson in teacher_lessons)
            for day in sorted(active_days):
                total = sum(lesson.duration for lesson in teacher_lessons if lesson.day == day)
                daily_totals.append(f"{DAYS_AR[day]} {self._duration_label(total)}")
            story += [PageBreak(), self._heading(f"جدول المدرس(ة): {teacher.name}", styles["section"]),
                      self._paragraph(profile, styles["meta"]),
                      self._paragraph(
                          f"الحجم المسند: {self._duration_label(scheduled_total)}  •  "
                          f"الحجم المستهدف: {self._duration_label(teacher.max_weekly_minutes)}",
                          styles["meta"],
                      ),
                      self._paragraph(f"أيام الراحة: {'، '.join(rest_days)}", styles["rest"]), Spacer(1, 3*mm),
                      self._paragraph(f"التوزيع اليومي: {'  •  '.join(daily_totals)}", styles["meta"]), Spacer(1, 3*mm),
                      self._teacher_schedule_table(teacher_lessons, class_by_id, styles)]

        signature_rows = [
            ["إمضاء المدير(ة) وختم المؤسسة", "رأي المتفقد(ة)", "مصادقة المندوبية الجهوية"],
            ["\n\n\n\n", "\n\n\n\n", "\n\n\n\n"],
        ]
        signature = Table(
            [[self._paragraph(value, styles["signature_header"] if row == 0 else styles["cell"]) for value in values]
             for row, values in enumerate(signature_rows)],
            colWidths=[62*mm] * 3, rowHeights=[12*mm, 45*mm],
        )
        signature.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), .6, _LINE), ("BACKGROUND", (0, 0), (-1, 0), _PALE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story += [PageBreak(), self._heading("المراجعة والمصادقة", styles["section"]),
                  self._paragraph("تمت مراجعة الإسناد وجداول الأوقات طبق القواعد المفعلة للسنة الدراسية.", styles["meta"]),
                  Spacer(1, 8*mm), signature]

        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)

    def export_teacher_schedule(self, out_path, school, teacher, classes, lessons, rules):
        """Export one selected teacher timetable as a print-ready PDF."""
        if not self.font_path.exists():
            raise FileNotFoundError(f"Arabic PDF font is missing: {self.font_path}")
        if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_FONT_NAME, str(self.font_path)))

        teacher_lessons = sorted(
            (item for item in lessons if item.teacher_id == teacher.id),
            key=lambda item: (item.day, item.start_minute),
        )
        if not teacher_lessons:
            raise ValueError("لا توجد حصص مبرمجة لهذا المدرّس.")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        page_size = landscape(A4)
        document = SimpleDocTemplate(
            str(out_path), pagesize=page_size, rightMargin=12*mm, leftMargin=12*mm,
            topMargin=7*mm, bottomMargin=12*mm,
            title=f"جدول أوقات المدرس {teacher.name}",
            author=school.name or "المؤسسة التربوية",
            subject=f"جدول أوقات المدرس - {school.academic_year}",
        )
        document.school_name = school.name or "المؤسسة التربوية"
        styles = self._styles()
        class_by_id = {item.id: item for item in classes}
        total = sum(item.duration for item in teacher_lessons)
        active_days = {item.day for item in teacher_lessons}
        rest_days = ["الأحد", *[DAYS_AR[day] for day in range(6) if day not in active_days]]
        available_width = page_size[0] - 24*mm
        banner = Table(
            [[self._heading(f"جدول أوقات المدرّس: {teacher.name}", styles["banner"]) ]],
            colWidths=[available_width], rowHeights=[10*mm],
        )
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        info = Table(
            [[
                self._multiline([school.academic_year, f"الراحة: {'، '.join(rest_days)}"], styles["meta"]),
                self._multiline([f"أيام العمل: {len(active_days)}", f"المواد: {'، '.join(teacher.subjects) or '—'}"], styles["meta"]),
                self._multiline([teacher.name, f"{total / 60:g} h / {teacher.max_weekly_minutes / 60:g} h"], styles["meta"]),
            ]],
            colWidths=[available_width / 3] * 3,
        )
        info.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), .5, _LINE),
            ("BACKGROUND", (0, 0), (-1, -1), _PALE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story = [
            banner, Spacer(1, 1.5*mm),
            info, Spacer(1, 2*mm),
            self._teacher_schedule_table(teacher_lessons, class_by_id, styles, wide=True),
        ]
        document.build(story, onFirstPage=self._footer, onLaterPages=self._footer)

    @staticmethod
    def _footer(canvas, document):
        page_width = canvas._pagesize[0]
        canvas.saveState(); canvas.setStrokeColor(_LINE); canvas.line(12*mm, 12*mm, page_width-12*mm, 12*mm)
        canvas.setFont(_FONT_NAME, 8); canvas.setFillColor(colors.HexColor("#62778A"))
        canvas.drawRightString(page_width-12*mm, 7.5*mm, _rtl(getattr(document, "school_name", "")))
        canvas.drawString(12*mm, 7.5*mm, _rtl(f"صفحة {document.page}")); canvas.restoreState()

    @staticmethod
    def _duration_label(minutes):
        hours, remaining = divmod(minutes, 60)
        return f"{hours} س و {remaining} دق" if hours and remaining else (f"{hours} س" if hours else f"{remaining} دق")

    @staticmethod
    def _heading(text, style): return Paragraph(escape(_rtl(text)), style)
    @staticmethod
    def _paragraph(text, style): return Paragraph(escape(_rtl(text)), style)

    def _table(self, rows, widths, styles):
        data = [[self._paragraph(value, styles["header"] if index == 0 else styles["cell"]) for value in row]
                for index, row in enumerate(rows)]
        table = Table(data, colWidths=widths, repeatRows=1, hAlign="CENTER")
        commands = [("GRID", (0, 0), (-1, -1), 0.45, _LINE),
                                   ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for row in range(2, len(rows), 2):
            commands.append(("BACKGROUND", (0, row), (-1, row), _PALE))
        table.setStyle(TableStyle(commands))
        return table

    def _teacher_schedule_table(self, lessons, class_by_id, styles, wide=False):
        # Left-to-right physical columns; the day label stays on the far right.
        slots = [
            ("15:00 - 17:00", 900, 1020),
            ("13:00 - 15:00", 780, 900),
            ("12:00 - 13:00", 720, 780),
            ("10:00 - 12:00", 600, 720),
            ("08:00 - 10:00", 480, 600),
        ]
        data = [[self._multiline([label], styles["schedule_header"]) for label, _start, _end in slots]
                + [self._paragraph("اليوم", styles["schedule_header"])]]
        rest_rows = []
        for day in range(6):
            day_lessons = [lesson for lesson in lessons if lesson.day == day]
            rest_day = not day_lessons
            row = []
            for _label, start, end in slots:
                matching = [lesson for lesson in day_lessons
                            if lesson.start_minute < end and lesson.start_minute + lesson.duration > start]
                if rest_day:
                    lines = ["راحة"] if start == 720 else []
                elif start == 720 and not matching:
                    lines = ["راحة منتصف النهار"]
                else:
                    lines = []
                    for index, lesson in enumerate(matching):
                        if wide:
                            lines.extend([
                                f"{minute_to_hhmm(lesson.start_minute)}-{minute_to_hhmm(lesson.start_minute + lesson.duration)}",
                                f"{class_by_id[lesson.class_id].name} • {lesson.subject}",
                            ])
                        else:
                            lines.extend([
                                f"{minute_to_hhmm(lesson.start_minute)}-{minute_to_hhmm(lesson.start_minute + lesson.duration)}",
                                class_by_id[lesson.class_id].name,
                                lesson.subject,
                            ])
                cell_style = styles["schedule_cell_wide"] if wide else styles["schedule_cell"]
                row.append(self._multiline(lines, cell_style))
            row.append(self._paragraph(DAYS_AR[day], styles["schedule_header"]))
            data.append(row)
            if rest_day:
                rest_rows.append(day + 1)

        widths = ([42*mm] * 5 + [35*mm]) if wide else ([31*mm] * 5 + [29*mm])
        heights = ([11*mm] + [23.5*mm] * 6) if wide else ([12*mm] + [24*mm] * 6)
        table = Table(data, colWidths=widths, rowHeights=heights,
                      repeatRows=1, hAlign="CENTER")
        commands = [
            ("GRID", (0, 0), (-1, -1), .6, colors.HexColor("#73808C")),
            ("BACKGROUND", (0, 0), (-1, 0), _ORANGE),
            ("BACKGROUND", (-1, 1), (-1, -1), _ORANGE),
            ("BACKGROUND", (2, 1), (2, -1), colors.HexColor("#F1F3F5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        for row in rest_rows:
            commands.append(("BACKGROUND", (0, row), (-1, row), _REST))
        table.setStyle(TableStyle(commands))
        return table

    @staticmethod
    def _multiline(lines, style):
        if not lines:
            return Paragraph("", style)
        rendered = []
        for line in lines:
            if _ARABIC.search(str(line)):
                rendered.append(escape(_rtl(line)))
            else:
                rendered.append(f'<font name="Helvetica">{escape(str(line))}</font>')
        return Paragraph("<br/>".join(rendered), style)

    def _info_table(self, rows, styles):
        data = [[self._paragraph(value, styles["meta"]) for value in row] for row in rows]
        table = Table(data, colWidths=[93*mm, 93*mm])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), .7, _LINE), ("INNERGRID", (0, 0), (-1, -1), .4, _LINE),
            ("BACKGROUND", (0, 0), (-1, -1), _PALE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        return table

    def _stats_table(self, rows, styles):
        data = [
            [self._paragraph(value, styles["stat_value"] if row == 0 else styles["stat_label"]) for value in values]
            for row, values in enumerate(rows)
        ]
        table = Table(data, colWidths=[46.5*mm] * 4)
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), .7, _LINE), ("INNERGRID", (0, 0), (-1, -1), .4, _LINE),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
            ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ]))
        return table

    @staticmethod
    def _styles():
        base = getSampleStyleSheet()
        return {
            "banner": ParagraphStyle("ArabicBanner", parent=base["Normal"], fontName=_FONT_NAME, textColor=colors.white, fontSize=11, leading=16, alignment=TA_CENTER),
            "title": ParagraphStyle("ArabicTitle", parent=base["Title"], fontName=_FONT_NAME, textColor=_NAVY, fontSize=23, leading=30, alignment=TA_CENTER),
            "subtitle": ParagraphStyle("ArabicSubtitle", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEAL, fontSize=14, leading=19, alignment=TA_CENTER),
            "year": ParagraphStyle("ReportYear", parent=base["Normal"], fontName="Helvetica-Bold", textColor=_TEAL, fontSize=13, leading=18, alignment=TA_CENTER),
            "date": ParagraphStyle("ReportDate", parent=base["Normal"], fontName="Helvetica", textColor=_TEXT, fontSize=9, leading=13, alignment=TA_CENTER),
            "section": ParagraphStyle("ArabicSection", parent=base["Heading2"], fontName=_FONT_NAME, textColor=_NAVY, fontSize=16, leading=22, alignment=TA_CENTER, spaceAfter=3*mm),
            "meta": ParagraphStyle("ArabicMeta", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEXT, fontSize=10, leading=15, alignment=TA_RIGHT),
            "validation": ParagraphStyle("ArabicValidation", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEXT, fontSize=11, leading=16, alignment=TA_CENTER),
            "rest": ParagraphStyle("ArabicRest", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEAL, fontSize=10, leading=15, alignment=TA_RIGHT, spaceBefore=1.5*mm),
            "stat_value": ParagraphStyle("ArabicStatValue", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEAL, fontSize=17, leading=21, alignment=TA_CENTER),
            "stat_label": ParagraphStyle("ArabicStatLabel", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEXT, fontSize=9, leading=12, alignment=TA_CENTER),
            "warning": ParagraphStyle("ArabicWarning", parent=base["Normal"], fontName=_FONT_NAME, fontSize=9, leading=13, alignment=TA_RIGHT, borderColor=colors.HexColor("#bc8d3d"), borderWidth=0.5, borderPadding=5, spaceAfter=2*mm),
            "header": ParagraphStyle("ArabicHeader", parent=base["Normal"], fontName=_FONT_NAME, textColor=colors.white, fontSize=9, leading=12, alignment=TA_CENTER),
            "schedule_header": ParagraphStyle("ScheduleHeader", parent=base["Normal"], fontName=_FONT_NAME, textColor=colors.HexColor("#212529"), fontSize=8.5, leading=10.5, alignment=TA_CENTER),
            "schedule_cell": ParagraphStyle("ScheduleCell", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEXT, fontSize=7.2, leading=8.5, alignment=TA_CENTER),
            "schedule_cell_wide": ParagraphStyle("ScheduleCellWide", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEXT, fontSize=8.6, leading=10.2, alignment=TA_CENTER),
            "signature_header": ParagraphStyle("ArabicSignatureHeader", parent=base["Normal"], fontName=_FONT_NAME, textColor=_NAVY, fontSize=9, leading=12, alignment=TA_CENTER),
            "cell": ParagraphStyle("ArabicCell", parent=base["Normal"], fontName=_FONT_NAME, textColor=_TEXT, fontSize=8.5, leading=11, alignment=TA_CENTER),
        }
