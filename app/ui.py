import os
import tkinter as tk
import traceback
from collections import defaultdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .demo_data import populate_demo_database
from .models import Assignment, DAYS_AR, School
from .pdf_export import PDFExporter
from .solver import PedagogicalSolver, SolverError
from .teacher_import import TeacherImportError, extract_teacher_names_from_docx

NAVY = "#12304A"
NAVY_DARK = "#09243A"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
SUCCESS = "#059669"
WARNING = "#FFB703"
ORANGE = "#FF9800"
BACKGROUND = "#F4F7FB"
CARD = "#FFFFFF"
TEXT = "#263F50"
MUTED = "#718390"
DANGER = "#E32636"
BORDER = "#C8D4DA"
SOFT_BLUE = "#EAF2FF"
TABLE_HEAD = "#EAF0F3"
FONT = "Times New Roman"
SECTION_LETTERS = ("أ", "ب", "ج", "د", "هـ", "و", "ز", "ح")
CLASS_SHIFT_CHOICES = {
    "صباحية  08:00–13:00": "morning",
    "مسائية  12:00–17:00": "afternoon",
}


class MainWindow(tk.Tk):
    def __init__(self, db, rules, root_dir, licence=None):
        super().__init__()
        self.db, self.rules, self.root_dir = db, rules, Path(root_dir)
        self.licence = licence
        self.all_subjects = rules.all_subjects()
        self.last_warnings = []
        self.title("التنظيم البيداغوجي")
        self.geometry("1380x860")
        self.minsize(1180, 760)
        try:
            self.state("zoomed")
        except tk.TclError:
            pass
        self.configure(bg=BACKGROUND)
        self._configure_style()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close_app)
        self.refresh_all()
        if self.licence:
            self.after(300_000, self._periodic_licence_check)

    def report_callback_exception(self, exception_type, exception, traceback_object):
        """Keep an unexpected button/dialog error from closing the application."""
        traceback.print_exception(exception_type, exception, traceback_object)
        messagebox.showerror(
            "خطأ غير متوقع",
            "تعذر إتمام العملية، لكن بياناتك لم تُحذف.\n"
            "أغلق هذه الرسالة وراجع المدخلات أو أعد تشغيل البرنامج.",
            parent=self,
        )

    def _configure_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        # The drop-down list is a Tk listbox, so it needs its own font rule.
        self.option_add("*TCombobox*Listbox.font", (FONT, 18))
        self.option_add("*TCombobox*Listbox.background", "#FFFFFF")
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BACKGROUND, foreground=TEXT, font=(FONT, 14))
        style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=(FONT, 14))
        style.configure("Subtle.TLabel", background=CARD, foreground=MUTED, font=(FONT, 13))
        style.configure("CardTitle.TLabel", background=CARD, foreground=NAVY, font=(FONT, 23, "bold"))
        style.configure("Section.TLabel", background=CARD, foreground=NAVY, font=(FONT, 18, "bold"))
        style.configure("Hero.TLabel", background=BACKGROUND, foreground=NAVY, font=(FONT, 27, "bold"))
        style.configure("PageSubtle.TLabel", background=BACKGROUND, foreground=MUTED, font=(FONT, 14))
        style.configure("Badge.TLabel", background=SOFT_BLUE, foreground=ACCENT_HOVER, font=(FONT, 13, "bold"), padding=(12, 7))
        style.configure("TEntry", fieldbackground="#FFFFFF", foreground=TEXT, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, padding=(12, 10), font=(FONT, 15))
        style.configure("TCombobox", fieldbackground="#FFFFFF", foreground=TEXT, bordercolor=BORDER, padding=(11, 9), font=(FONT, 15), arrowsize=20)
        style.configure("Large.TCombobox", fieldbackground="#FFFFFF", foreground=TEXT, bordercolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT, borderwidth=1, arrowsize=24,
                        padding=(15, 13), font=(FONT, 18, "bold"))
        style.map("Large.TCombobox", bordercolor=[("focus", ACCENT)], fieldbackground=[("readonly", "#F7FAFF")])
        style.configure("Selector.TLabel", background=CARD, foreground=NAVY, font=(FONT, 16, "bold"))
        style.configure("Selector.TButton", background=ACCENT, foreground="#FFFFFF", borderwidth=0,
                        padding=(20, 13), font=(FONT, 15, "bold"))
        style.map("Selector.TButton", background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)])
        style.configure("Primary.TButton", background=ACCENT, foreground="#FFFFFF", borderwidth=0, padding=(18, 11), font=(FONT, 14, "bold"))
        style.map("Primary.TButton", background=[("active", ACCENT_HOVER), ("pressed", ACCENT_HOVER)])
        style.configure("Secondary.TButton", background=TABLE_HEAD, foreground=NAVY, borderwidth=1,
                        bordercolor=BORDER, padding=(16, 10), font=(FONT, 14, "bold"))
        style.map("Secondary.TButton", background=[("active", "#DDE7EC")], bordercolor=[("active", ACCENT)])
        style.configure("Danger.TButton", background="#FFE5E8", foreground=DANGER, borderwidth=0, padding=(15, 10), font=(FONT, 14, "bold"))
        style.map("Danger.TButton", background=[("active", "#F6D7D7")])
        style.configure("Success.TButton", background=SUCCESS, foreground="#FFFFFF", borderwidth=0,
                        padding=(20, 12), font=(FONT, 15, "bold"))
        style.map("Success.TButton", background=[("active", "#10834C"), ("pressed", "#0D7342")])
        style.configure("Info.TButton", background=SOFT_BLUE, foreground=ACCENT_HOVER, borderwidth=0,
                        padding=(17, 10), font=(FONT, 14, "bold"))
        style.map("Info.TButton", background=[("active", "#C7DCFF"), ("pressed", "#B8D2FF")])
        style.configure("Outline.TButton", background="#FFFFFF", foreground=NAVY, borderwidth=1,
                        bordercolor=BORDER, padding=(18, 11), font=(FONT, 14, "bold"))
        style.map("Outline.TButton", background=[("active", "#EDF4FA")], bordercolor=[("active", ACCENT)])
        style.configure("Form.TEntry", fieldbackground="#FFFFFF", foreground=TEXT, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER, padding=(13, 10), font=(FONT, 15))
        style.configure("Form.TCombobox", fieldbackground="#FFFFFF", foreground=TEXT, bordercolor=BORDER,
                        arrowsize=20, padding=(12, 9), font=(FONT, 15))
        style.configure("Form.TSpinbox", fieldbackground="#FFFFFF", foreground=TEXT, bordercolor=BORDER,
                        arrowsize=18, padding=(12, 9), font=(FONT, 15))
        style.configure("App.TNotebook", background=BACKGROUND, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure("App.TNotebook.Tab", background=TABLE_HEAD, foreground=MUTED, padding=(28, 13), font=(FONT, 15, "bold"), borderwidth=1, bordercolor=BORDER)
        style.map("App.TNotebook.Tab", background=[("selected", CARD), ("active", "#EDF3F7")], foreground=[("selected", NAVY)])
        style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=50,
                        borderwidth=0, font=(FONT, 14))
        style.configure("Treeview.Heading", background=TABLE_HEAD, foreground=TEXT, relief="flat",
                        font=(FONT, 15, "bold"), padding=(10, 13))
        style.map("Treeview", background=[("selected", SOFT_BLUE)], foreground=[("selected", NAVY)])
        style.configure("Compact.Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT, rowheight=44, borderwidth=0, font=(FONT, 13))
        style.configure("Compact.Treeview.Heading", background=TABLE_HEAD, foreground=TEXT, relief="flat", font=(FONT, 14, "bold"), padding=(9, 11))
        style.map("Compact.Treeview", background=[("selected", SOFT_BLUE)], foreground=[("selected", NAVY)])
        style.configure("TCheckbutton", background=CARD, foreground=TEXT, font=(FONT, 13))
        style.map("TCheckbutton", background=[("active", CARD)])

    @staticmethod
    def _card(parent, padding=24):
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1, bd=0)
        content = ttk.Frame(card, style="Card.TFrame", padding=padding)
        content.pack(fill="both", expand=True)
        return card, content

    @staticmethod
    def _page_intro(parent, title, subtitle):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 14))
        text_box = ttk.Frame(header)
        text_box.pack(side="right", fill="x", expand=True)
        ttk.Label(text_box, text=title, style="Hero.TLabel").pack(anchor="e")
        ttk.Label(text_box, text=subtitle, style="PageSubtle.TLabel").pack(anchor="e", pady=(1, 0))
        return header

    @staticmethod
    def _format_minutes(minutes):
        hours, remainder = divmod(int(minutes), 60)
        if hours and remainder:
            return f"{hours} س و{remainder} دق"
        if hours:
            return "ساعة" if hours == 1 else f"{hours} س"
        return f"{remainder} دقيقة"

    @staticmethod
    def _short_list(values, limit=3):
        values = list(dict.fromkeys(values))
        if len(values) <= limit:
            return "، ".join(values) if values else "—"
        return f"{'، '.join(values[:limit])}  +{len(values) - limit}"

    @staticmethod
    def _ltr(value):
        return f"\u200e{value}\u200e"

    def _solver(self):
        policy = self.db.schedule_policy()
        policy["rooms"] = [
            {"name": room.name, "kind": room.kind, "enabled": room.enabled,
             "availability": room.availability}
            for room in self.db.rooms()
        ]
        return PedagogicalSolver(
            self.rules,
            policy=policy,
            preferred_rest_days=self.db.teacher_preferred_rest_days(),
        )

    def _require_licence(self, silent=False):
        if not self.licence:
            return True
        status = self.licence.validate()
        if status.valid:
            return True
        if not silent:
            messagebox.showerror("الرخصة غير صالحة", status.message, parent=self)
        return False

    def _periodic_licence_check(self):
        if not self._require_licence(silent=True):
            messagebox.showerror(
                "توقّف التفعيل", "لم تعد الرخصة صالحة. سيُغلق البرنامج لحماية النسخة.", parent=self,
            )
            return self.close_app()
        self.after(300_000, self._periodic_licence_check)

    def _center_dialog(self, dialog, width, height, min_width=None, min_height=None):
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        width = min(width, screen_width - 70)
        height = min(height, screen_height - 90)
        self.update_idletasks()
        parent_x = self.winfo_rootx() if self.winfo_width() > 1 else 0
        parent_y = self.winfo_rooty() if self.winfo_height() > 1 else 0
        parent_width = self.winfo_width() if self.winfo_width() > 1 else screen_width
        parent_height = self.winfo_height() if self.winfo_height() > 1 else screen_height
        x = max(20, parent_x + (parent_width - width) // 2)
        y = max(20, parent_y + (parent_height - height) // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.minsize(min(min_width or width, width), min(min_height or height, height))

    @staticmethod
    def _attach_tree_scrollbars(parent, tree, padding=0):
        vertical = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        vertical.pack(side="left", fill="y", pady=(padding, 18))
        horizontal.pack(side="bottom", fill="x", padx=(18, padding))
        tree.pack(side="right", fill="both", expand=True, padx=(18, padding), pady=(padding, 18))

    def _build(self):
        body = tk.Frame(self, bg=BACKGROUND)
        body.pack(fill="both", expand=True)
        sidebar = tk.Frame(body, bg=CARD, width=252, highlightbackground=BORDER, highlightthickness=1)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)
        brand = tk.Frame(sidebar, bg=CARD, height=112)
        brand.pack(fill="x")
        brand.pack_propagate(False)
        mark = tk.Label(brand, text="ت ب", bg=ACCENT, fg="#FFFFFF", width=3, height=1,
                        font=(FONT, 17, "bold"), padx=5, pady=6)
        mark.pack(side="right", padx=(10, 18), pady=23)
        brand_text = tk.Frame(brand, bg=CARD)
        brand_text.pack(side="right", fill="y", pady=20)
        tk.Label(brand_text, text="التنظيم البيداغوجي", bg=CARD, fg=TEXT,
                 font=(FONT, 18, "bold")).pack(anchor="e")
        tk.Label(brand_text, text="إدارة الإسناد والجداول", bg=CARD, fg=MUTED,
                 font=(FONT, 11)).pack(anchor="e", pady=(2, 0))
        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=16)
        tk.Label(sidebar, text="القائمة الرئيسية", bg=CARD, fg=MUTED,
                 font=(FONT, 12, "bold")).pack(anchor="e", padx=22, pady=(20, 8))

        workspace = tk.Frame(body, bg=BACKGROUND)
        workspace.pack(side="right", fill="both", expand=True)
        topbar = tk.Frame(workspace, bg=CARD, height=66, highlightbackground=BORDER, highlightthickness=1)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)
        tk.Label(topbar, text=f"السنة الدراسية  {self.rules.academic_year}", bg=CARD, fg=TEXT,
                 font=(FONT, 14, "bold")).pack(side="right", padx=26)
        tk.Label(topbar, text="منظومة محلية آمنة  •  حفظ آلي للبيانات", bg=CARD, fg=MUTED,
                 font=(FONT, 12)).pack(side="left", padx=26)
        page_host = ttk.Frame(workspace, padding=(24, 16, 24, 22))
        page_host.pack(fill="both", expand=True)
        self.tab_school = ttk.Frame(page_host)
        self.tab_classes = ttk.Frame(page_host)
        self.tab_rooms = ttk.Frame(page_host)
        self.tab_teachers = ttk.Frame(page_host)
        self.tab_generate = ttk.Frame(page_host)
        self.pages = {"school": self.tab_school, "classes": self.tab_classes, "rooms": self.tab_rooms, "teachers": self.tab_teachers, "generate": self.tab_generate}
        self.nav_buttons = {}
        for key, label in (("school", "01  معلومات المدرسة"), ("classes", "02  الأقسام"), ("rooms", "03  القاعات والتوفّر"), ("teachers", "04  المدرسون والإسناد"), ("generate", "05  التوليد والنتائج")):
            button = tk.Button(
                sidebar, text=label, command=lambda page=key: self.show_page(page), anchor="e",
                bg=CARD, fg=TEXT, activebackground=SOFT_BLUE, activeforeground=NAVY,
                relief="flat", bd=0, padx=22, pady=15, font=(FONT, 15, "bold"), cursor="hand2",
            )
            button.pack(fill="x", padx=14, pady=3)
            self.nav_buttons[key] = button
        hint_card = tk.Frame(sidebar, bg="#F7FAFC", highlightbackground=BORDER, highlightthickness=1)
        hint_card.pack(side="bottom", fill="x", padx=14, pady=16)
        tk.Label(hint_card, text="حالة الملف", bg="#F7FAFC", fg=NAVY,
                 font=(FONT, 13, "bold")).pack(anchor="e", padx=13, pady=(11, 2))
        self.sidebar_hint = tk.Label(
            hint_card, text="املأ البيانات أولاً، ثم ولّد جدولك.", justify="right", wraplength=195,
            bg="#F7FAFC", fg=MUTED, font=(FONT, 12),
        )
        self.sidebar_hint.pack(anchor="e", padx=13, pady=(0, 11))
        self._school_tab(); self._classes_tab(); self._rooms_tab(); self._teachers_tab(); self._generate_tab()
        self.show_page("school")

    def show_page(self, page_name):
        for page in self.pages.values(): page.pack_forget()
        self.pages[page_name].pack(fill="both", expand=True)
        for key, button in self.nav_buttons.items():
            active = key == page_name
            button.configure(bg=ACCENT if active else CARD, fg="#FFFFFF" if active else TEXT)

    def _school_tab(self):
        wrap = ttk.Frame(self.tab_school)
        wrap.pack(fill="both", expand=True)
        self._page_intro(wrap, "بيانات المؤسسة", "خطوة 1 من 4  •  تُدرج هذه البيانات آلياً في الوثائق الرسمية.")
        card, content = self._card(wrap, 30)
        card.pack(fill="x", padx=40)
        ttk.Label(content, text=f"السنة الدراسية {self.rules.academic_year}", style="Badge.TLabel").pack(anchor="e", pady=(0, 18))
        form = ttk.Frame(content, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(0, weight=1)
        self.school_vars = {}
        fields = [("name", "اسم المدرسة"), ("delegation", "المندوبية الجهوية"), ("district", "الدائرة"),
                  ("director", "المدير(ة)"), ("academic_year", "السنة الدراسية")]
        for row, (key, label) in enumerate(fields):
            variable = tk.StringVar(); self.school_vars[key] = variable
            ttk.Label(form, text=label, style="Card.TLabel").grid(row=row, column=1, sticky="e", padx=(18, 0), pady=7)
            ttk.Entry(form, textvariable=variable, justify="right", width=48).grid(row=row, column=0, sticky="ew", pady=7)
        buttons = ttk.Frame(content, style="Card.TFrame")
        buttons.pack(fill="x", pady=(25, 0))
        ttk.Button(buttons, text="حفظ المعلومات", style="Primary.TButton", command=self.save_school).pack(side="right")
        ttk.Button(buttons, text="تحميل بيانات الاختبار", style="Secondary.TButton", command=self.load_demo_data).pack(side="left")

    def _classes_tab(self):
        outer = ttk.Frame(self.tab_classes)
        outer.pack(fill="both", expand=True)
        self._page_intro(
            outer,
            "الأقسام والمستويات",
            "خطوة 2 من 4  •  اختر المستوى ثم الشعبة من القائمتين. المستويات الستة تبقى ظاهرة دائماً.",
        )

        selector_card, selector = self._card(outer, 18)
        selector_card.pack(fill="x", pady=(0, 10))
        self.grade_options = {self.rules.grade(grade)["name"]: grade for grade in range(1, 7)}
        self.class_grade_choice = tk.StringVar(value=next(iter(self.grade_options)))
        self.class_section_choice = tk.StringVar(value=SECTION_LETTERS[0])
        self.class_shift_choice = tk.StringVar(value=next(iter(CLASS_SHIFT_CHOICES)))
        selector_head = ttk.Frame(selector, style="Card.TFrame")
        selector_head.pack(fill="x", pady=(0, 12))
        ttk.Label(selector_head, text="إضافة قسم جديد", style="Section.TLabel").pack(side="right")
        ttk.Label(
            selector_head,
            text="حدّد المستوى والشعبة وفترة الدراسة. يمكن تعديل الفترة لاحقاً من بطاقة القسم.",
            style="Subtle.TLabel",
        ).pack(side="right", padx=18)
        selector_fields = ttk.Frame(selector, style="Card.TFrame")
        selector_fields.pack(fill="x")
        ttk.Label(selector_fields, text="المستوى", style="Selector.TLabel").pack(side="right", padx=(0, 7))
        ttk.Combobox(
            selector_fields, textvariable=self.class_grade_choice, values=list(self.grade_options),
            state="readonly", justify="right", width=18, style="Large.TCombobox",
        ).pack(side="right")
        ttk.Label(selector_fields, text="الشعبة", style="Selector.TLabel").pack(side="right", padx=(18, 7))
        ttk.Combobox(
            selector_fields, textvariable=self.class_section_choice, values=SECTION_LETTERS,
            state="readonly", justify="center", width=7, style="Large.TCombobox",
        ).pack(side="right")
        ttk.Label(selector_fields, text="الفترة", style="Selector.TLabel").pack(side="right", padx=(18, 7))
        ttk.Combobox(
            selector_fields, textvariable=self.class_shift_choice, values=list(CLASS_SHIFT_CHOICES),
            state="readonly", justify="right", width=22, style="Large.TCombobox",
        ).pack(side="right")
        ttk.Button(
            selector_fields, text="+ إضافة القسم", style="Selector.TButton", command=self.add_selected_class,
        ).pack(side="left")

        self.grade_section_hosts = {}
        self.grade_count_labels = {}
        grade_grid = ttk.Frame(outer)
        grade_grid.pack(fill="x")
        for column in range(3):
            grade_grid.columnconfigure(column, weight=1, uniform="grades")
        for row in range(2):
            grade_grid.rowconfigure(row, weight=1)

        for grade in range(1, 7):
            row = (grade - 1) // 3
            column = 2 - ((grade - 1) % 3)
            shell = tk.Frame(grade_grid, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            shell.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
            top = tk.Frame(shell, bg=SOFT_BLUE)
            top.pack(fill="x")
            tk.Label(top, text=self.rules.grade(grade)["name"], bg=SOFT_BLUE, fg=NAVY,
                     font=(FONT, 19, "bold"), padx=13, pady=9).pack(side="right")
            weekly_hours = sum(self.rules.subjects(grade).values()) // 60
            tk.Label(top, text=f"{weekly_hours} ساعة", bg=SOFT_BLUE, fg=ACCENT_HOVER,
                     font=(FONT, 13, "bold"), padx=13).pack(side="left")
            body = tk.Frame(shell, bg=CARD)
            body.pack(fill="both", expand=True, padx=12, pady=9)
            count = tk.Label(body, text="", bg=CARD, fg=MUTED, font=(FONT, 13))
            count.pack(anchor="e", pady=(0, 6))
            self.grade_count_labels[grade] = count
            sections = tk.Frame(body, bg=CARD)
            sections.pack(fill="x")
            for section_column in range(2):
                sections.columnconfigure(section_column, weight=1, uniform="sections")
            self.grade_section_hosts[grade] = sections

        summary_card, summary = self._card(outer, 14)
        summary_card.pack(fill="x", pady=(12, 0))
        self.class_summary = ttk.Label(summary, text="", style="Card.TLabel")
        self.class_summary.pack(side="right")
        ttk.Label(summary, text="بعد إضافة الأقسام اضبط إسناد كل مادة يدوياً، ثم ولّد التوقيت.", style="Subtle.TLabel").pack(side="left")

    def _teachers_tab(self):
        outer = ttk.Frame(self.tab_teachers); outer.pack(fill="both", expand=True)
        intro = self._page_intro(
            outer,
            "المدرسون والإسناد اليدوي",
            f"خطوة 4 من 5  •  أضف الاسم والحجم والمواد، ثم حدّد الأقسام والمواد المسندة فعلياً.",
        )
        actions = ttk.Frame(intro); actions.pack(side="left", anchor="w", pady=(0, 2))
        ttk.Button(actions, text="استيراد الأسماء من DOCX", style="Secondary.TButton", command=self.import_teachers_docx).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="+ إضافة مدرس يدوياً", style="Primary.TButton", command=self.add_teacher).pack(side="left")

        summary_card, summary = self._card(outer, 14); summary_card.pack(fill="x")
        self.teacher_summary = ttk.Label(summary, text="", style="Badge.TLabel", justify="right")
        self.teacher_summary.pack(side="right")
        ttk.Label(summary, text="كل سطر بطاقة مختصرة. انقر نقراً مزدوجاً لفتح بيانات المدرّس كاملة.", style="Subtle.TLabel").pack(side="left", pady=6)

        list_card, list_content = self._card(outer, 0); list_card.pack(fill="both", expand=True, pady=(14, 0))
        toolbar = ttk.Frame(list_content, style="Card.TFrame", padding=(18, 12)); toolbar.pack(fill="x")
        ttk.Label(toolbar, text="قائمة المدرسين", style="Section.TLabel").pack(side="right")
        search_box = ttk.Frame(toolbar, style="Card.TFrame")
        search_box.pack(side="right", padx=(22, 0))
        ttk.Label(search_box, text="بحث", style="Card.TLabel").pack(side="right", padx=(8, 0))
        self.teacher_search = tk.StringVar()
        search = ttk.Entry(search_box, textvariable=self.teacher_search, justify="right", width=30)
        search.pack(side="right")
        self.teacher_search.trace_add("write", lambda *_: self.refresh_teachers())
        ttk.Button(toolbar, text="حذف", style="Danger.TButton", command=self.delete_teacher).pack(side="left")
        ttk.Button(toolbar, text="تعديل", style="Secondary.TButton", command=self.edit_teacher).pack(side="left", padx=8)

        # Treeview draws columns from left to right.  The reversed declaration keeps
        # the most important Arabic field (the teacher's name) on the right.
        columns = ("status", "target", "assigned", "classes", "subjects", "name")
        self.teachers_tree = ttk.Treeview(list_content, columns=columns, show="headings", selectmode="browse")
        definitions = [
            ("status", "الحالة", 95), ("target", "المستهدف", 110), ("assigned", "المُسند", 110),
            ("classes", "الأقسام المسموح بها", 260), ("subjects", "المواد المسموح بها", 300),
            ("name", "الاسم واللقب", 220),
        ]
        for col, text, width in definitions:
            self.teachers_tree.heading(col, text=text)
            self.teachers_tree.column(col, width=width, minwidth=70, anchor="e" if col in {"name", "subjects", "classes"} else "center", stretch=col in {"subjects", "classes"})
        self.teachers_tree.tag_configure("even", background="#F6F9FC")
        self.teachers_tree.tag_configure("odd", background="#FFFFFF")
        self.teachers_tree.tag_configure("warning", foreground="#9A6700")
        self._attach_tree_scrollbars(list_content, self.teachers_tree)
        self.teachers_tree.bind("<Double-1>", lambda _event: self.edit_teacher())

    def _generate_tab(self):
        outer = ttk.Frame(self.tab_generate); outer.pack(fill="both", expand=True)
        self._page_intro(outer, "التوليد والتحقق", "خطوة 5 من 5  •  ثبّت الإسناد اليدوي والقيود، ثم ولّد جدول الأوقات وراجعه.")
        card, bar = self._card(outer, 16); card.pack(fill="x")
        description = ttk.Frame(bar, style="Card.TFrame"); description.pack(side="right")
        ttk.Label(description, text="تركيب جدول الأوقات", style="Section.TLabel").pack(anchor="e")
        ttk.Label(description, text="الإسناد يحدده المدير؛ النظام يركّب التوقيت ويحترم القيود ثم يصدّره PDF.", style="Subtle.TLabel").pack(anchor="e", pady=(2, 0))
        self.generation_summary = ttk.Label(description, text="", style="Badge.TLabel")
        self.generation_summary.pack(anchor="e", pady=(8, 0))
        buttons = ttk.Frame(bar, style="Card.TFrame"); buttons.pack(side="left")
        ttk.Button(buttons, text="إعدادات الجدولة", style="Outline.TButton", command=self.open_schedule_settings).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="ضبط الإسناد اليدوي", style="Info.TButton", command=self.open_manual_assignments).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="عرض جداول المدرسين", style="Secondary.TButton", command=self.show_teacher_timetable).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="تصدير PDF عربي", style="Secondary.TButton", command=self.export_pdf).pack(side="left", padx=(0, 8))
        self.generate_button = ttk.Button(buttons, text="توليد الجدول آلياً", style="Primary.TButton", command=self.generate)
        self.generate_button.pack(side="left")
        self.generation_progress = ttk.Progressbar(bar, mode="indeterminate", length=170)
        result_card, result_content = self._card(outer, 0); result_card.pack(fill="both", expand=True, pady=(16, 0))
        result_head = ttk.Frame(result_content, style="Card.TFrame", padding=(18, 14)); result_head.pack(fill="x")
        ttk.Label(result_head, text="النتائج", style="Section.TLabel").pack(side="right")
        ttk.Label(result_head, text="اختر معلّماً أو حصة ثم استعمل الإجراء المناسب.", style="Subtle.TLabel").pack(side="right", padx=18)
        ttk.Button(
            result_head, text="تعديل الإسناد يدوياً", style="Info.TButton", command=self.edit_assignment,
        ).pack(side="left")
        self.result_tabs = ttk.Notebook(result_content, style="App.TNotebook")
        self.result_tabs.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        assignment_page, schedule_page, warning_page = (ttk.Frame(self.result_tabs, style="Card.TFrame") for _ in range(3))
        self.assignment_page, self.schedule_page, self.warning_page = assignment_page, schedule_page, warning_page
        # Add tabs in reverse so their visible order reads naturally from right to left.
        self.result_tabs.add(warning_page, text="التحقق والتنبيهات")
        self.result_tabs.add(schedule_page, text="جداول الحصص")
        self.result_tabs.add(assignment_page, text="الإسناد حسب المدرّس")

        assignment_toolbar = ttk.Frame(assignment_page, style="Card.TFrame", padding=(10, 9))
        assignment_toolbar.pack(fill="x")
        ttk.Label(assignment_toolbar, text="ملخّص الإسناد", style="Section.TLabel").pack(side="right")
        ttk.Label(
            assignment_toolbar, text="كل معلّم يظهر مرة واحدة؛ انقر مرتين لعرض مواده وأقسامه.", style="Subtle.TLabel",
        ).pack(side="right", padx=18)
        self.assignment_filter = tk.StringVar()
        ttk.Entry(assignment_toolbar, textvariable=self.assignment_filter, justify="right", width=28).pack(side="left")
        ttk.Label(assignment_toolbar, text="بحث", style="Card.TLabel").pack(side="left", padx=8)
        self.assignment_filter.trace_add("write", lambda *_: self._refresh_assignment_rows())
        assignment_host = ttk.Frame(assignment_page, style="Card.TFrame")
        assignment_host.pack(fill="both", expand=True)
        assignment_columns = ("status", "target", "assigned", "classes", "subjects", "specialty", "teacher")
        self.assignment_tree = ttk.Treeview(assignment_host, columns=assignment_columns, show="headings", selectmode="browse")
        for column, label, width, anchor in (
            ("status", "الحالة", 105, "center"), ("target", "المستهدف", 105, "center"),
            ("assigned", "المُسند", 105, "center"),
            ("classes", "الأقسام", 190, "e"), ("subjects", "المواد", 230, "e"),
            ("specialty", "الاختصاص", 150, "e"), ("teacher", "المدرّس(ة)", 190, "e"),
        ):
            self.assignment_tree.heading(column, text=label)
            self.assignment_tree.column(column, width=width, minwidth=90, anchor=anchor, stretch=column in {"classes", "subjects"})
        self.assignment_tree.tag_configure("balanced", background="#EEF9F2", foreground="#0E6B3E")
        self.assignment_tree.tag_configure("underload", background="#FFF8E6", foreground="#815B00")
        self.assignment_tree.tag_configure("unused", background="#FFF0F1", foreground="#A61B29")
        self._attach_tree_scrollbars(assignment_host, self.assignment_tree, padding=10)
        self.assignment_tree.bind("<Double-1>", lambda _event: self.edit_assignment())

        schedule_toolbar = ttk.Frame(schedule_page, style="Card.TFrame", padding=(10, 9))
        schedule_toolbar.pack(fill="x")
        ttk.Label(schedule_toolbar, text="جدول الحصص المفصّل", style="Section.TLabel").pack(side="right")
        self.lesson_filter = tk.StringVar()
        self.lesson_day_filter = tk.StringVar(value="كل الأيام")
        ttk.Combobox(
            schedule_toolbar, textvariable=self.lesson_day_filter,
            values=["كل الأيام", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"],
            state="readonly", justify="right", width=15,
        ).pack(side="left")
        ttk.Entry(schedule_toolbar, textvariable=self.lesson_filter, justify="right", width=27).pack(side="left", padx=8)
        ttk.Label(schedule_toolbar, text="بحث", style="Card.TLabel").pack(side="left")
        self.lesson_filter.trace_add("write", lambda *_: self._refresh_lesson_rows())
        self.lesson_day_filter.trace_add("write", lambda *_: self._refresh_lesson_rows())
        schedule_host = ttk.Frame(schedule_page, style="Card.TFrame")
        schedule_host.pack(fill="both", expand=True)
        self.lesson_tree = ttk.Treeview(schedule_host, columns=("day", "time", "class", "subject", "teacher"), show="headings")
        for column, label, width in (("day", "اليوم", 120), ("time", "التوقيت", 145), ("class", "القسم", 160), ("subject", "المادة", 210), ("teacher", "المدرس(ة)", 250)):
            self.lesson_tree.heading(column, text=label); self.lesson_tree.column(column, width=width, minwidth=90, anchor="e" if column in {"class", "subject", "teacher"} else "center")
        self.lesson_tree.tag_configure("even", background="#F6F9FC")
        self.lesson_tree.tag_configure("odd", background="#FFFFFF")
        self._attach_tree_scrollbars(schedule_host, self.lesson_tree, padding=10)
        warning_host = ttk.Frame(warning_page, style="Card.TFrame")
        warning_host.pack(fill="both", expand=True, padx=10, pady=10)
        self.warning_canvas = tk.Canvas(warning_host, bg=CARD, highlightthickness=0)
        warning_scroll = ttk.Scrollbar(warning_host, orient="vertical", command=self.warning_canvas.yview)
        self.warning_list = tk.Frame(self.warning_canvas, bg=CARD)
        self.warning_window = self.warning_canvas.create_window((0, 0), window=self.warning_list, anchor="nw")
        self.warning_canvas.configure(yscrollcommand=warning_scroll.set)
        warning_scroll.pack(side="left", fill="y")
        self.warning_canvas.pack(side="right", fill="both", expand=True)
        self.warning_list.bind(
            "<Configure>", lambda _event: self.warning_canvas.configure(scrollregion=self.warning_canvas.bbox("all")),
        )
        self.warning_canvas.bind(
            "<Configure>", lambda event: self.warning_canvas.itemconfigure(self.warning_window, width=event.width),
        )

    def save_school(self):
        values = {key: value.get().strip() for key, value in self.school_vars.items()}
        if not values["name"]:
            return messagebox.showwarning("بيانات ناقصة", "اكتب اسم المدرسة قبل الحفظ.")
        if not values["academic_year"]:
            values["academic_year"] = self.rules.academic_year
        self.db.set_school(School(**values))
        messagebox.showinfo("تم الحفظ", "تم حفظ معلومات المدرسة.")

    def load_demo_data(self):
        has_data = bool(self.db.classes() or self.db.teachers())
        if has_data and not messagebox.askyesno(
            "تحميل بيانات الاختبار",
            "سيتم تعويض بيانات المدرسة والأقسام والمدرسين والجداول الحالية ببيانات اختبار كاملة.\nهل تريد المتابعة؟",
        ):
            return
        try:
            result = populate_demo_database(self.db, self.rules, replace=True, generate=True)
        except SolverError as error:
            return messagebox.showerror("تعذر إعداد بيانات الاختبار", str(error))
        self.refresh_all()
        self.show_result(result.warnings if result else [])
        self.show_page("generate")
        messagebox.showinfo(
            "بيانات الاختبار جاهزة",
            f"تم إعداد {len(self.db.classes())} أقسام و{len(self.db.teachers())} مدرساً، مع توليد الإسناد وجدول الحصص.",
        )

    def close_app(self):
        self.db.close()
        self.destroy()

    def add_selected_class(self):
        grade = self.grade_options[self.class_grade_choice.get()]
        letter = self.class_section_choice.get()
        shift = CLASS_SHIFT_CHOICES[self.class_shift_choice.get()]
        class_name = f"{self.rules.grade(grade)['name']} {letter}"
        if any(item.grade == grade and item.name == class_name for item in self.db.classes()):
            return messagebox.showinfo("موجود", f"القسم «{class_name}» مضاف من قبل.")
        self.db.add_class(class_name, grade, shift)
        self.db.clear_generated()
        self.refresh_classes()
        self.show_result([])

    def edit_class_shift(self, class_id, class_name, current_shift):
        dialog = tk.Toplevel(self)
        dialog.title("تحديد فترة القسم")
        dialog.configure(bg=BACKGROUND)
        dialog.transient(self)
        dialog.grab_set()
        self._center_dialog(dialog, 620, 330, 560, 300)
        outer = ttk.Frame(dialog, padding=22)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=f"فترة القسم: {class_name}", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(
            outer,
            text="الصباحي يبدأ 08:00 وينتهي 12:00 أو 13:00 حسب حجم اليوم. المسائي ينتهي 17:00 ويبدأ 12:00 أو 13:00.",
            style="PageSubtle.TLabel", justify="right", wraplength=560,
        ).pack(anchor="e", pady=(4, 18))
        card, choices = self._card(outer, 16)
        card.pack(fill="x")

        def apply_shift(shift):
            if shift != current_shift and self.db.lessons():
                if not messagebox.askyesno(
                    "إعادة التوليد مطلوبة",
                    "تغيير فترة القسم سيحذف الإسناد والجدول المولّدين لأن توقيتاتهما لم تعد صالحة.\nهل تريد المتابعة؟",
                    parent=dialog,
                ):
                    return
            self.db.update_class_shift(class_id, shift)
            if shift != current_shift:
                self.db.clear_generated()
            dialog.destroy()
            self.refresh_classes()
            self.show_result([])

        morning_text = "✓ صباحية  08:00–13:00" if current_shift == "morning" else "صباحية  08:00–13:00"
        afternoon_text = "✓ مسائية  12:00–17:00" if current_shift == "afternoon" else "مسائية  12:00–17:00"
        ttk.Button(
            choices, text=morning_text, style="Primary.TButton", command=lambda: apply_shift("morning"),
        ).pack(fill="x", pady=(0, 8))
        ttk.Button(
            choices, text=afternoon_text, style="Secondary.TButton", command=lambda: apply_shift("afternoon"),
        ).pack(fill="x")
        ttk.Button(outer, text="إلغاء", style="Outline.TButton", command=dialog.destroy).pack(side="left", pady=(14, 0))
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def remove_class(self, class_id, class_name):
        if not messagebox.askyesno(
            "حذف القسم",
            f"هل تريد حذف القسم «{class_name}»؟\nسيُحذف إسناده وجدوله المولّد.",
        ):
            return
        self.db.delete_class(class_id)
        self.db.clear_generated()
        self.refresh_classes()
        self.show_result([])

    def _rooms_tab(self):
        outer = ttk.Frame(self.tab_rooms); outer.pack(fill="both", expand=True)
        intro = self._page_intro(
            outer, "القاعات والتوفّر",
            "خطوة 3 من 5  •  عرّف كل قاعة وأيام وساعات توفرها؛ القاعة الاحتياطية لا تُستعمل إلا عند الضرورة.",
        )
        actions = ttk.Frame(intro); actions.pack(side="left")
        ttk.Button(actions, text="+ إضافة قاعة", style="Primary.TButton", command=self.add_room).pack(side="left")
        ttk.Button(actions, text="تعديل", style="Secondary.TButton", command=self.edit_room).pack(side="left", padx=8)
        ttk.Button(actions, text="حذف", style="Danger.TButton", command=self.delete_room).pack(side="left")
        summary_card, summary = self._card(outer, 14); summary_card.pack(fill="x")
        self.room_summary = ttk.Label(summary, text="", style="Badge.TLabel")
        self.room_summary.pack(side="right")
        ttk.Label(summary, text="التوفّر الفعلي يدخل مباشرة في حساب السعة ومنع تداخل الأقسام.", style="Subtle.TLabel").pack(side="left", pady=6)
        card, content = self._card(outer, 0); card.pack(fill="both", expand=True, pady=(14, 0))
        columns = ("status", "hours", "days", "kind", "name")
        self.rooms_tree = ttk.Treeview(content, columns=columns, show="headings", selectmode="browse")
        for key, title, width in (("status", "الحالة", 110), ("hours", "التوقيت", 180), ("days", "الأيام", 330), ("kind", "النوع", 160), ("name", "اسم القاعة", 220)):
            self.rooms_tree.heading(key, text=title)
            self.rooms_tree.column(key, width=width, anchor="e" if key in {"name", "days"} else "center", stretch=key == "days")
        self.rooms_tree.tag_configure("disabled", foreground=MUTED, background="#F1F5F9")
        self.rooms_tree.tag_configure("regular", background="#FFFFFF")
        self.rooms_tree.tag_configure("emergency", background="#FFF8E6", foreground="#805B00")
        self._attach_tree_scrollbars(content, self.rooms_tree)
        self.rooms_tree.bind("<Double-1>", lambda _event: self.edit_room())

    def _selected_room(self):
        selected = self.rooms_tree.selection() if hasattr(self, "rooms_tree") else ()
        room_id = getattr(self, "room_item_map", {}).get(selected[0]) if selected else None
        return next((room for room in self.db.rooms() if room.id == room_id), None)

    def add_room(self):
        self.open_room_editor()

    def edit_room(self):
        room = self._selected_room()
        if not room:
            return messagebox.showwarning("تنبيه", "اختر قاعة لتعديلها.")
        self.open_room_editor(room)

    def delete_room(self):
        room = self._selected_room()
        if not room:
            return messagebox.showwarning("تنبيه", "اختر قاعة لحذفها.")
        if messagebox.askyesno("حذف القاعة", f"هل تريد حذف «{room.name}»؟"):
            self.db.delete_room(room.id); self.db.clear_generated(); self.refresh_rooms(); self.show_result([])

    def open_room_editor(self, room=None):
        dialog = tk.Toplevel(self); dialog.title("تعديل قاعة" if room else "إضافة قاعة")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 760, 620, 700, 560)
        outer = ttk.Frame(dialog, padding=22); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="بطاقة القاعة", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(outer, text="حدّد الاسم والنوع ثم الأيام والفترة التي تكون فيها القاعة متاحة.", style="PageSubtle.TLabel").pack(anchor="e", pady=(2, 14))
        card, box = self._card(outer, 20); card.pack(fill="both", expand=True)
        name = tk.StringVar(value=room.name if room else "")
        kind_labels = {"قاعة عادية": "regular", "قاعة احتياطية / تحضيري": "emergency"}
        current_kind = next((label for label, key in kind_labels.items() if room and room.kind == key), "قاعة عادية")
        kind = tk.StringVar(value=current_kind); enabled = tk.BooleanVar(value=room.enabled if room else True)
        ttk.Label(box, text="اسم القاعة", style="Section.TLabel").pack(anchor="e")
        ttk.Entry(box, textvariable=name, justify="right").pack(fill="x", pady=(5, 12))
        row = ttk.Frame(box, style="Card.TFrame"); row.pack(fill="x")
        ttk.Combobox(row, textvariable=kind, values=list(kind_labels), state="readonly", justify="right", width=28).pack(side="right")
        ttk.Checkbutton(row, text="القاعة مفعّلة", variable=enabled).pack(side="right", padx=18)
        start = tk.StringVar(value="08:00"); end = tk.StringVar(value="17:00")
        if room:
            intervals = [interval for values in room.availability.values() for interval in values]
            if intervals:
                start.set(f"{min(x[0] for x in intervals)//60:02d}:{min(x[0] for x in intervals)%60:02d}")
                end.set(f"{max(x[1] for x in intervals)//60:02d}:{max(x[1] for x in intervals)%60:02d}")
        time_row = ttk.Frame(box, style="Card.TFrame"); time_row.pack(fill="x", pady=16)
        ttk.Label(time_row, text="من", style="Card.TLabel").pack(side="right", padx=6)
        ttk.Entry(time_row, textvariable=start, width=10, justify="center").pack(side="right")
        ttk.Label(time_row, text="إلى", style="Card.TLabel").pack(side="right", padx=6)
        ttk.Entry(time_row, textvariable=end, width=10, justify="center").pack(side="right")
        day_vars = {}
        days = ttk.Frame(box, style="Card.TFrame"); days.pack(fill="x")
        for index, label in enumerate(DAYS_AR):
            selected = bool(room and room.availability.get(str(index))) if room else True
            day_vars[index] = tk.BooleanVar(value=selected)
            ttk.Checkbutton(days, text=label, variable=day_vars[index]).grid(row=index//3, column=2-index%3, sticky="e", padx=20, pady=8)
        for column in range(3): days.columnconfigure(column, weight=1)
        def save():
            room_name = name.get().strip()
            try:
                start_minute = self.rules.time_to_minute(start.get().strip())
                end_minute = self.rules.time_to_minute(end.get().strip())
            except Exception:
                return messagebox.showerror("توقيت غير صحيح", "استعمل الصيغة 08:00 مثلاً.", parent=dialog)
            if not room_name or start_minute >= end_minute:
                return messagebox.showwarning("بيانات ناقصة", "اكتب اسماً وتوقيتاً صحيحاً.", parent=dialog)
            availability = {str(day): [[start_minute, end_minute]] for day, variable in day_vars.items() if variable.get()}
            try:
                if room: self.db.update_room(room.id, room_name, kind_labels[kind.get()], enabled.get(), availability)
                else: self.db.add_room(room_name, kind_labels[kind.get()], availability)
            except Exception as error:
                return messagebox.showerror("تعذر الحفظ", f"اسم القاعة مستعمل أو البيانات غير صالحة.\n{error}", parent=dialog)
            self.db.clear_generated(); dialog.destroy(); self.refresh_rooms(); self.show_result([])
        footer = ttk.Frame(outer); footer.pack(fill="x", pady=(14, 0))
        ttk.Button(footer, text="حفظ القاعة", style="Success.TButton", command=save).pack(side="right")
        ttk.Button(footer, text="إلغاء", style="Outline.TButton", command=dialog.destroy).pack(side="right", padx=8)

    def add_teacher(self):
        self.open_teacher_editor()

    def _selected_teacher(self):
        selected = self.teachers_tree.selection()
        if not selected:
            return None
        teacher_id = getattr(self, "teacher_item_map", {}).get(selected[0])
        if teacher_id is None:
            return None
        return next((teacher for teacher in self.db.teachers() if teacher.id == teacher_id), None)

    def edit_teacher(self):
        teacher = self._selected_teacher()
        if not teacher:
            return messagebox.showwarning("تنبيه", "اختر مدرساً لتعديل بياناته.")
        self.open_teacher_editor(teacher)

    def open_simple_teacher_editor(self, teacher=None):
        dialog = tk.Toplevel(self)
        dialog.title("تعديل بطاقة المدرّس" if teacher else "إضافة مدرس")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 1180, 820, 980, 700)
        hero = tk.Frame(dialog, bg=NAVY, height=96); hero.pack(fill="x"); hero.pack_propagate(False)
        tk.Label(hero, text="بطاقة المدرّس ونطاق التدريس", bg=NAVY, fg="#FFFFFF", font=(FONT, 25, "bold")).pack(anchor="e", padx=30, pady=(18, 0))
        tk.Label(hero, text="الاسم، الحجم، المواد المسموح بها، ثم اختيار عدة أقسام من القائمة.", bg=NAVY, fg="#D7E7F3", font=(FONT, 13)).pack(anchor="e", padx=30, pady=(2, 0))
        footer = ttk.Frame(dialog, padding=(24, 10, 24, 16)); footer.pack(side="bottom", fill="x")
        host = tk.Frame(dialog, bg=BACKGROUND); host.pack(fill="both", expand=True)
        canvas = tk.Canvas(host, bg=BACKGROUND, highlightthickness=0)
        scroll = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding=22)
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set); scroll.pack(side="left", fill="y"); canvas.pack(side="right", fill="both", expand=True)
        content.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-e.delta / 120), "units"))

        name = tk.StringVar(value=teacher.name if teacher else "")
        hours = tk.StringVar(value=f"{teacher.max_weekly_minutes / 60:g}" if teacher else "18")
        info_card, info = self._card(content, 18); info_card.pack(fill="x")
        ttk.Label(info, text="1  المعلومات الضرورية", style="Section.TLabel").pack(anchor="e", pady=(0, 10))
        fields = ttk.Frame(info, style="Card.TFrame"); fields.pack(fill="x")
        fields.columnconfigure(0, weight=1); fields.columnconfigure(1, weight=3)
        ttk.Label(fields, text="الحجم الأسبوعي المستهدف", style="Card.TLabel").grid(row=0, column=0, sticky="e", padx=8)
        ttk.Spinbox(fields, textvariable=hours, from_=1, to=40, increment=.5, justify="center", width=12).grid(row=1, column=0, sticky="ew", padx=8)
        ttk.Label(fields, text="الاسم واللقب", style="Card.TLabel").grid(row=0, column=1, sticky="e", padx=8)
        ttk.Entry(fields, textvariable=name, justify="right").grid(row=1, column=1, sticky="ew", padx=8)

        subject_card, subject_content = self._card(content, 18); subject_card.pack(fill="x", pady=(12, 0))
        ttk.Label(subject_content, text="2  المواد المسموح بتدريسها", style="Section.TLabel").pack(anchor="e")
        ttk.Label(subject_content, text="اختيار المادة هنا هو ترخيص المدير، وهو المرجع الوحيد للمولّد.", style="Subtle.TLabel").pack(anchor="e", pady=(2, 8))
        subject_grid = tk.Frame(subject_content, bg=CARD); subject_grid.pack(fill="x")
        subject_vars = {subject: tk.BooleanVar(value=bool(teacher and subject in teacher.subjects)) for subject in self.all_subjects}
        for index, subject in enumerate(self.all_subjects):
            tk.Checkbutton(subject_grid, text=subject, variable=subject_vars[subject], anchor="e",
                           bg="#F8FAFC", fg=TEXT, selectcolor="#FFFFFF", activebackground=SOFT_BLUE,
                           relief="flat", highlightbackground=BORDER, highlightthickness=1,
                           padx=10, pady=8, font=(FONT, 12, "bold"), cursor="hand2").grid(
                               row=index//4, column=3-index%4, sticky="ew", padx=4, pady=4)
        for column in range(4): subject_grid.columnconfigure(column, weight=1, uniform="subjects")

        assignment_card, assignment_content = self._card(content, 18); assignment_card.pack(fill="x", pady=(12, 0))
        ttk.Label(assignment_content, text="3  الأقسام التي يمكن لهذا المدرّس تدريسها", style="Section.TLabel").pack(anchor="e")
        ttk.Label(assignment_content, text="يمكن اختيار أكثر من قسم. نفس القسم ونفس المادة يمكن السماح بهما لعدة مدرسين؛ الإسناد النهائي يتم لاحقاً.", style="Subtle.TLabel").pack(anchor="e", pady=(2, 10))
        classes = self.db.classes()
        selected_class_ids = set(teacher.class_ids if teacher else [])
        selector_row = ttk.Frame(assignment_content, style="Card.TFrame"); selector_row.pack(fill="x")
        class_summary = tk.StringVar()
        ttk.Label(selector_row, textvariable=class_summary, style="Badge.TLabel").pack(side="right")

        def update_class_summary():
            labels = [item.name for item in classes if item.id in selected_class_ids]
            class_summary.set(self._short_list(labels, 5) if labels else "لم يتم اختيار أقسام")

        def choose_classes():
            popup = tk.Toplevel(dialog); popup.title("اختيار عدة أقسام")
            popup.configure(bg=BACKGROUND); popup.transient(dialog); popup.grab_set()
            self._center_dialog(popup, 620, 560, 560, 500)
            shell, box = self._card(popup, 20); shell.pack(fill="both", expand=True, padx=14, pady=14)
            ttk.Label(box, text="اختر قسماً أو عدة أقسام", style="Section.TLabel").pack(anchor="e")
            ttk.Label(box, text="Ctrl/Shift للاختيار المتعدد، أو استعمل أزرار تحديد الكل.", style="Subtle.TLabel").pack(anchor="e", pady=(2, 10))
            listbox = tk.Listbox(box, selectmode="multiple", exportselection=False, font=(FONT, 15),
                                 bg="#F8FAFC", fg=TEXT, selectbackground=ACCENT, selectforeground="#FFFFFF",
                                 relief="flat", highlightthickness=1, highlightbackground=BORDER, activestyle="none")
            listbox.pack(fill="both", expand=True)
            for index, school_class in enumerate(classes):
                listbox.insert("end", school_class.name)
                if school_class.id in selected_class_ids: listbox.selection_set(index)
            controls = ttk.Frame(box, style="Card.TFrame"); controls.pack(fill="x", pady=(12, 0))
            ttk.Button(controls, text="تحديد الكل", style="Info.TButton", command=lambda: listbox.selection_set(0, "end")).pack(side="right")
            ttk.Button(controls, text="إلغاء الكل", style="Secondary.TButton", command=lambda: listbox.selection_clear(0, "end")).pack(side="right", padx=8)
            def accept():
                selected_class_ids.clear()
                selected_class_ids.update(classes[index].id for index in listbox.curselection())
                update_class_summary(); popup.destroy()
            ttk.Button(controls, text="اعتماد الاختيار", style="Success.TButton", command=accept).pack(side="left")
        ttk.Button(selector_row, text="فتح قائمة الأقسام المتعددة", style="Primary.TButton", command=choose_classes).pack(side="left")
        update_class_summary()
        if not classes:
            ttk.Label(assignment_content, text="أضف الأقسام أولاً من الخطوة الثانية.", style="Subtle.TLabel").pack(anchor="e", pady=12)

        def save():
            teacher_name = name.get().strip()
            try: weekly_minutes = int(float(hours.get().replace(",", ".")) * 60)
            except ValueError: return messagebox.showerror("خطأ", "الحجم الأسبوعي غير صحيح.", parent=dialog)
            selected_subjects = [subject for subject, variable in subject_vars.items() if variable.get()]
            if not teacher_name or weekly_minutes <= 0 or not selected_subjects or not selected_class_ids:
                return messagebox.showwarning("بيانات ناقصة", "الاسم والحجم ومادة واحدة وقسم واحد على الأقل مطلوبة.", parent=dialog)
            if teacher:
                teacher_id = teacher.id
                self.db.update_teacher(teacher_id, teacher_name, "إسناد يدوي", weekly_minutes, selected_subjects, "", 0)
            else:
                teacher_id = self.db.add_teacher(teacher_name, "إسناد يدوي", weekly_minutes, selected_subjects, "", 0)
            self.db.set_teacher_classes(teacher_id, selected_class_ids)
            self.db.clear_generated()
            dialog.destroy(); self.refresh_teachers(); self.show_result([])
            messagebox.showinfo("تم الحفظ", "تم حفظ المواد والأقسام المسموح بها. اضبط الإسناد النهائي من شاشة الإسناد اليدوي.")
        ttk.Button(footer, text="حفظ بطاقة المدرّس", style="Success.TButton", command=save).pack(side="right")
        ttk.Button(footer, text="إلغاء", style="Outline.TButton", command=dialog.destroy).pack(side="right", padx=8)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        dialog.bind("<Control-s>", lambda _e: save())

    def open_teacher_editor(self, teacher=None):
        return self.open_simple_teacher_editor(teacher)
        dialog = tk.Toplevel(self)
        dialog.title("تعديل مدرس" if teacher else "إضافة مدرس")
        dialog.configure(bg=BACKGROUND)
        dialog.transient(self)
        dialog.grab_set()
        target_width = min(1120, dialog.winfo_screenwidth() - 80)
        target_height = min(820, dialog.winfo_screenheight() - 100)
        parent_x = self.winfo_rootx() if self.winfo_width() > 1 else 0
        parent_y = self.winfo_rooty() if self.winfo_height() > 1 else 0
        parent_width = self.winfo_width() if self.winfo_width() > 1 else dialog.winfo_screenwidth()
        parent_height = self.winfo_height() if self.winfo_height() > 1 else dialog.winfo_screenheight()
        x = max(20, parent_x + (parent_width - target_width) // 2)
        y = max(20, parent_y + (parent_height - target_height) // 2)
        dialog.geometry(f"{target_width}x{target_height}+{x}+{y}")
        dialog.minsize(min(980, target_width), min(720, target_height))

        hero = tk.Frame(dialog, bg=CARD, height=94, highlightbackground=BORDER, highlightthickness=1)
        hero.pack(fill="x")
        hero.pack_propagate(False)
        tk.Frame(hero, bg=ACCENT, height=4).pack(fill="x")
        hero_text = tk.Frame(hero, bg=CARD)
        hero_text.pack(side="right", fill="y", padx=30, pady=12)
        tk.Label(
            hero_text, text="تعديل بطاقة المدرس" if teacher else "إضافة مدرس جديد",
            bg=CARD, fg=NAVY, font=(FONT, 25, "bold"),
        ).pack(anchor="e")
        tk.Label(
            hero_text, text="أدخل البيانات الأساسية ثم راجع المواد المقترحة قبل الحفظ.",
            bg=CARD, fg=MUTED, font=(FONT, 13),
        ).pack(anchor="e", pady=(2, 0))
        tk.Label(
            hero, text="بطاقة المدرّس", bg=SOFT_BLUE, fg=ACCENT_HOVER, font=(FONT, 14, "bold"),
            padx=18, pady=7,
        ).pack(side="left", padx=30)

        # Keep the actions visible and let the form scroll on smaller laptop
        # screens.  This prevents the subject grid or save button from being
        # clipped when Windows display scaling is above 100%.
        dialog_footer = ttk.Frame(dialog, padding=(26, 10, 26, 16))
        dialog_footer.pack(side="bottom", fill="x")
        content_host = tk.Frame(dialog, bg=BACKGROUND)
        content_host.pack(fill="both", expand=True)
        content_canvas = tk.Canvas(content_host, bg=BACKGROUND, highlightthickness=0)
        content_scroll = ttk.Scrollbar(content_host, orient="vertical", command=content_canvas.yview)
        content = ttk.Frame(content_canvas, padding=(26, 18, 26, 12))
        content_window = content_canvas.create_window((0, 0), window=content, anchor="nw")
        content_canvas.configure(yscrollcommand=content_scroll.set)
        content_scroll.pack(side="left", fill="y")
        content_canvas.pack(side="right", fill="both", expand=True)
        content.bind(
            "<Configure>", lambda _event: content_canvas.configure(scrollregion=content_canvas.bbox("all")),
        )
        content_canvas.bind(
            "<Configure>", lambda event: content_canvas.itemconfigure(content_window, width=event.width),
        )
        content_canvas.bind(
            "<MouseWheel>", lambda event: content_canvas.yview_scroll(int(-event.delta / 120), "units"),
        )

        name = tk.StringVar(value=teacher.name if teacher else "")
        specialty = tk.StringVar(value=teacher.specialty if teacher else (self.rules.specialties()[0] if self.rules.specialties() else ""))
        training = tk.StringVar(value=teacher.training if teacher else (self.rules.trainings()[0] if self.rules.trainings() else ""))
        experience = tk.StringVar(value=str(teacher.experience_years if teacher else 0))
        hours = tk.StringVar(value=f"{teacher.max_weekly_minutes / 60:g}" if teacher else "18")

        info_card, info = self._card(content, 20)
        info_card.pack(fill="x")
        info_head = ttk.Frame(info, style="Card.TFrame")
        info_head.pack(fill="x", pady=(0, 12))
        ttk.Label(info_head, text="1", style="Badge.TLabel").pack(side="right", padx=(10, 0))
        ttk.Label(info_head, text="المعلومات الأساسية", style="Section.TLabel").pack(side="right")
        ttk.Label(info_head, text="الحقول المطلوبة واضحة ويمكن تعديلها لاحقاً.", style="Subtle.TLabel").pack(side="left")

        form = ttk.Frame(info, style="Card.TFrame")
        form.pack(fill="x")
        form.columnconfigure(0, weight=1, uniform="teacher_fields")
        form.columnconfigure(1, weight=1, uniform="teacher_fields")

        def field_cell(title, row, column):
            cell = tk.Frame(form, bg=CARD)
            cell.grid(row=row, column=column, sticky="ew", padx=(0, 9) if column == 0 else (9, 0), pady=7)
            tk.Label(cell, text=title, bg=CARD, fg=NAVY, font=(FONT, 14, "bold")).pack(anchor="e", pady=(0, 5))
            return cell

        name_cell = field_cell("الاسم واللقب *", 0, 1)
        ttk.Entry(name_cell, textvariable=name, justify="right", style="Form.TEntry").pack(fill="x")
        specialty_cell = field_cell("الاختصاص العلمي *", 0, 0)
        ttk.Combobox(
            specialty_cell, textvariable=specialty, values=self.rules.specialties(), state="readonly",
            justify="right", style="Form.TCombobox",
        ).pack(fill="x")
        training_cell = field_cell("التكوين الخاص", 1, 1)
        ttk.Combobox(
            training_cell, textvariable=training, values=self.rules.trainings(), state="readonly",
            justify="right", style="Form.TCombobox",
        ).pack(fill="x")
        workload_cell = field_cell("الحجم الساعي المستهدف والخبرة", 1, 0)
        workload = tk.Frame(workload_cell, bg=CARD)
        workload.pack(fill="x")
        for column in range(2):
            workload.columnconfigure(column, weight=1, uniform="workload")
        hours_box = tk.Frame(workload, bg=CARD)
        hours_box.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        tk.Label(hours_box, text="الحجم الأسبوعي المستهدف (ساعة)", bg=CARD, fg=MUTED, font=(FONT, 12)).pack(anchor="e")
        ttk.Spinbox(
            hours_box, textvariable=hours, from_=1, to=40, increment=.5, justify="center", style="Form.TSpinbox",
        ).pack(fill="x", pady=(3, 0))
        experience_box = tk.Frame(workload, bg=CARD)
        experience_box.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        tk.Label(experience_box, text="سنوات الخبرة", bg=CARD, fg=MUTED, font=(FONT, 12)).pack(anchor="e")
        ttk.Spinbox(
            experience_box, textvariable=experience, from_=0, to=50, justify="center", style="Form.TSpinbox",
        ).pack(fill="x", pady=(3, 0))

        subjects_card, subjects_content = self._card(content, 18)
        subjects_card.pack(fill="both", expand=True, pady=(14, 0))
        subject_head = ttk.Frame(subjects_content, style="Card.TFrame")
        subject_head.pack(fill="x", pady=(0, 10))
        ttk.Label(subject_head, text="2", style="Badge.TLabel").pack(side="right", padx=(10, 0))
        ttk.Label(subject_head, text="المواد المسموح بإسنادها", style="Section.TLabel").pack(side="right")
        subject_vars = {subject: tk.BooleanVar(value=subject in (teacher.subjects if teacher else [])) for subject in self.all_subjects}
        subject_box = tk.Frame(subjects_content, bg=CARD)
        subject_box.pack(fill="both", expand=True)
        for index, subject in enumerate(self.all_subjects):
            tk.Checkbutton(
                subject_box, text=subject, variable=subject_vars[subject], anchor="e", justify="right",
                bg="#F7FAFC", fg=TEXT, activebackground=SOFT_BLUE, activeforeground=NAVY,
                selectcolor="#FFFFFF", relief="flat", bd=0, highlightthickness=1,
                highlightbackground=BORDER, padx=12, pady=9, font=(FONT, 13, "bold"), cursor="hand2",
            ).grid(row=index // 4, column=3 - index % 4, sticky="ew", padx=5, pady=5)
        for column in range(4):
            subject_box.columnconfigure(column, weight=1, uniform="subjects")

        def apply_recommendations():
            recommended = set(self.rules.recommended_subjects(specialty.get(), training.get()))
            for subject, variable in subject_vars.items():
                variable.set(subject in recommended)

        ttk.Button(
            subject_head, text="اختيار مواد الاختصاص المقترحة", style="Info.TButton", command=apply_recommendations,
        ).pack(side="left")
        if not teacher:
            apply_recommendations()

        def save():
            teacher_name = name.get().strip()
            selected_subjects = [subject for subject, variable in subject_vars.items() if variable.get()]
            if not teacher_name or not selected_subjects:
                return messagebox.showwarning("بيانات ناقصة", "الاسم ومادة واحدة على الأقل مطلوبان.", parent=dialog)
            try:
                weekly_minutes = int(float(hours.get().replace(",", ".")) * 60)
                years = int(experience.get())
            except ValueError:
                return messagebox.showerror("خطأ", "الخبرة أو الحجم الساعي غير صحيح.", parent=dialog)
            if weekly_minutes <= 0 or years < 0:
                return messagebox.showerror("خطأ", "راجع سنوات الخبرة والحجم الساعي.", parent=dialog)
            values = (teacher_name, specialty.get(), weekly_minutes, selected_subjects, training.get(), years)
            if teacher:
                self.db.update_teacher(teacher.id, *values)
            else:
                self.db.add_teacher(*values)
            self.db.clear_generated()
            dialog.destroy(); self.refresh_teachers(); self.show_result([])

        ttk.Button(dialog_footer, text="حفظ المدرس  ✓", style="Success.TButton", command=save).pack(side="right")
        ttk.Button(dialog_footer, text="إلغاء", style="Outline.TButton", command=dialog.destroy).pack(side="right", padx=10)
        ttk.Label(dialog_footer, text="* حقول إجبارية", style="PageSubtle.TLabel").pack(side="left", pady=10)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.bind("<Control-s>", lambda _event: save())
        dialog.bind("<Control-S>", lambda _event: save())

    def _pick_subjects(self, parent, selected, callback):
        dialog = tk.Toplevel(parent); dialog.title("اختيار المواد"); dialog.configure(bg=BACKGROUND); dialog.transient(parent); dialog.grab_set(); dialog.resizable(False, False)
        shell, box = self._card(dialog, 22); shell.pack(padx=14, pady=14)
        ttk.Label(box, text="المواد التي يمكن للمدرس تدريسها", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="e", pady=(0, 10))
        variables = {subject: tk.BooleanVar(value=subject in selected) for subject in self.all_subjects}
        for index, subject in enumerate(self.all_subjects):
            ttk.Checkbutton(box, text=subject, variable=variables[subject]).grid(row=1 + index // 3, column=2 - index % 3, sticky="e", padx=14, pady=6)
        def accept():
            values = [subject for subject, variable in variables.items() if variable.get()]
            if not values:
                return messagebox.showwarning("تنبيه", "اختر مادة واحدة على الأقل.", parent=dialog)
            callback(values); dialog.destroy()
        ttk.Button(box, text="اعتماد المواد", style="Primary.TButton", command=accept).grid(row=8, column=0, columnspan=3, pady=(15, 0))
        self._center_dialog(dialog, 780, 500, 720, 460)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def import_teachers_docx(self):
        path = filedialog.askopenfilename(title="اختيار قائمة المدرسين", filetypes=[("Word DOCX", "*.docx")])
        if not path:
            return
        try:
            names = extract_teacher_names_from_docx(path)
        except TeacherImportError as error:
            return messagebox.showerror("تعذر الاستيراد", str(error))
        self._open_simple_teacher_import(names, Path(path).name)

    def _open_simple_teacher_import(self, names, source_name):
        dialog = tk.Toplevel(self); dialog.title("استيراد أسماء المدرسين")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 900, 680, 780, 600)
        outer = ttk.Frame(dialog, padding=20); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="استيراد الأسماء فقط", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(outer, text=f"{self._ltr(source_name)}  •  اختر المواد المشتركة الآن، ثم عدّل إسناد كل مدرس من بطاقته.", style="PageSubtle.TLabel").pack(anchor="e", pady=(2, 12))
        subjects_card, subjects_box = self._card(outer, 16); subjects_card.pack(fill="x")
        ttk.Label(subjects_box, text="المواد المسموح بها مبدئياً", style="Section.TLabel").pack(anchor="e", pady=(0, 8))
        variables = {subject: tk.BooleanVar(value=False) for subject in self.all_subjects}
        grid = tk.Frame(subjects_box, bg=CARD); grid.pack(fill="x")
        for index, subject in enumerate(self.all_subjects):
            ttk.Checkbutton(grid, text=subject, variable=variables[subject]).grid(row=index//4, column=3-index%4, sticky="e", padx=8, pady=5)
        for column in range(4): grid.columnconfigure(column, weight=1)
        names_card, names_box = self._card(outer, 14); names_card.pack(fill="both", expand=True, pady=12)
        text_widget = tk.Text(names_box, height=12, font=(FONT, 14), wrap="word", relief="flat", bg="#F8FAFC", fg=TEXT)
        text_widget.pack(fill="both", expand=True); text_widget.insert("1.0", "\n".join(names))
        hours = tk.StringVar(value="18")
        footer = ttk.Frame(outer); footer.pack(fill="x")
        ttk.Label(footer, text="الحجم الأسبوعي").pack(side="right", padx=6)
        ttk.Spinbox(footer, textvariable=hours, from_=1, to=40, increment=.5, width=8, justify="center").pack(side="right")
        def import_rows():
            selected_subjects = [subject for subject, variable in variables.items() if variable.get()]
            imported_names = [line.strip() for line in text_widget.get("1.0", "end").splitlines() if line.strip()]
            try: minutes = int(float(hours.get().replace(",", ".")) * 60)
            except ValueError: return messagebox.showerror("خطأ", "الحجم الأسبوعي غير صحيح.", parent=dialog)
            if not selected_subjects or not imported_names:
                return messagebox.showwarning("بيانات ناقصة", "اختر مادة واكتب اسماً واحداً على الأقل.", parent=dialog)
            existing = {item.name.casefold() for item in self.db.teachers()}; added = 0
            for teacher_name in imported_names:
                if teacher_name.casefold() in existing: continue
                self.db.add_teacher(teacher_name, "إسناد يدوي", minutes, selected_subjects, "", 0)
                existing.add(teacher_name.casefold()); added += 1
            dialog.destroy(); self.refresh_teachers(); messagebox.showinfo("تم الاستيراد", f"تمت إضافة {added} مدرساً. افتح كل بطاقة لضبط الأقسام المسندة.")
        ttk.Button(footer, text="استيراد", style="Success.TButton", command=import_rows).pack(side="left")
        ttk.Button(footer, text="إلغاء", style="Outline.TButton", command=dialog.destroy).pack(side="left", padx=8)

    def _open_teacher_import(self, names, source_name):
        dialog = tk.Toplevel(self); dialog.title("مراجعة قائمة المدرسين"); dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 1080, 720, 940, 620)
        outer = ttk.Frame(dialog, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=f"مراجعة {len(names)} اسماً قبل الاستيراد", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(
            outer,
            text=f"المصدر: {self._ltr(source_name)}  •  صحّح الاسم إن لزم، واختر اختصاص كل مدرس. زر المواد يتيح تحديد المواد بدقة.",
            style="PageSubtle.TLabel",
        ).pack(anchor="e", pady=(3, 12))

        quick_card, quick = self._card(outer, 14); quick_card.pack(fill="x")
        common_specialty = tk.StringVar(value=self.rules.specialties()[0])
        common_training = tk.StringVar(value=self.rules.trainings()[0])
        ttk.Label(quick, text="تطبيق سريع على الجميع", style="Section.TLabel").pack(side="right", padx=(14, 0))
        ttk.Combobox(quick, textvariable=common_specialty, values=self.rules.specialties(), state="readonly", justify="right", width=24).pack(side="right", padx=6)
        ttk.Combobox(quick, textvariable=common_training, values=self.rules.trainings(), state="readonly", justify="right", width=26).pack(side="right", padx=6)

        rows_card, rows_host = self._card(outer, 0); rows_card.pack(fill="both", expand=True, pady=(12, 0))
        canvas = tk.Canvas(rows_host, bg=CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(rows_host, orient="vertical", command=canvas.yview)
        rows = ttk.Frame(canvas, style="Card.TFrame", padding=(12, 8))
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="left", fill="y"); canvas.pack(side="right", fill="both", expand=True)
        rows.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        for column, label in enumerate(("المواد", "الحجم", "الخبرة", "التكوين", "الاختصاص", "الاسم واللقب")):
            ttk.Label(rows, text=label, style="Section.TLabel").grid(row=0, column=column, padx=6, pady=(4, 10), sticky="e")
        rows.columnconfigure(5, weight=1); rows.columnconfigure(4, weight=1); rows.columnconfigure(3, weight=1)

        records = []
        def refresh_record(record, reset=True):
            if reset:
                record["subjects"] = self.rules.recommended_subjects(record["specialty"].get(), record["training"].get())
            record["subject_button"].configure(text=f"المواد ({len(record['subjects'])})")

        for index, teacher_name in enumerate(names, 1):
            record = {
                "name": tk.StringVar(value=teacher_name), "specialty": tk.StringVar(value=self.rules.specialties()[0]),
                "training": tk.StringVar(value=self.rules.trainings()[0]), "experience": tk.StringVar(value="0"),
                "hours": tk.StringVar(value="18"), "subjects": [],
            }
            ttk.Entry(rows, textvariable=record["name"], justify="right", width=27).grid(row=index, column=5, sticky="ew", padx=5, pady=5)
            specialty_box = ttk.Combobox(rows, textvariable=record["specialty"], values=self.rules.specialties(), state="readonly", justify="right", width=21)
            specialty_box.grid(row=index, column=4, sticky="ew", padx=5, pady=5)
            training_box = ttk.Combobox(rows, textvariable=record["training"], values=self.rules.trainings(), state="readonly", justify="right", width=23)
            training_box.grid(row=index, column=3, sticky="ew", padx=5, pady=5)
            ttk.Spinbox(rows, textvariable=record["experience"], from_=0, to=50, width=6, justify="center").grid(row=index, column=2, padx=5, pady=5)
            ttk.Spinbox(rows, textvariable=record["hours"], from_=1, to=40, increment=.5, width=6, justify="center").grid(row=index, column=1, padx=5, pady=5)
            record["subject_button"] = ttk.Button(rows, text="المواد", style="Secondary.TButton")
            record["subject_button"].grid(row=index, column=0, padx=5, pady=5)
            record["subject_button"].configure(command=lambda r=record: self._pick_subjects(dialog, r["subjects"], lambda values, rec=r: (rec.update(subjects=values), refresh_record(rec, False))))
            specialty_box.bind("<<ComboboxSelected>>", lambda _event, r=record: refresh_record(r))
            training_box.bind("<<ComboboxSelected>>", lambda _event, r=record: refresh_record(r))
            refresh_record(record); records.append(record)

        def apply_all():
            for record in records:
                record["specialty"].set(common_specialty.get()); record["training"].set(common_training.get()); refresh_record(record)
        ttk.Button(quick, text="تطبيق", style="Primary.TButton", command=apply_all).pack(side="left")

        def import_rows():
            existing = {teacher.name.casefold() for teacher in self.db.teachers()}
            payload, skipped = [], []
            for record in records:
                teacher_name = record["name"].get().strip()
                if not teacher_name or teacher_name.casefold() in existing:
                    skipped.append(teacher_name or "اسم فارغ"); continue
                try:
                    minutes = int(float(record["hours"].get().replace(",", ".")) * 60)
                    years = int(record["experience"].get())
                except ValueError:
                    return messagebox.showerror("خطأ", f"راجع الحجم أو الخبرة للمدرس {teacher_name}.", parent=dialog)
                if not record["subjects"]:
                    return messagebox.showwarning("مواد ناقصة", f"اختر مادة واحدة على الأقل للمدرس {teacher_name}.", parent=dialog)
                payload.append((teacher_name, record["specialty"].get(), minutes, record["subjects"], record["training"].get(), years))
                existing.add(teacher_name.casefold())
            if not payload:
                return messagebox.showwarning("لا توجد إضافات", "كل الأسماء موجودة أو غير صالحة.", parent=dialog)
            self.db.add_teachers(payload); self.db.clear_generated(); dialog.destroy(); self.refresh_teachers(); self.show_result([])
            note = f"تم استيراد {len(payload)} مدرساً."
            if skipped: note += f" تم تجاهل {len(skipped)} اسماً مكرراً أو فارغاً."
            messagebox.showinfo("تم الاستيراد", note)

        footer = ttk.Frame(outer); footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="إلغاء", style="Secondary.TButton", command=dialog.destroy).pack(side="left")
        ttk.Button(footer, text="استيراد القائمة", style="Primary.TButton", command=import_rows).pack(side="left", padx=8)

    def delete_teacher(self):
        teacher = self._selected_teacher()
        if not teacher: return messagebox.showwarning("تنبيه", "اختر مدرساً للحذف.")
        if not messagebox.askyesno("تأكيد الحذف", f"حذف المدرس(ة) «{teacher.name}»؟ سيُحذف إسناده وجدوله المولّد."):
            return
        self.db.delete_teacher(teacher.id); self.db.clear_generated(); self.refresh_teachers(); self.show_result([])

    def _schedule_policy(self):
        defaults = {
            "available_rooms": int(self.rules.assignment_rule("available_rooms", 6)),
            "emergency_room_count": int(self.rules.assignment_rule("emergency_room_count", 0)),
            "emergency_room_available_from": str(self.rules.assignment_rule("emergency_room_available_from", "12:00")),
            "emergency_room_available_all_saturday": bool(self.rules.assignment_rule("emergency_room_available_all_saturday", False)),
            "school_start": "08:00", "school_end": "17:00",
            "morning_start": "08:00", "morning_end": "13:00",
            "afternoon_start": "12:00", "afternoon_end": "17:00",
            "preferred_saturday_end": str(self.rules.assignment_rule("preferred_saturday_end", "13:00")),
            "saturday_afternoon_free": True,
            "preferred_teacher_working_days": self.rules.teacher_preferred_working_days(),
            "max_teacher_working_days": self.rules.teacher_max_working_days(),
            "teacher_daily_max_minutes": self.rules.teacher_daily_max(),
            "teacher_balanced_day_minutes": self.rules.teacher_balanced_day(),
            "teacher_transition_minutes": 0,
        }
        defaults.update(self.db.schedule_policy())
        return defaults

    def open_schedule_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("إعدادات الجدولة")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 1040, 760, 920, 680)
        outer = ttk.Frame(dialog, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="إعدادات المدرسة والقيود", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(
            outer,
            text="هذه القواعد تخص المدرسة الحالية. الإسناد يبقى يدوياً والنظام يستعملها لتركيب التوقيت فقط.",
            style="PageSubtle.TLabel",
        ).pack(anchor="e", pady=(2, 12))

        notebook = ttk.Notebook(outer, style="App.TNotebook")
        notebook.pack(fill="both", expand=True)
        general = ttk.Frame(notebook, style="Card.TFrame", padding=20)
        availability = ttk.Frame(notebook, style="Card.TFrame", padding=20)
        notebook.add(availability, text="راحة المدرسين")
        notebook.add(general, text="القاعات والفترات")

        policy = self._schedule_policy()
        variables = {}
        fields = [
            ("available_rooms", "عدد القاعات العادية", "int"),
            ("emergency_room_count", "عدد القاعات الاحتياطية", "int"),
            ("school_start", "بداية اليوم", "time"),
            ("school_end", "نهاية اليوم", "time"),
            ("morning_start", "بداية الفترة الصباحية", "time"),
            ("morning_end", "نهاية الفترة الصباحية", "time"),
            ("afternoon_start", "بداية الفترة المسائية", "time"),
            ("afternoon_end", "نهاية الفترة المسائية", "time"),
            ("emergency_room_available_from", "توفر القاعة الاحتياطية من", "time"),
            ("preferred_saturday_end", "نهاية السبت المطلوبة", "time"),
            ("preferred_teacher_working_days", "أيام العمل المفضلة للمدرس", "int"),
            ("max_teacher_working_days", "أقصى أيام عمل للمدرس", "int"),
            ("teacher_daily_max_minutes", "أقصى عمل يومي بالدقائق", "int"),
            ("teacher_balanced_day_minutes", "الحجم اليومي المتوازن بالدقائق", "int"),
            ("teacher_transition_minutes", "راحة الانتقال صباح/مساء بالدقائق", "int"),
        ]
        for column in (0, 2):
            general.columnconfigure(column, weight=1)
        for index, (key, label, _kind) in enumerate(fields):
            block = 0 if index < 8 else 1
            row = index if block == 0 else index - 8
            entry_column = 2 if block == 0 else 0
            label_column = entry_column + 1
            variable = tk.StringVar(value=str(policy[key])); variables[key] = variable
            ttk.Label(general, text=label, style="Card.TLabel").grid(
                row=row, column=label_column, sticky="e", padx=(12, 6), pady=6,
            )
            ttk.Entry(general, textvariable=variable, justify="center", width=18).grid(
                row=row, column=entry_column, sticky="ew", padx=(8, 16), pady=6,
            )

        saturday_free = tk.BooleanVar(value=bool(policy["saturday_afternoon_free"]))
        emergency_saturday = tk.BooleanVar(value=bool(policy["emergency_room_available_all_saturday"]))
        checks = ttk.Frame(general, style="Card.TFrame")
        checks.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(14, 0))
        ttk.Checkbutton(checks, text="السبت بعد الوقت المحدد راحة", variable=saturday_free).pack(side="right", padx=12)
        ttk.Checkbutton(checks, text="القاعات الاحتياطية متاحة السبت كاملاً", variable=emergency_saturday).pack(side="right", padx=12)

        teachers = self.db.teachers()
        teacher_by_label = {f"{item.name}  •  {item.id}": item for item in teachers}
        teacher_choice = tk.StringVar(value=next(iter(teacher_by_label), ""))
        ttk.Label(availability, text="اختر المدرس ثم حدّد يومي الراحة المفضّلين", style="Section.TLabel").pack(anchor="e", pady=(0, 14))
        ttk.Label(availability, text="هذه أفضلية وليست منعاً: عند الضرورة يمكن للنظام استعمال أحد اليومين.", style="Subtle.TLabel").pack(anchor="e", pady=(0, 12))
        teacher_combo = ttk.Combobox(
            availability, textvariable=teacher_choice, values=list(teacher_by_label),
            state="readonly", justify="right", style="Large.TCombobox",
        )
        teacher_combo.pack(fill="x")
        day_vars = [tk.BooleanVar() for _ in DAYS_AR]
        days_box = ttk.Frame(availability, style="Card.TFrame")
        days_box.pack(fill="x", pady=24)
        for day, variable in zip(DAYS_AR, day_vars):
            ttk.Checkbutton(days_box, text=day, variable=variable).pack(side="right", padx=10)

        def load_teacher_days(*_args):
            teacher = teacher_by_label.get(teacher_choice.get())
            selected = self.db.teacher_preferred_rest_days().get(teacher.id, set()) if teacher else set()
            for index, variable in enumerate(day_vars):
                variable.set(index in selected)

        def save_teacher_days():
            teacher = teacher_by_label.get(teacher_choice.get())
            if not teacher:
                return messagebox.showwarning("لا يوجد مدرس", "أضف المدرسين أولاً.", parent=dialog)
            selected = {index for index, variable in enumerate(day_vars) if variable.get()}
            if len(selected) != 2:
                return messagebox.showwarning("اختيار ناقص", "اختر يومي راحة بالضبط.", parent=dialog)
            self.db.set_teacher_preferred_rest_days(teacher.id, selected)
            self.db.clear_generated(); self.show_result([])
            messagebox.showinfo("تم الحفظ", f"تم حفظ يومي الراحة المفضّلين لـ {teacher.name}.", parent=dialog)

        teacher_combo.bind("<<ComboboxSelected>>", load_teacher_days)
        load_teacher_days()
        ttk.Button(
            availability, text="حفظ يومي الراحة المفضّلين", style="Primary.TButton", command=save_teacher_days,
        ).pack(anchor="e")

        def parse_time(value):
            parts = value.strip().split(":")
            if len(parts) != 2:
                raise ValueError
            hour, minute = map(int, parts)
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return hour * 60 + minute

        def save_policy():
            data = {}
            try:
                for key, _label, kind in fields:
                    data[key] = int(variables[key].get()) if kind == "int" else variables[key].get().strip()
                    if kind == "time":
                        parse_time(data[key])
                if data["available_rooms"] < 1 or data["emergency_room_count"] < 0:
                    raise ValueError
                if not 1 <= data["preferred_teacher_working_days"] <= data["max_teacher_working_days"] <= 6:
                    raise ValueError
                if parse_time(data["school_start"]) >= parse_time(data["school_end"]):
                    raise ValueError
                if parse_time(data["morning_start"]) >= parse_time(data["morning_end"]):
                    raise ValueError
                if parse_time(data["afternoon_start"]) >= parse_time(data["afternoon_end"]):
                    raise ValueError
                if data["teacher_daily_max_minutes"] < 60 or data["teacher_transition_minutes"] < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return messagebox.showerror(
                    "قيم غير صالحة", "راجع الأعداد والتوقيت بصيغة HH:MM وتأكد أن البداية قبل النهاية.", parent=dialog,
                )
            data["saturday_afternoon_free"] = saturday_free.get()
            data["emergency_room_available_all_saturday"] = emergency_saturday.get()
            self.db.save_schedule_policy(data)
            self.db.clear_generated(); self.show_result([])
            dialog.destroy()
            messagebox.showinfo("تم الحفظ", "تم حفظ قيود الجدولة. الإسناد اليدوي بقي محفوظاً.")

        footer = ttk.Frame(outer); footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="حفظ الإعدادات", style="Success.TButton", command=save_policy).pack(side="right")
        ttk.Button(footer, text="إغلاق", style="Outline.TButton", command=dialog.destroy).pack(side="left")

    def open_manual_assignments(self):
        classes = self.db.classes(); teachers = self.db.teachers()
        if not classes or not teachers:
            return messagebox.showwarning("بيانات ناقصة", "أضف الأقسام والمدرسين أولاً.")
        class_by_label = {f"{item.name}  •  {item.id}": item for item in classes}
        teacher_by_label = {f"{item.name}  •  {item.id}": item for item in teachers}
        assignments = {
            (item.class_id, item.subject): item
            for item in self.db.fixed_assignments()
        }

        dialog = tk.Toplevel(self)
        dialog.title("الإسناد اليدوي للأقسام")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 1040, 720, 900, 620)
        outer = ttk.Frame(dialog, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="الإسناد اليدوي", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(
            outer, text="اختر القسم، ثم المادة، ثم المعلّم. النظام لن يغيّر هذا الإسناد أثناء توليد التوقيت.",
            style="PageSubtle.TLabel",
        ).pack(anchor="e", pady=(2, 12))
        top = ttk.Frame(outer); top.pack(fill="x")
        class_choice = tk.StringVar(value=next(iter(class_by_label)))
        ttk.Label(top, text="القسم", style="Card.TLabel").pack(side="right", padx=(8, 0))
        class_combo = ttk.Combobox(
            top, textvariable=class_choice, values=list(class_by_label), state="readonly",
            justify="right", style="Large.TCombobox", width=30,
        )
        class_combo.pack(side="right")
        summary = ttk.Label(top, text="", style="Badge.TLabel")
        summary.pack(side="left")

        card, host = self._card(outer, 0); card.pack(fill="both", expand=True, pady=(12, 0))
        tree = ttk.Treeview(host, columns=("status", "teacher", "hours", "subject"), show="headings", selectmode="browse")
        for column, label, width, anchor in (
            ("status", "الحالة", 120, "center"), ("teacher", "المعلّم المسند", 300, "e"),
            ("hours", "الحجم", 110, "center"), ("subject", "المادة", 260, "e"),
        ):
            tree.heading(column, text=label); tree.column(column, width=width, anchor=anchor)
        tree.tag_configure("done", background="#EEF9F2", foreground="#0E6B3E")
        tree.tag_configure("missing", background="#FFF0F1", foreground="#A61B29")
        self._attach_tree_scrollbars(host, tree, padding=10)
        row_keys = {}

        editor = ttk.Frame(outer); editor.pack(fill="x", pady=(12, 0))
        teacher_choice = tk.StringVar()
        teacher_combo = ttk.Combobox(
            editor, textvariable=teacher_choice, state="readonly", justify="right",
            style="Large.TCombobox", width=42,
        )
        teacher_combo.pack(side="right")

        def total_required():
            return sum(len(self.rules.subjects(item.grade)) for item in classes)

        def refresh_rows(*_args):
            tree.delete(*tree.get_children()); row_keys.clear()
            school_class = class_by_label[class_choice.get()]
            teacher_names = {item.id: item.name for item in teachers}
            for subject, minutes in self.rules.subjects(school_class.grade).items():
                current = assignments.get((school_class.id, subject))
                row = tree.insert(
                    "", "end",
                    values=(
                        "مكتمل" if current else "ينقص معلّم",
                        teacher_names.get(current.teacher_id, "—") if current else "—",
                        self._format_minutes(minutes), subject,
                    ),
                    tags=("done" if current else "missing",),
                )
                row_keys[row] = (school_class.id, subject, minutes)
            summary.configure(text=f"{len(assignments)} / {total_required()} إسناد")
            children = tree.get_children()
            if children:
                tree.selection_set(children[0]); tree.focus(children[0]); load_teacher_choices()

        def load_teacher_choices(*_args):
            selected = tree.selection()
            if not selected:
                teacher_combo.configure(values=[]); teacher_choice.set(""); return
            class_id, subject, _minutes = row_keys[selected[0]]
            school_class = next(item for item in classes if item.id == class_id)
            solver = self._solver()
            eligible = []
            for teacher_label, teacher in teacher_by_label.items():
                if subject not in teacher.subjects or (teacher.class_ids and class_id not in teacher.class_ids):
                    continue
                if (subject == "الفرنسية" and school_class.grade == 2
                        and self.rules.assignment_rule("french_year2_specialist_required", True)
                        and not solver._has_subject_expertise(teacher, subject)):
                    continue
                if (subject == "التربية البدنية"
                        and self.rules.assignment_rule("physical_education_specialist_required", True)
                        and not solver._has_subject_expertise(teacher, subject)):
                    continue
                eligible.append(teacher_label)
            teacher_combo.configure(values=eligible)
            current = assignments.get((class_id, subject))
            current_label = next((label for label, item in teacher_by_label.items() if current and item.id == current.teacher_id), "")
            teacher_choice.set(current_label if current_label in eligible else (eligible[0] if eligible else ""))

        def save_assignment():
            selected = tree.selection(); teacher = teacher_by_label.get(teacher_choice.get())
            if not selected or not teacher:
                return messagebox.showwarning("اختيار ناقص", "اختر المادة ومعلّماً مؤهلاً لها.", parent=dialog)
            class_id, subject, minutes = row_keys[selected[0]]
            current = assignments.get((class_id, subject))
            load = sum(
                item.weekly_minutes for key, item in assignments.items()
                if item.teacher_id == teacher.id and key != (class_id, subject)
            )
            if load + minutes > teacher.max_weekly_minutes:
                return messagebox.showerror(
                    "تجاوز الحجم", f"هذا الإسناد يتجاوز الحجم الأسبوعي للمدرس {teacher.name}.", parent=dialog,
                )
            assignments[(class_id, subject)] = Assignment(class_id, teacher.id, subject, minutes)
            self.db.save_fixed_assignments(list(assignments.values()))
            self.db.clear_generated(); self.show_result([]); refresh_rows()

        def remove_assignment():
            selected = tree.selection()
            if not selected:
                return
            class_id, subject, _minutes = row_keys[selected[0]]
            assignments.pop((class_id, subject), None)
            self.db.save_fixed_assignments(list(assignments.values()))
            self.db.clear_generated(); self.show_result([]); refresh_rows()

        tree.bind("<<TreeviewSelect>>", load_teacher_choices)
        class_combo.bind("<<ComboboxSelected>>", refresh_rows)
        ttk.Button(editor, text="حفظ إسناد المادة", style="Primary.TButton", command=save_assignment).pack(side="right", padx=8)
        ttk.Button(editor, text="إلغاء هذا الإسناد", style="Danger.TButton", command=remove_assignment).pack(side="left")
        ttk.Button(editor, text="إغلاق", style="Outline.TButton", command=dialog.destroy).pack(side="left", padx=8)
        refresh_rows()

    def generate(self):
        if not self._require_licence():
            return
        if getattr(self, "generation_running", False):
            return
        self.generation_running = True
        self.generate_button.configure(state="disabled", text="جارٍ التوليد…")
        self.generation_progress.pack(side="left", padx=14)
        self.generation_progress.start(10)
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            classes = self.db.classes()
            teachers = self.db.teachers()
            fixed = self.db.fixed_assignments()
            setup_errors = self._validate_setup(classes, teachers, fixed)
            if setup_errors:
                messagebox.showerror("الملف غير جاهز للتوليد", "\n\n".join(setup_errors[:8]))
                return
            complementary = self.db.complementary_minutes()
            expected = sum(len(self.rules.subjects(item.grade)) for item in classes)
            if len(fixed) != expected:
                messagebox.showwarning(
                    "الإسناد اليدوي غير مكتمل",
                    f"الإسناد اليدوي غير مكتمل: تم ضبط {len(fixed)} من {expected}. "
                    "أكمل معلّم كل مادة ثم أعد التوليد.",
                )
                return self.open_manual_assignments()
            solver = self._solver()
            result = solver.rebuild(
                classes, teachers, fixed, complementary_minutes=complementary
            )
            self.db.save_assignments(result.assignments); self.db.save_lessons(result.lessons); self.show_result(result.warnings)
            messagebox.showinfo(
                "نجاح",
                "تم تركيب جدول الأوقات آلياً مع المحافظة على الإسناد اليدوي كاملاً.",
            )
        except SolverError as error:
            messagebox.showerror("تعذر التوليد", str(error))
        finally:
            self.generation_progress.stop()
            self.generation_progress.pack_forget()
            self.generation_running = False
            self.generate_button.configure(state="normal", text="توليد الجدول آلياً")
            self.configure(cursor="")

    def _validate_setup(self, classes, teachers, assignments):
        errors = []
        if not classes: errors.append("أضف قسماً واحداً على الأقل.")
        if not teachers: errors.append("أضف مدرساً واحداً على الأقل.")
        rooms = [room for room in self.db.rooms() if room.enabled]
        if not rooms: errors.append("فعّل قاعة واحدة على الأقل وحدد توفرها.")
        elif not any(room.availability for room in rooms): errors.append("القاعات المفعّلة دون أيام أو ساعات متاحة.")
        class_by_id = {item.id: item for item in classes}
        teacher_by_id = {item.id: item for item in teachers}
        seen = set(); loads = defaultdict(int)
        for item in assignments:
            key = (item.class_id, item.subject)
            if key in seen: errors.append("يوجد إسناد مكرر لنفس المادة والقسم.")
            seen.add(key)
            teacher = teacher_by_id.get(item.teacher_id); school_class = class_by_id.get(item.class_id)
            if not teacher or not school_class:
                errors.append("يوجد إسناد مرتبط بمدرس أو قسم محذوف."); continue
            if item.subject not in teacher.subjects:
                errors.append(f"{teacher.name} غير مسموح له بتدريس {item.subject}.")
            if teacher.class_ids and item.class_id not in teacher.class_ids:
                errors.append(f"القسم {school_class.name} غير موجود ضمن الأقسام المسموح بها للمدرس {teacher.name}.")
            loads[teacher.id] += item.weekly_minutes
        for teacher in teachers:
            if loads[teacher.id] > teacher.max_weekly_minutes:
                errors.append(f"إسناد {teacher.name} يتجاوز حجمه الأسبوعي المستهدف.")
        return list(dict.fromkeys(errors))

    def edit_assignment(self, assignment=None):
        if assignment is None:
            selected = self.assignment_tree.selection()
            if not selected:
                return messagebox.showwarning("اختيار الإسناد", "اختر معلّماً من ملخّص الإسناد أو انقر عليه نقراً مزدوجاً.")
            group = getattr(self, "assignment_item_map", {}).get(selected[0], [])
            if not group:
                return messagebox.showwarning("اختيار الإسناد", "لا يوجد إسناد لهذا المدرّس. أعد التوليد ثم حاول مجدداً.")
            if len(group) > 1:
                return self._choose_teacher_assignment(group)
            assignment = group[0]

        all_classes = self.db.classes()
        classes = {item.id: item for item in all_classes}
        teachers = self.db.teachers()
        teacher_by_id = {item.id: item for item in teachers}
        current_assignments = self.db.assignments()
        loads = {teacher.id: 0 for teacher in teachers}
        for item in current_assignments:
            loads[item.teacher_id] = loads.get(item.teacher_id, 0) + item.weekly_minutes
        current_teacher = teacher_by_id[assignment.teacher_id]
        school_class = classes[assignment.class_id]
        solver = self._solver()

        def can_teach(item, teacher):
            if item.subject not in teacher.subjects or (teacher.class_ids and item.class_id not in teacher.class_ids):
                return False
            item_class = classes[item.class_id]
            if (item.subject == "الفرنسية" and item_class.grade == 2
                    and self.rules.assignment_rule("french_year2_specialist_required", True)):
                return solver._has_subject_expertise(teacher, item.subject)
            return True

        def revised_assignments(target_id, swapped=None):
            revised = []
            for item in current_assignments:
                teacher_id = item.teacher_id
                if (item.class_id, item.subject) == (assignment.class_id, assignment.subject):
                    teacher_id = target_id
                elif swapped and (item.class_id, item.subject) == (swapped.class_id, swapped.subject):
                    teacher_id = current_teacher.id
                revised.append(Assignment(item.class_id, teacher_id, item.subject, item.weekly_minutes))
            return revised

        # Validate every displayed proposal now.  The director never sees an option
        # that is known to exceed a workload or produce a conflicting timetable.
        self.configure(cursor="watch")
        self.update_idletasks()
        candidate_actions = []
        try:
            for target in teachers:
                if target.id == current_teacher.id or not can_teach(assignment, target):
                    continue
                direct_load = loads[target.id] + assignment.weekly_minutes
                if direct_load <= target.max_weekly_minutes:
                    try:
                        result = self._solver().rebuild(
                            all_classes, teachers, revised_assignments(target.id), optimize=False,
                            complementary_minutes=self.db.complementary_minutes(),
                        )
                    except SolverError:
                        pass
                    else:
                        candidate_actions.append({
                            "teacher": target,
                            "operation": "نقل مباشر",
                            "before": loads[target.id],
                            "after": direct_load,
                            "status": "جاهز",
                            "result": result,
                            "assignments": result.assignments,
                            "detail": f"نقل {assignment.subject} – {school_class.name} من {current_teacher.name} إلى {target.name}.",
                        })

                # If the receiving teacher is full, offer practical exchanges too.
                # Two feasible exchanges per teacher keep the decision list concise.
                feasible_swaps = 0
                swap_pool = sorted(
                    (item for item in current_assignments if item.teacher_id == target.id
                     and (item.class_id, item.subject) != (assignment.class_id, assignment.subject)),
                    key=lambda item: (abs(item.weekly_minutes - assignment.weekly_minutes), item.weekly_minutes),
                )
                for swapped in swap_pool:
                    if feasible_swaps >= 2 or not can_teach(swapped, current_teacher):
                        continue
                    target_after = loads[target.id] - swapped.weekly_minutes + assignment.weekly_minutes
                    current_after = loads[current_teacher.id] - assignment.weekly_minutes + swapped.weekly_minutes
                    if target_after > target.max_weekly_minutes or current_after > current_teacher.max_weekly_minutes:
                        continue
                    try:
                        result = self._solver().rebuild(
                            all_classes, teachers, revised_assignments(target.id, swapped), optimize=False,
                            complementary_minutes=self.db.complementary_minutes(),
                        )
                    except SolverError:
                        continue
                    swapped_class = classes[swapped.class_id]
                    candidate_actions.append({
                        "teacher": target,
                        "operation": f"تبديل مع {swapped.subject} – {swapped_class.name}",
                        "before": loads[target.id],
                        "after": target_after,
                        "status": "تبديل آمن",
                        "result": result,
                        "assignments": result.assignments,
                        "detail": (
                            f"إسناد {assignment.subject} – {school_class.name} إلى {target.name}، "
                            f"وإسناد {swapped.subject} – {swapped_class.name} إلى {current_teacher.name}."
                        ),
                    })
                    feasible_swaps += 1
        finally:
            self.configure(cursor="")

        if not candidate_actions:
            return messagebox.showerror(
                "لا يوجد تعديل آمن",
                "جرّب النظام النقل المباشر والتبديل بين المدرسين، ولم يجد حلاً يحترم التأهيل والحجم والتوقيت.\n"
                "يمكنك تعديل مواد التأهيل أو الحجم الأسبوعي للمدرس ثم إعادة المحاولة.",
            )

        dialog = tk.Toplevel(self)
        dialog.title("تعديل الإسناد يدوياً")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 1040, 660, 900, 570)
        outer = ttk.Frame(dialog, padding=18); outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="تعديل الإسناد يدوياً", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(
            outer,
            text=(f"{school_class.name}  •  {assignment.subject}  •  {self._format_minutes(assignment.weekly_minutes)}"
                  f"  •  المدرّس الحالي: {current_teacher.name}"),
            style="Badge.TLabel",
        ).pack(anchor="e", pady=(8, 12))
        ttk.Label(
            outer,
            text="اختر حلاً جاهزاً. النقل المباشر ينقل المادة فقط، والتبديل يبادل إسنادين للمحافظة على 18 ساعة.",
            style="PageSubtle.TLabel",
        ).pack(anchor="e", pady=(0, 12))

        table_card, table_host = self._card(outer, 0); table_card.pack(fill="both", expand=True)
        tree = ttk.Treeview(
            table_host, columns=("status", "after", "before", "operation", "teacher"),
            show="headings", selectmode="browse",
        )
        for column, label, width, anchor in (
            ("status", "الحالة", 120, "center"),
            ("after", "الحجم بعد التعديل", 145, "center"),
            ("before", "الحجم الحالي", 130, "center"),
            ("operation", "العملية المقترحة", 320, "e"),
            ("teacher", "المدرّس البديل", 210, "e"),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, minwidth=95, anchor=anchor)
        action_map = {}
        for index, action in enumerate(candidate_actions):
            target = action["teacher"]
            row = tree.insert(
                "", "end",
                values=(
                    action["status"], self._format_minutes(action["after"]),
                    f"{self._format_minutes(action['before'])} / {self._format_minutes(target.max_weekly_minutes)}",
                    action["operation"], target.name,
                ),
                tags=("swap" if action["status"] == "تبديل آمن" else "direct",),
            )
            action_map[row] = action
            if index == 0:
                tree.selection_set(row); tree.focus(row)
        tree.tag_configure("direct", background="#EAF8F0", foreground="#0B6539")
        tree.tag_configure("swap", background="#FFF7E2", foreground="#775300")
        self._attach_tree_scrollbars(table_host, tree, padding=10)

        detail = tk.StringVar(value=candidate_actions[0]["detail"])
        detail_box = tk.Label(
            outer, textvariable=detail, bg="#E7F1FF", fg=NAVY, font=(FONT, 13, "bold"),
            justify="right", anchor="e", padx=14, pady=10, wraplength=950,
        )
        detail_box.pack(fill="x", pady=(12, 0))

        def refresh_detail(*_args):
            selected = tree.selection()
            if selected:
                detail.set(action_map[selected[0]]["detail"])
        tree.bind("<<TreeviewSelect>>", refresh_detail)

        def save_manual_assignment():
            selected = tree.selection()
            if not selected:
                return messagebox.showwarning("اختيار مطلوب", "اختر نقلاً أو تبديلاً من الجدول.", parent=dialog)
            action = action_map[selected[0]]
            self.configure(cursor="watch")
            dialog.configure(cursor="watch")
            dialog.update_idletasks()
            try:
                result = self._solver().rebuild(
                    all_classes, teachers, action["assignments"], optimize=True,
                    complementary_minutes=self.db.complementary_minutes(),
                )
            except SolverError as error:
                self.configure(cursor="")
                dialog.configure(cursor="")
                return messagebox.showerror("تعذر اعتماد التعديل", str(error), parent=dialog)
            self.configure(cursor="")
            if self.db.fixed_assignments():
                self.db.save_fixed_assignments(result.assignments)
            self.db.save_assignments(result.assignments)
            self.db.save_lessons(result.lessons)
            dialog.destroy()
            self.show_result(result.warnings)
            messagebox.showinfo("تم التعديل", "تم اعتماد التعديل وإعادة تركيب الجدول والتحقق من التعارضات.")

        actions = ttk.Frame(outer); actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="اعتماد التعديل وإعادة الجدولة", style="Success.TButton", command=save_manual_assignment).pack(side="right")
        ttk.Button(actions, text="إلغاء", style="Outline.TButton", command=dialog.destroy).pack(side="left")
        tree.bind("<Double-1>", lambda _event: save_manual_assignment())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def _choose_teacher_assignment(self, assignments):
        classes = {item.id: item for item in self.db.classes()}
        dialog = tk.Toplevel(self)
        dialog.title("تفاصيل إسناد المدرّس")
        dialog.configure(bg=BACKGROUND); dialog.transient(self); dialog.grab_set()
        self._center_dialog(dialog, 820, 560, 720, 480)
        outer = ttk.Frame(dialog, padding=18); outer.pack(fill="both", expand=True)
        teacher = next((item for item in self.db.teachers() if item.id == assignments[0].teacher_id), None)
        ttk.Label(outer, text=teacher.name if teacher else "تفاصيل الإسناد", style="Hero.TLabel").pack(anchor="e")
        ttk.Label(
            outer, text="اختر المادة والقسم المراد تغيير معلّمهما، ثم اضغط تعديل.", style="PageSubtle.TLabel",
        ).pack(anchor="e", pady=(2, 12))
        host_card, host = self._card(outer, 0); host_card.pack(fill="both", expand=True)
        tree = ttk.Treeview(host, columns=("hours", "subject", "class"), show="headings", selectmode="browse")
        for column, label, width in (
            ("hours", "الحجم", 120), ("subject", "المادة", 260), ("class", "القسم", 240),
        ):
            tree.heading(column, text=label); tree.column(column, width=width, anchor="e" if column != "hours" else "center")
        item_map = {}
        for index, item in enumerate(assignments):
            row = tree.insert(
                "", "end", values=(self._format_minutes(item.weekly_minutes), item.subject, classes[item.class_id].name),
                tags=("even" if index % 2 == 0 else "odd",),
            )
            item_map[row] = item
        tree.tag_configure("even", background="#F6F9FC")
        tree.tag_configure("odd", background="#FFFFFF")
        self._attach_tree_scrollbars(host, tree, padding=10)

        def open_selected():
            selected = tree.selection()
            if not selected:
                return messagebox.showwarning("اختيار مطلوب", "اختر إسناداً من القائمة.", parent=dialog)
            chosen = item_map[selected[0]]
            dialog.destroy()
            self.edit_assignment(chosen)

        footer = ttk.Frame(outer); footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="تعديل الإسناد المحدد", style="Primary.TButton", command=open_selected).pack(side="right")
        ttk.Button(footer, text="إغلاق", style="Outline.TButton", command=dialog.destroy).pack(side="left")
        tree.bind("<Double-1>", lambda _event: open_selected())
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def _refresh_assignment_rows(self):
        if not hasattr(self, "assignment_tree"):
            return
        self.assignment_tree.delete(*self.assignment_tree.get_children())
        self.assignment_item_map = {}
        query = self.assignment_filter.get().strip().casefold() if hasattr(self, "assignment_filter") else ""
        classes = {item.id: item for item in self.db.classes()}
        assignments = self.db.assignments()
        complementary = self.db.complementary_minutes()
        by_teacher = defaultdict(list)
        for item in assignments:
            by_teacher[item.teacher_id].append(item)
        for teacher in self.db.teachers():
            items = by_teacher.get(teacher.id, [])
            subjects = [item.subject for item in items]
            class_names = [classes[item.class_id].name for item in items if item.class_id in classes]
            haystack = " ".join([teacher.name, teacher.specialty, *subjects, *class_names]).casefold()
            if query and query not in haystack:
                continue
            official = sum(item.weekly_minutes for item in items)
            extra = complementary.get(teacher.id, 0)
            assigned = official + extra
            remaining = max(0, teacher.max_weekly_minutes - assigned)
            if not items:
                status, tag = "غير مسند", "unused"
            elif remaining:
                status, tag = f"ناقص {self._format_minutes(remaining)}", "underload"
            else:
                status, tag = "مكتمل", "balanced"
            if extra:
                subjects.append(f"تكميلية ({self._format_minutes(extra)})")
            row = self.assignment_tree.insert(
                "", "end",
                values=(
                    status, self._format_minutes(teacher.max_weekly_minutes), self._format_minutes(assigned),
                    self._short_list(class_names, 4), self._short_list(subjects, 4),
                    teacher.specialty or "غير محدد", teacher.name,
                ),
                tags=(tag,),
            )
            self.assignment_item_map[row] = items
        self.after_idle(lambda: self.assignment_tree.xview_moveto(1.0))

    def _refresh_lesson_rows(self):
        if not hasattr(self, "lesson_tree"):
            return
        self.lesson_tree.delete(*self.lesson_tree.get_children())
        from .models import DAYS_AR, minute_to_hhmm
        query = self.lesson_filter.get().strip().casefold() if hasattr(self, "lesson_filter") else ""
        selected_day = self.lesson_day_filter.get() if hasattr(self, "lesson_day_filter") else "كل الأيام"
        classes = {item.id: item for item in self.db.classes()}
        teachers = {item.id: item for item in self.db.teachers()}
        visible = 0
        for item in sorted(self.db.lessons(), key=lambda value: (value.day, value.start_minute, classes[value.class_id].name)):
            day_name = DAYS_AR[item.day]
            class_name = classes[item.class_id].name
            teacher_name = teachers[item.teacher_id].name
            haystack = " ".join([day_name, class_name, item.subject, teacher_name]).casefold()
            if selected_day != "كل الأيام" and day_name != selected_day:
                continue
            if query and query not in haystack:
                continue
            self.lesson_tree.insert(
                "", "end",
                values=(
                    day_name,
                    f"{minute_to_hhmm(item.start_minute)} – {minute_to_hhmm(item.start_minute + item.duration)}",
                    class_name, item.subject, teacher_name,
                ),
                tags=("even" if visible % 2 == 0 else "odd",),
            )
            visible += 1
        self.after_idle(lambda: self.lesson_tree.xview_moveto(1.0))

    def _render_audit(self, has_results):
        for child in self.warning_list.winfo_children():
            child.destroy()

        if not has_results:
            empty = tk.Frame(self.warning_list, bg="#F5F9FD", highlightbackground="#DDE7F0", highlightthickness=1)
            empty.pack(fill="x", padx=10, pady=10)
            tk.Label(empty, text="لا توجد نتائج بعد", bg="#F5F9FD", fg=NAVY, font=(FONT, 19, "bold"), anchor="e").pack(fill="x", padx=18, pady=(16, 5))
            tk.Label(
                empty,
                text="أضف الأقسام والمدرّسين وحدد اختصاصاتهم، ثم اضغط «توليد الجدول آلياً».",
                bg="#F5F9FD", fg=MUTED, font=(FONT, 14), anchor="e", justify="right",
            ).pack(fill="x", padx=18, pady=(0, 16))
            return

        errors = sum(warning.startswith("خطأ:") for warning in self.last_warnings)
        suggestions = len(self.last_warnings) - errors
        head = tk.Frame(self.warning_list, bg="#F5F9FD", highlightbackground="#DDE7F0", highlightthickness=1)
        head.pack(fill="x", padx=10, pady=(10, 5))
        tk.Label(
            head, text="نتيجة التدقيق", bg="#F5F9FD", fg=NAVY, font=(FONT, 18, "bold"), anchor="e",
        ).pack(side="right", padx=16, pady=13)
        tk.Label(
            head, text=f"{errors} أخطاء", bg="#FFE5E8" if errors else "#DDF5E8", fg=DANGER if errors else SUCCESS,
            font=(FONT, 13, "bold"), padx=12, pady=6,
        ).pack(side="right", padx=5)
        tk.Label(
            head, text=f"{suggestions} تنبيهات واقتراحات", bg="#FFF3CD", fg="#765700",
            font=(FONT, 13, "bold"), padx=12, pady=6,
        ).pack(side="right", padx=5)

        if not self.last_warnings:
            ok = tk.Frame(self.warning_list, bg="#EEF9F2", highlightbackground="#B9DFC9", highlightthickness=1)
            ok.pack(fill="x", padx=10, pady=6)
            tk.Label(
                ok, text="✓ لم يسجل محرك التحقق أي مخالفة للقواعد المفعّلة.",
                bg="#EEF9F2", fg=SUCCESS, font=(FONT, 15, "bold"), anchor="e", justify="right",
            ).pack(fill="x", padx=18, pady=16)
            return

        for index, warning in enumerate(self.last_warnings, 1):
            is_error = warning.startswith("خطأ:")
            background = "#FFF4F5" if is_error else "#FFFBED"
            border = "#F0B9BF" if is_error else "#E8D28A"
            foreground = "#A61B29" if is_error else "#765700"
            label = "خطأ" if is_error else "تنبيه"
            message = warning.split(":", 1)[1].strip() if ":" in warning else warning
            card = tk.Frame(self.warning_list, bg=background, highlightbackground=border, highlightthickness=1)
            card.pack(fill="x", padx=10, pady=5)
            badge = tk.Label(card, text=f"{label} {index}", bg=foreground, fg="#FFFFFF", font=(FONT, 12, "bold"), padx=11, pady=5)
            badge.pack(side="right", anchor="n", padx=(10, 14), pady=13)
            tk.Label(
                card, text=message, bg=background, fg=foreground, font=(FONT, 14, "bold"),
                anchor="e", justify="right", wraplength=790, padx=8, pady=12,
            ).pack(side="right", fill="x", expand=True)

    def show_result(self, warnings=None):
        if warnings is not None:
            self.last_warnings = list(warnings)
        self._refresh_assignment_rows()
        self._refresh_lesson_rows()
        self.refresh_teachers()
        assignments, lessons = self.db.assignments(), self.db.lessons()
        if hasattr(self, "assignment_page"):
            self.result_tabs.tab(self.assignment_page, text=f"الإسناد حسب المدرّس ({len(self.db.teachers())})")
            self.result_tabs.tab(self.schedule_page, text=f"جداول الحصص ({len(lessons)})")
            self.result_tabs.tab(self.warning_page, text=f"التحقق والتنبيهات ({len(self.last_warnings)})")
        if not assignments and not lessons:
            self.generation_summary.configure(text="لم يتم التوليد بعد")
            self._render_audit(False)
            return
        total_assigned = sum(item.weekly_minutes for item in assignments) + sum(self.db.complementary_minutes().values())
        total_capacity = sum(item.max_weekly_minutes for item in self.db.teachers())
        self.generation_summary.configure(
            text=f"{len(assignments)} إسناد  •  {len(lessons)} حصة  •  "
                 f"{self._format_minutes(total_assigned)} من {self._format_minutes(total_capacity)}"
        )
        self._render_audit(True)
        if self.last_warnings:
            self.result_tabs.select(self.warning_page)

    def export_pdf(self):
        if not self._require_licence():
            return
        if not self.db.lessons(): return messagebox.showwarning("تنبيه", "ولّد الجدول أولاً.")
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="التنظيم_البيداغوجي_2026_2027.pdf")
        if not path: return
        try:
            PDFExporter(self.root_dir / "templates").export(path, self.db.get_school(), self.db.classes(), self.db.teachers(),
                                                               self.db.assignments(), self.db.lessons(), self.rules, self.last_warnings)
            messagebox.showinfo("تم", f"تم إنشاء PDF:\n{path}")
        except Exception as error:
            messagebox.showerror("تعذر إنشاء PDF", f"لم يتم إنشاء الملف.\n{error}")

    def show_teacher_timetable(self):
        lessons = self.db.lessons()
        if not lessons:
            return messagebox.showwarning("تنبيه", "ولّد الجدول أولاً.")
        teachers = [teacher for teacher in self.db.teachers() if any(item.teacher_id == teacher.id for item in lessons)]
        if not teachers:
            return messagebox.showwarning("تنبيه", "لا توجد جداول مدرسين لعرضها.")
        classes = {item.id: item for item in self.db.classes()}
        teacher_by_name = {teacher.name: teacher for teacher in teachers}

        dialog = tk.Toplevel(self)
        dialog.title("جداول أوقات المدرسين")
        dialog.configure(bg=BACKGROUND)
        dialog.transient(self)
        dialog.grab_set()
        self._center_dialog(dialog, 1240, 780, 1040, 680)

        hero = tk.Frame(dialog, bg=CARD, height=78, highlightbackground=BORDER, highlightthickness=1)
        hero.pack(fill="x")
        hero.pack_propagate(False)
        tk.Frame(hero, bg=ACCENT, height=4).pack(fill="x")
        title_box = tk.Frame(hero, bg=CARD)
        title_box.pack(side="right", padx=26, pady=8)
        tk.Label(title_box, text="جدول أوقات المدرّس", bg=CARD, fg=NAVY, font=(FONT, 23, "bold")).pack(anchor="e")
        tk.Label(title_box, text="عرض أسبوعي واضح مع الحجم وأيام العمل والراحة", bg=CARD, fg=MUTED, font=(FONT, 12)).pack(anchor="e")
        ttk.Button(hero, text="إغلاق", style="Outline.TButton", command=dialog.destroy).pack(side="left", padx=24, pady=13)
        ttk.Button(
            hero, text="طباعة الجدول", style="Primary.TButton", command=lambda: print_current()
        ).pack(side="left", padx=(0, 8), pady=13)

        outer = ttk.Frame(dialog, padding=(20, 14, 20, 18))
        outer.pack(fill="both", expand=True)
        control_card, controls = self._card(outer, 13)
        control_card.pack(fill="x", pady=(0, 12))
        selected_name = tk.StringVar(value=teachers[0].name)
        ttk.Label(controls, text="المدرّس", style="Selector.TLabel").pack(side="right", padx=(14, 0))
        selector = ttk.Combobox(
            controls, textvariable=selected_name, values=[teacher.name for teacher in teachers],
            state="readonly", justify="right", width=30, style="Large.TCombobox",
        )
        selector.pack(side="right")
        summary = tk.Frame(controls, bg=CARD)
        summary.pack(side="left")

        grid_card = tk.Frame(outer, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        grid_card.pack(fill="both", expand=True)
        grid_scroll = ttk.Scrollbar(grid_card, orient="vertical")
        grid_scroll.pack(side="left", fill="y")
        grid_canvas = tk.Canvas(
            grid_card, bg=CARD, highlightthickness=0,
            yscrollcommand=grid_scroll.set,
        )
        grid_canvas.pack(side="right", fill="both", expand=True)
        grid_scroll.configure(command=grid_canvas.yview)
        grid = tk.Frame(grid_canvas, bg=BORDER)
        grid_window = grid_canvas.create_window((0, 0), window=grid, anchor="nw")
        grid.bind(
            "<Configure>",
            lambda _event: grid_canvas.configure(scrollregion=grid_canvas.bbox("all")),
        )
        grid_canvas.bind(
            "<Configure>",
            lambda event: grid_canvas.itemconfigure(grid_window, width=event.width),
        )
        grid_canvas.bind(
            "<MouseWheel>",
            lambda event: grid_canvas.yview_scroll(int(-event.delta / 120), "units"),
        )
        for column in range(6):
            grid.columnconfigure(column, weight=1, uniform="schedule")
        for row in range(7):
            grid.rowconfigure(row, weight=0, minsize=54 if row == 0 else 76)

        slots = [
            ("15:00 — 17:00", 900, 1020),
            ("13:00 — 15:00", 780, 900),
            ("12:00 — 13:00", 720, 780),
            ("10:00 — 12:00", 600, 720),
            ("08:00 — 10:00", 480, 600),
        ]

        def lesson_text(day_lessons, start, end):
            entries = []
            matching = sorted(
                (
                    item for item in day_lessons
                    if item.start_minute < end and item.start_minute + item.duration > start
                ),
                key=lambda item: item.start_minute,
            )
            for item in matching:
                item_end = item.start_minute + item.duration
                from .models import minute_to_hhmm
                class_name = classes[item.class_id].name.replace("السنة ", "", 1)
                entries.append(
                    f"{minute_to_hhmm(item.start_minute)}–{minute_to_hhmm(item_end)}  •  {class_name}\n"
                    f"{item.subject}"
                )
            return "\n".join(entries)

        def slot_entry_count(day_lessons, start, end):
            return sum(
                item.start_minute < end and item.start_minute + item.duration > start
                for item in day_lessons
            )

        def render(*_args):
            for child in grid.winfo_children():
                child.destroy()
            for child in summary.winfo_children():
                child.destroy()
            teacher = teacher_by_name[selected_name.get()]
            teacher_lessons = [item for item in lessons if item.teacher_id == teacher.id]
            daily_totals = {
                day: sum(item.duration for item in teacher_lessons if item.day == day)
                for day in range(6)
            }
            active = [day for day, minutes in daily_totals.items() if minutes]
            rest = ["الأحد", *[self._day_name(day) for day in range(6) if not daily_totals[day]]]
            total = sum(daily_totals.values())
            metrics = [
                (teacher.specialty or "اختصاص غير محدد", SOFT_BLUE, NAVY),
                (f"المُسند {self._format_minutes(total)} / المستهدف {self._format_minutes(teacher.max_weekly_minutes)}", "#FFF3CD" if total < teacher.max_weekly_minutes else "#DDF5E8", "#765700" if total < teacher.max_weekly_minutes else "#0E6B3E"),
                (f"{len(active)} أيام عمل", SOFT_BLUE, NAVY),
                (f"الراحة: {'، '.join(rest)}", "#DDF5E8", "#0E6B3E"),
            ]
            for text, background, foreground in metrics:
                tk.Label(summary, text=text, bg=background, fg=foreground, font=(FONT, 12, "bold"), padx=11, pady=7).pack(side="right", padx=4)
            headers = [label for label, _start, _end in slots] + ["اليوم"]
            for column, label in enumerate(headers):
                tk.Label(
                    grid, text=label, bg=NAVY if column == 5 else ACCENT, fg="#FFFFFF", font=(FONT, 14, "bold"),
                    relief="flat", bd=0, padx=6, pady=9,
                ).grid(row=0, column=column, sticky="nsew", padx=(0, 1), pady=(0, 1))
            for day in range(6):
                row = day + 1
                day_lessons = [item for item in teacher_lessons if item.day == day]
                is_rest = not day_lessons
                busiest_slot = max(
                    (slot_entry_count(day_lessons, start, end) for _label, start, end in slots),
                    default=0,
                )
                # Each lesson uses two readable lines (time/class then subject).
                # Dense days grow instead of clipping; the table itself scrolls
                # when several days require extra height.
                grid.rowconfigure(row, minsize=max(76, 12 + busiest_slot * 34))
                for column, (_label, start, end) in enumerate(slots):
                    if is_rest:
                        text = "يوم راحة" if column == 2 else ""
                        background = "#EDF8F1"
                    else:
                        text = lesson_text(day_lessons, start, end)
                        if not text and start == 720:
                            text = "راحة منتصف النهار"
                            background = "#F2F5F7"
                        else:
                            background = "#FFFFFF" if row % 2 else "#F7FAFC"
                    tk.Label(
                        grid, text=text, bg=background, fg=TEXT if not is_rest else "#287A4E",
                        font=(FONT, 11, "bold" if text else "normal"), justify="center", wraplength=185,
                        relief="flat", bd=0, padx=6, pady=6,
                    ).grid(row=row, column=column, sticky="nsew", padx=(0, 1), pady=(0, 1))
                tk.Label(
                    grid, text=self._day_name(day), bg=SOFT_BLUE if not is_rest else "#DDF5E8", fg=NAVY,
                    font=(FONT, 15, "bold"), relief="flat", bd=0, padx=7, pady=8,
                ).grid(row=row, column=5, sticky="nsew", padx=(0, 1), pady=(0, 1))
            grid.update_idletasks()
            grid_canvas.configure(scrollregion=grid_canvas.bbox("all"))
            grid_canvas.yview_moveto(0)

        def print_current():
            teacher = teacher_by_name[selected_name.get()]
            safe_name = "_".join(teacher.name.split())
            path = filedialog.asksaveasfilename(
                parent=dialog,
                title="حفظ جدول المدرّس للطباعة",
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile=f"جدول_{safe_name}.pdf",
            )
            if not path:
                return
            try:
                PDFExporter(self.root_dir / "templates").export_teacher_schedule(
                    path, self.db.get_school(), teacher, self.db.classes(), lessons, self.rules
                )
            except Exception as error:
                return messagebox.showerror(
                    "تعذر تجهيز الطباعة", f"لم يتم إنشاء ملف الطباعة.\n{error}", parent=dialog
                )
            if messagebox.askyesno(
                "الجدول جاهز",
                f"تم إنشاء جدول {teacher.name} بصيغة PDF.\n\nهل تريد فتحه الآن للطباعة؟",
                parent=dialog,
            ):
                try:
                    os.startfile(path)
                except OSError:
                    messagebox.showinfo("مكان الملف", f"الملف محفوظ هنا:\n{path}", parent=dialog)

        selector.bind("<<ComboboxSelected>>", render)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        render()

    @staticmethod
    def _day_name(day):
        from .models import DAYS_AR
        return DAYS_AR[day]

    def refresh_school(self):
        school = self.db.get_school()
        for key, value in self.school_vars.items(): value.set(getattr(school, key))

    def refresh_classes(self):
        classes = self.db.classes()
        if hasattr(self, "grade_section_hosts"):
            for grade, host in self.grade_section_hosts.items():
                for child in host.winfo_children():
                    child.destroy()
                grade_classes = [item for item in classes if item.grade == grade]
                self.grade_count_labels[grade].configure(
                    text=f"{len(grade_classes)} قسم مضاف" if grade_classes else "لا توجد شعبة مضافة بعد"
                )
                if not grade_classes:
                    tk.Label(host, text="—", bg=CARD, fg="#A6B4C0", font=(FONT, 15)).grid(
                        row=0, column=0, columnspan=4, sticky="e"
                    )
                    continue
                prefix = self.rules.grade(grade)["name"] + " "
                for index, item in enumerate(grade_classes):
                    letter = item.name.removeprefix(prefix)
                    cell = tk.Frame(host, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
                    cell.grid(row=index // 2, column=1 - (index % 2), sticky="ew", padx=3, pady=3)
                    if item.shift == "morning":
                        shift_text, chip_bg, chip_fg = "صباحية", "#FFF7E3", "#8A6100"
                    elif item.shift == "afternoon":
                        shift_text, chip_bg, chip_fg = "مسائية", SOFT_BLUE, ACCENT_HOVER
                    else:
                        shift_text, chip_bg, chip_fg = "حدّد الفترة", "#FFE5E8", DANGER
                    tk.Button(
                        cell, text=f"{letter}  •  {shift_text}",
                        command=lambda class_id=item.id, name=item.name, shift=item.shift: self.edit_class_shift(class_id, name, shift),
                        bg=chip_bg, fg=chip_fg, activebackground=chip_bg, activeforeground=chip_fg,
                        relief="flat", bd=0, padx=7, pady=5, font=(FONT, 13, "bold"), cursor="hand2", anchor="e",
                    ).pack(side="right", fill="x", expand=True)
                    tk.Button(
                        cell, text="×", command=lambda class_id=item.id, name=item.name: self.remove_class(class_id, name),
                        bg="#FFF4F5", fg=DANGER, activebackground="#FFE5E8", activeforeground=DANGER,
                        relief="flat", bd=0, padx=8, pady=5, font=(FONT, 13, "bold"), cursor="hand2",
                    ).pack(side="left")
        if hasattr(self, "class_summary"):
            levels = len({item.grade for item in classes})
            morning = sum(item.shift == "morning" for item in classes)
            afternoon = sum(item.shift == "afternoon" for item in classes)
            missing = sum(not item.shift_window for item in classes)
            missing_text = f"  •  {missing} دون فترة" if missing else ""
            self.class_summary.configure(
                text=f"{len(classes)} قسم  •  {levels} مستويات  •  {morning} صباحي  •  {afternoon} مسائي{missing_text}"
            )

    def refresh_teachers(self):
        self.teachers_tree.delete(*self.teachers_tree.get_children())
        self.teacher_item_map = {}
        query = self.teacher_search.get().strip().casefold() if hasattr(self, "teacher_search") else ""
        all_teachers = self.db.teachers()
        class_by_id = {item.id: item for item in self.db.classes()}
        manual_assignments = self.db.fixed_assignments()
        assigned_minutes = defaultdict(int)
        for assignment in (manual_assignments or self.db.assignments()):
            assigned_minutes[assignment.teacher_id] += assignment.weekly_minutes
        for teacher_id, minutes in self.db.complementary_minutes().items():
            assigned_minutes[teacher_id] += minutes
        visible_index = 0
        for item in all_teachers:
            teacher_classes = [class_by_id[class_id].name for class_id in item.class_ids if class_id in class_by_id]
            haystack = " ".join([item.name, *item.subjects, *teacher_classes]).casefold()
            if query and query not in haystack:
                continue
            current = assigned_minutes.get(item.id, 0)
            remaining = max(0, item.max_weekly_minutes - current)
            status = "غير مسند" if current == 0 else ("ناقص" if remaining else "مكتمل")
            item_id = self.teachers_tree.insert(
                "", "end",
                values=(
                    status,
                    self._format_minutes(item.max_weekly_minutes), self._format_minutes(current),
                    self._short_list(teacher_classes, 3),
                    self._short_list(item.subjects, 2),
                    item.name,
                ),
                tags=("warning" if remaining else ("even" if visible_index % 2 == 0 else "odd"),),
            )
            self.teacher_item_map[item_id] = item.id
            visible_index += 1
        if hasattr(self, "teacher_summary"):
            total_target = sum(item.max_weekly_minutes for item in all_teachers)
            total_assigned = sum(assigned_minutes.values())
            self.teacher_summary.configure(
                text=f"{len(all_teachers)} مدرساً  •  "
                     f"المُسند {self._format_minutes(total_assigned)} من {self._format_minutes(total_target)}"
            )
        # Treeview lays columns left-to-right.  Keep the Arabic identity columns
        # visible first when the window is narrower than the complete table.
        self.after_idle(lambda: self.teachers_tree.xview_moveto(1.0))

    def refresh_rooms(self):
        if not hasattr(self, "rooms_tree"):
            return
        self.rooms_tree.delete(*self.rooms_tree.get_children())
        self.room_item_map = {}
        rooms = self.db.rooms()
        for room in rooms:
            active_days = [DAYS_AR[day] for day in range(6) if room.availability.get(str(day))]
            intervals = [interval for values in room.availability.values() for interval in values]
            if intervals:
                first, last = min(item[0] for item in intervals), max(item[1] for item in intervals)
                hours = f"{first//60:02d}:{first%60:02d} – {last//60:02d}:{last%60:02d}"
            else:
                hours = "—"
            item = self.rooms_tree.insert("", "end", values=(
                "متاحة" if room.enabled else "معطّلة", hours,
                "، ".join(active_days) if active_days else "لا توجد أيام",
                "عادية" if room.kind == "regular" else "احتياطية / تحضيري", room.name,
            ), tags=(("disabled" if not room.enabled else room.kind),))
            self.room_item_map[item] = room.id
        if hasattr(self, "room_summary"):
            enabled = sum(room.enabled for room in rooms)
            emergency = sum(room.enabled and room.kind == "emergency" for room in rooms)
            self.room_summary.configure(text=f"{enabled} قاعة مفعّلة  •  {emergency} احتياطية")

    def refresh_all(self):
        self.refresh_school(); self.refresh_classes(); self.refresh_rooms(); self.refresh_teachers()
        assignments, lessons = self.db.assignments(), self.db.lessons()
        warnings = self._solver().audit(
            self.db.classes(), self.db.teachers(), assignments, lessons,
            self.db.complementary_minutes(),
        ) if assignments or lessons else []
        self.show_result(warnings)
        if hasattr(self, "sidebar_hint"):
            self.sidebar_hint.configure(text=f"{len(self.db.classes())} قسم  •  {len(self.db.teachers())} مدرس\nالمرحلة الأخيرة: التوليد والتحقق")
