"""Import teacher names from ordinary Word documents without Office dependencies."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
IGNORED_HEADINGS = {
    "الاسم", "اللقب", "الاسم واللقب", "اسم المدرس", "اسم المعلم", "المدرسون",
    "المعلمون", "قائمة المدرسين", "قائمة المعلمين", "nom", "prénom", "nom et prénom",
    "enseignant", "enseignante", "enseignants", "liste des enseignants",
}


class TeacherImportError(ValueError):
    pass


def _clean_name(value: str) -> str:
    value = re.sub(r"^[\s\u2022\-*–—·]+", "", value or "")
    value = re.sub(r"^\s*\d+[.)\-:]\s*", "", value)
    value = re.sub(r"\s+", " ", value).strip(" \t|؛;،,")
    value = re.sub(r"^(?:الأستاذة?|المعلمة?|السيدة?|M(?:me|r|lle)\.?|Prof\.?)\s+", "", value, flags=re.IGNORECASE)
    return value.strip()


def normalize_teacher_names(values) -> list[str]:
    names, seen = [], set()
    for raw in values:
        for part in re.split(r"[\r\n]+", str(raw or "")):
            name = _clean_name(part)
            key = name.casefold()
            if len(name) < 3 or key in IGNORED_HEADINGS or key in seen:
                continue
            if re.fullmatch(r"[\d\W_]+", name):
                continue
            seen.add(key)
            names.append(name)
    return names


def extract_teacher_names_from_docx(path: str | Path) -> list[str]:
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise TeacherImportError("اختر ملف Word بصيغة DOCX.")
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise TeacherImportError("تعذر قراءة ملف Word. تأكد أنه ملف DOCX سليم.") from error
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise TeacherImportError("محتوى ملف Word غير صالح.") from error
    paragraphs = []
    for paragraph in root.iter(WORD_NS + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(WORD_NS + "t"))
        if text.strip():
            paragraphs.append(text)
    names = normalize_teacher_names(paragraphs)
    if not names:
        raise TeacherImportError("لم يتم العثور على أسماء. ضع كل اسم في سطر أو خلية مستقلة داخل الملف.")
    return names
