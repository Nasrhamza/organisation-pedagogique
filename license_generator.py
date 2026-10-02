"""Private licence issuer. Keep the keys folder private and never distribute it."""
from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app.licensing import create_key_pair, issue_licence, licence_code

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
PRIVATE_KEY = ROOT / "keys" / "license_private.pem"
PUBLIC_KEY = ROOT / "config" / "license_public.pem"


def ensure_keys() -> None:
    if not PRIVATE_KEY.exists() and not PUBLIC_KEY.exists():
        create_key_pair(PRIVATE_KEY, PUBLIC_KEY)
    elif not PRIVATE_KEY.exists() or not PUBLIC_KEY.exists():
        raise RuntimeError("ملفات المفاتيح ناقصة. استرجعها من نسخة احتياطية؛ لا تنشئ زوجاً جديداً.")


class Generator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("مولّد رخص التنظيم البيداغوجي")
        self.resizable(False, False)
        self.customer = tk.StringVar()
        self.device = tk.StringVar()
        self.expires = tk.StringVar()
        self.activation_code = tk.StringVar()
        form = ttk.Frame(self, padding=24)
        form.grid()
        for row, (label, variable, hint) in enumerate((
            ("اسم الحريف/المدرسة", self.customer, ""),
            ("معرّف الجهاز", self.device, "انسخه من شاشة التفعيل"),
            ("تاريخ الانتهاء", self.expires, "اختياري، YYYY-MM-DD"),
        )):
            ttk.Label(form, text=label).grid(row=row, column=1, sticky="e", padx=8, pady=7)
            ttk.Entry(form, textvariable=variable, width=38, justify="right").grid(row=row, column=0, pady=7)
            if hint:
                ttk.Label(form, text=hint, foreground="#666").grid(row=row, column=2, sticky="w", padx=6)
        ttk.Button(form, text="إنشاء كود التفعيل", command=self.generate).grid(row=3, column=0, columnspan=3, pady=(16, 7))
        ttk.Label(form, text="كود التفعيل (انسخه وأرسله للحريف)").grid(row=4, column=1, sticky="e", padx=8, pady=(8, 3))
        self.code_box = tk.Text(form, width=62, height=6, wrap="word", font=("Consolas", 9))
        self.code_box.grid(row=5, column=0, columnspan=3, pady=(0, 8))
        ttk.Button(form, text="نسخ الكود", command=self.copy_code).grid(row=6, column=0, columnspan=3)

    def generate(self):
        if not self.customer.get().strip() or not self.device.get().strip():
            return messagebox.showwarning("بيانات ناقصة", "اسم الحريف ومعرّف الجهاز مطلوبان.")
        try:
            document = issue_licence(PRIVATE_KEY, self.customer.get(), self.device.get(), self.expires.get().strip() or None)
            self.activation_code.set(licence_code(document))
            self.code_box.delete("1.0", "end"); self.code_box.insert("1.0", self.activation_code.get())
            messagebox.showinfo("تم", "تم إنشاء كود التفعيل. انسخه وأرسله للحريف.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("خطأ", str(exc))

    def copy_code(self):
        code = self.activation_code.get()
        if not code:
            return messagebox.showwarning("تنبيه", "أنشئ كود التفعيل أولاً.")
        self.clipboard_clear(); self.clipboard_append(code); self.update()
        messagebox.showinfo("تم", "تم نسخ كود التفعيل.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-keys", action="store_true", help="Create the private/public signing keys once.")
    args = parser.parse_args()
    try:
        ensure_keys()
        if args.init_keys:
            print(f"Keys ready. Keep private key secret: {PRIVATE_KEY}")
        else:
            Generator().mainloop()
    except (OSError, RuntimeError) as exc:
        raise SystemExit(str(exc))
