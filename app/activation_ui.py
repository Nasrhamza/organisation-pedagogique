from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .licensing import LicenceManager, device_id


def request_activation(manager: LicenceManager) -> bool:
    """Block application startup until a valid device-bound code is installed."""
    root = tk.Tk()
    root.title("تفعيل التنظيم البيداغوجي")
    root.geometry("760x540")
    root.minsize(700, 500)
    root.configure(bg="#F2F5F7")
    accepted = {"value": False}
    code = tk.StringVar()
    machine = device_id()

    card = tk.Frame(root, bg="#FFFFFF", highlightbackground="#C8D4DA", highlightthickness=1)
    card.pack(fill="both", expand=True, padx=36, pady=32)
    tk.Label(card, text="تفعيل النسخة", bg="#FFFFFF", fg="#173F58",
             font=("Times New Roman", 28, "bold")).pack(anchor="e", padx=30, pady=(28, 4))
    tk.Label(card, text="هذه النسخة محمية ومربوطة بجهاز واحد.", bg="#FFFFFF", fg="#718390",
             font=("Times New Roman", 15)).pack(anchor="e", padx=30)

    tk.Label(card, text="معرّف الجهاز", bg="#FFFFFF", fg="#263F50",
             font=("Times New Roman", 16, "bold")).pack(anchor="e", padx=30, pady=(24, 6))
    device_box = ttk.Entry(card, font=("Consolas", 16), justify="center")
    device_box.pack(fill="x", padx=30)
    device_box.insert(0, machine); device_box.configure(state="readonly")

    def copy_device():
        root.clipboard_clear(); root.clipboard_append(machine); root.update()
        messagebox.showinfo("تم النسخ", "تم نسخ معرّف الجهاز.", parent=root)

    ttk.Button(card, text="نسخ معرّف الجهاز", command=copy_device).pack(anchor="e", padx=30, pady=(7, 15))
    tk.Label(card, text="كود التفعيل المرسل من المزوّد", bg="#FFFFFF", fg="#263F50",
             font=("Times New Roman", 16, "bold")).pack(anchor="e", padx=30, pady=(2, 6))
    code_box = tk.Text(card, height=5, wrap="word", font=("Consolas", 10), relief="solid", bd=1)
    code_box.pack(fill="x", padx=30)

    def activate():
        status = manager.install_code(code_box.get("1.0", "end").strip())
        if not status.valid:
            return messagebox.showerror("فشل التفعيل", status.message, parent=root)
        accepted["value"] = True
        messagebox.showinfo("تم التفعيل", "تم تفعيل النسخة لهذا الجهاز بنجاح.", parent=root)
        root.destroy()

    actions = tk.Frame(card, bg="#FFFFFF")
    actions.pack(fill="x", padx=30, pady=22)
    tk.Button(actions, text="تفعيل وفتح البرنامج", command=activate, bg="#448AFF", fg="#FFFFFF",
              activebackground="#2F76E8", relief="flat", padx=24, pady=12,
              font=("Times New Roman", 15, "bold"), cursor="hand2").pack(side="right")
    tk.Button(actions, text="خروج", command=root.destroy, bg="#EAF0F3", fg="#173F58",
              relief="flat", padx=24, pady=12, font=("Times New Roman", 14, "bold")).pack(side="left")
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return accepted["value"]
