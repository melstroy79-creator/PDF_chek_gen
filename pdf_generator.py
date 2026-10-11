#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор PDF-чеков из CSV/JSON данных и HTML-шаблонов.

Как работает:
    1. Читает все CSV и JSON файлы из папки data/.
    2. Читает все HTML-шаблоны из папки templates/.
    3. Показывает список файлов и шаблонов, даёт выбрать один файл и шаблон.
    4. Показывает список счетов (invoice id) и даёт выбрать конкретный.
    5. Подставляет данные в шаблон и сохраняет PDF в папку output/.
    6. Автоматически открывает готовый PDF системной программой.

Требования:
    pip install -r requirements.txt

Структура проекта:
    pdf_generator.py
    requirements.txt
    data/        <- файлы .csv и .json
    templates/   <- файлы .html
    fonts/       <- (опционально) DejaVuSans.ttf / Roboto*.ttf для кириллицы
    output/      <- сюда сохраняются готовые PDF
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# --- Внешние зависимости с понятными сообщениями об ошибке ------------------
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    sys.exit(
        "Не найдена библиотека Jinja2.\n"
        "Установите зависимости командой:  pip install -r requirements.txt"
    )

try:
    from weasyprint import HTML
except ImportError:
    sys.exit(
        "Не найдена библиотека WeasyPrint.\n"
        "Установите зависимости командой:  pip install -r requirements.txt\n"
        "Windows: дополнительно нужен GTK (см. README.md)."
    )

# pandas необязателен: если есть — используем его для CSV, иначе стандартный csv.
try:
    import pandas as pd
except ImportError:
    pd = None

import csv


# --- Пути проекта -----------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"

DATA_EXTENSIONS = {".csv", ".json"}
TEMPLATE_EXTENSIONS = {".html", ".htm"}

# Возможные названия колонки/поля с идентификатором счёта.
ID_CANDIDATES = [
    "invoice_id", "invoiceid", "invoice_number", "invoice_no", "invoice_no.",
    "invoicenumber", "invoice", "account_id", "id", "number", "номер",
    "счет", "счёт", "код",
]


# --- Утилиты ----------------------------------------------------------------
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def header(title):
    line = "=" * 60
    print(line)
    print(title.center(60))
    print(line)


def pause():
    input("\nНажмите Enter, чтобы продолжить...")


def choose(prompt, options):
    """Аккуратное нумерованное меню с выбором по номеру."""
    print(f"\n{prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {i:>2}. {opt}")
    while True:
        raw = input("Введите номер варианта (или 'q' для выхода): ").strip()
        if raw.lower() == "q":
            sys.exit(0)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"  ! Некорректный ввод. Введите число от 1 до {len(options)}.")


def scan_files(directory, extensions):
    if not directory.exists():
        return []
    files = [
        p for p in sorted(directory.iterdir())
        if p.is_file() and p.suffix.lower() in extensions
    ]
    return files


def open_file(path):
    """Открывает файл системной программой (Windows / macOS / Linux)."""
    path = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 (Windows-only)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Не удалось автоматически открыть файл: {exc}")
        return False


# --- Чтение данных ----------------------------------------------------------
def read_csv(path):
    if pd is not None:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        return df.to_dict(orient="records")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # {"invoices": [...]}  ->  [...]
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
        else:
            data = [data]

    if not isinstance(data, list):
        raise ValueError("JSON должен содержать список объектов или словарь со списком.")
    return data


def load_records(path):
    if path.suffix.lower() == ".csv":
        return read_csv(path)
    return read_json(path)


def find_id_key(record):
    keys_lower = {str(k).lower(): k for k in record.keys()}
    for cand in ID_CANDIDATES:
        if cand in keys_lower:
            return keys_lower[cand]
    return None


def build_invoices(records):
    """
    Превращает список записей в словарь:
        {invoice_id: {"header": {...}, "items": [ {...}, ... ]}}

    Поддерживает два вида данных:
        * плоские строки (одна строка = одна позиция счёта);
        * вложенные объекты, где позиции лежат в списке (например, ключ "items").
    """
    invoices = {}
    dynamic_id_key = None

    for rec in records:
        if not isinstance(rec, dict):
            continue

        # Определяем ключ с id счёта (один раз для всего файла).
        if dynamic_id_key is None:
            dynamic_id_key = find_id_key(rec)
        id_key = dynamic_id_key or find_id_key(rec)

        iid = str(rec.get(id_key, "БЕЗ-ID")) if id_key else "БЕЗ-ID"

        # Ищем вложенный список позиций.
        items_key = None
        for key, value in rec.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                items_key = key
                break

        if iid not in invoices:
            invoices[iid] = {"id": iid, "header": {}, "items": [], "_id_key": id_key}

        if items_key is not None:
            header = {k: v for k, v in rec.items() if k != items_key}
            invoices[iid]["header"] = header
            invoices[iid]["items"].extend(rec[items_key])
        else:
            # Плоская строка: голова —— та же запись (без id), строка —— позиция.
            flat = rec
            invoices[iid]["header"] = {k: v for k, v in rec.items() if k != id_key}
            invoices[iid]["items"].append(flat)

    return invoices


def compute_total(items):
    """Пытается посчитать сумму по позициям (qty * price) или по полю total."""
    total = 0.0
    found = False
    for item in items:
        keys = {str(k).lower(): k for k in item.keys()}
        # прямое поле суммы
        for cand in ("total", "amount", "sum", "сумма", "стоимость"):
            if cand in keys:
                try:
                    total += float(str(item[keys[cand]]).replace(",", "."))
                    found = True
                    break
                except (ValueError, TypeError):
                    pass
        else:
            # количество * цена
            qty = None
            price = None
            for cand in ("qty", "quantity", "count", "шт", "количество"):
                if cand in keys:
                    try:
                        qty = float(str(item[keys[cand]]).replace(",", "."))
                    except (ValueError, TypeError):
                        qty = None
                    break
            for cand in ("price", "cost", "unit_price", "цена"):
                if cand in keys:
                    try:
                        price = float(str(item[keys[cand]]).replace(",", "."))
                    except (ValueError, TypeError):
                        price = None
                    break
            if qty is not None and price is not None:
                total += qty * price
                found = True
    return round(total, 2) if found else None


# --- Шрифты и кириллица -----------------------------------------------------
def build_font_css():
    """Регистрирует шрифты из папки fonts/ и задаёт безопасный базовый шрифт."""
    rules = []
    if FONTS_DIR.exists():
        for font_file in sorted(FONTS_DIR.glob("*")):
            if font_file.suffix.lower() not in (".ttf", ".otf"):
                continue
            stem = font_file.stem.lower()
            if "dejavu" in stem:
                family = "DejaVu Sans"
            elif "roboto" in stem:
                family = "Roboto"
            else:
                family = font_file.stem
            style = "italic" if ("italic" in stem or "oblique" in stem) else "normal"
            weight = "bold" if "bold" in stem else "normal"
            uri = font_file.resolve().as_uri()
            rules.append(
                f"@font-face {{ font-family: '{family}'; "
                f"src: url('{uri}'); font-weight: {weight}; font-style: {style}; }}"
            )

    base = (
        "html, body, * { "
        "font-family: 'DejaVu Sans', 'Roboto', 'Segoe UI', 'Helvetica Neue', "
        "Arial, sans-serif; }"
    )
    return "\n".join(rules + [base])


def inject_font_css(html_content):
    style = f"<style>\n{build_font_css()}\n</style>\n"
    if "</head>" in html_content:
        return html_content.replace("</head>", style + "</head>", 1)
    return style + html_content


# --- Готовый контекст для шаблона -------------------------------------------
# Канонические имена placeholders -> возможные названия полей в данных.
FIELD_ALIASES = {
    "invoice_id": ["invoice_id", "invoiceid", "invoice_number", "invoice_no",
                   "number", "id", "номер", "счёт", "счет"],
    "customer_name": ["customer_name", "customer", "client", "client_name",
                      "buyer", "покупатель", "клиент", "заказчик", "фио", "name"],
    "date": ["date", "invoice_date", "created_at", "order_date", "дата"],
    "email": ["email", "e-mail", "почта"],
    "phone": ["phone", "телефон", "тел"],
    "address": ["address", "адрес"],
    "status": ["status", "статус"],
}

ITEM_ALIASES = {
    "name": ["name", "item", "title", "product", "description",
             "наименование", "название", "товар", "услуга"],
    "qty": ["qty", "quantity", "count", "количество", "шт", "кол-во"],
    "unit": ["unit", "unit_name", "ед", "единица", "ед."],
    "price": ["price", "unit_price", "cost", "цена", "стоимость"],
    "sum": ["sum", "total", "amount", "line_total", "сумма", "итого"],
}


def pick(mapping, candidates):
    """Возвращает первое найденное значение по списку возможных имён ключей."""
    if not isinstance(mapping, dict):
        return None
    keys_lower = {str(k).lower(): k for k in mapping.keys()}
    for cand in candidates:
        if cand in keys_lower:
            return mapping[keys_lower[cand]]
    return None


def to_float(value):
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except (ValueError, TypeError):
        return None


def build_context(invoice, items):
    """
    Формирует плоский контекст для шаблона с удобными placeholders:
        invoice_id, customer_name, date, email, ...
        items: [{ name, qty, unit, price, sum, ... }, ...]
        total
    Исходные данные также доступны как invoice / header.
    """
    header = invoice["header"]

    fields = {canon: pick(header, aliases) for canon, aliases in FIELD_ALIASES.items()}
    fields["invoice_id"] = invoice.get("id") or fields.get("invoice_id")

    norm_items = []
    for idx, item in enumerate(items, 1):
        norm = dict(item)
        norm["#"] = idx
        for canon, aliases in ITEM_ALIASES.items():
            norm[canon] = pick(item, aliases)
        if norm.get("sum") in (None, ""):
            qty, price = to_float(norm.get("qty")), to_float(norm.get("price"))
            if qty is not None and price is not None:
                norm["sum"] = round(qty * price, 2)
        norm_items.append(norm)

    return {
        **fields,
        "invoice": header,
        "header": header,
        "items": norm_items,
        "total": compute_total(items),
    }


# --- Генерация PDF ----------------------------------------------------------
def render_pdf(template_path, invoice, items, output_path):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "htm"]),
    )
    template = env.get_template(template_path.name)

    context = build_context(invoice, items)

    html_content = template.render(**context)
    html_content = inject_font_css(html_content)

    HTML(string=html_content, base_url=str(TEMPLATES_DIR)).write_pdf(str(output_path))
    return output_path


def safe_filename(name):
    bad = '<>:"/\\|?*'
    cleaned = "".join("_" if c in bad else c for c in str(name)).strip()
    return cleaned or "invoice"


# --- Основной сценарий ------------------------------------------------------
def main():
    clear_screen()
    header("Генератор PDF-чеков")

    data_files = scan_files(DATA_DIR, DATA_EXTENSIONS)
    templates = scan_files(TEMPLATES_DIR, TEMPLATE_EXTENSIONS)

    print("\nДоступные файлы с данными (data/):")
    if data_files:
        for i, f in enumerate(data_files, 1):
            print(f"  {i:>2}. {f.name}")
    else:
        print("  (не найдено)")

    print("\nДоступные шаблоны (templates/):")
    if templates:
        for i, f in enumerate(templates, 1):
            print(f"  {i:>2}. {f.name}")
    else:
        print("  (не найдено)")

    if not data_files:
        sys.exit("\nОшибка: нет CSV/JSON файлов в папке data/. Добавьте файлы и запустите снова.")
    if not templates:
        sys.exit("\nОшибка: нет HTML-шаблонов в папке templates/. Добавьте шаблоны и запустите снова.")

    data_file = choose("Выберите файл с данными:", [f.name for f in data_files])
    data_path = DATA_DIR / data_file

    template_file = choose("Выберите HTML-шаблон:", [f.name for f in templates])
    template_path = TEMPLATES_DIR / template_file

    # Загрузка и подготовка данных.
    try:
        records = load_records(data_path)
        invoices = build_invoices(records)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"\nОшибка чтения файла {data_file}: {exc}")

    if not invoices:
        sys.exit("\nВ выбранном файле не найдено ни одного счёта.")

    invoice_ids = list(invoices.keys())
    invoice_id = choose("Выберите счёт (invoice id):", invoice_ids)
    invoice = invoices[invoice_id]

    # Генерация PDF.
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_name = f"invoice_{safe_filename(invoice_id)}.pdf"
    output_path = OUTPUT_DIR / out_name

    try:
        render_pdf(template_path, invoice, invoice["items"], output_path)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"\nОшибка генерации PDF: {exc}")

    print(f"\nГотово! PDF сохранён: {output_path}")

    if open_file(output_path):
        print("Файл открыт в системной программе просмотра PDF.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
