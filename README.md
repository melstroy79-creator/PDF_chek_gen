# Генератор PDF-чеков

Интерактивный консольный скрипт: читает данные (CSV/JSON), подставляет их
в HTML-шаблон и сохраняет готовый PDF, после чего открывает его системной программой.

## Структура

```
pdf_generator.py     основной скрипт
requirements.txt     зависимости
data/                исходные данные (.csv, .json)
templates/           HTML-шаблоны (.html)
fonts/               (опционально) шрифты с кириллицей
output/              готовые PDF
```

## Установка

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### WeasyPrint на Windows

WeasyPrint требует библиотеку GTK/Pango. Варианты:
1. Скачать установщик GTK3 и добавить его `bin` в `PATH`:
   https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases
2. Либо (проще) использовать WSL.

На macOS обычно достаточно `brew install pango` (если что-то не найдено).

### Кириллица

Положите `DejaVuSans.ttf` (и bold-версию) из https://dejavu-fonts.github.io/
в папку `fonts/`. Скрипт сам их зарегистрирует. Если папка пуста —
используется системный шрифт (Segoe UI / Arial), который тоже поддерживает кириллицу.

## Запуск

```bash
python pdf_generator.py
```

## Формат данных

**CSV** — плоские строки, счёт группируется по колонке `invoice_id`:

```csv
invoice_id,date,customer,item,qty,price
INV-1001,2026-10-01,ООО "Ромашка",Ноутбук,1,75000
INV-1001,2026-10-01,ООО "Ромашка",Мышь,2,1500
```

**JSON** — либо плоский список, либо объекты со вложенным списком позиций:

```json
[
  {
    "invoice_id": "INV-2001",
    "customer": "ООО «ТехноСервис»",
    "items": [
      { "name": "Сервер 1U", "qty": 1, "price": 210000 }
    ]
  }
]
```

Колонка с идентификатором счёта определяется автоматически:
`invoice_id`, `invoice_number`, `id`, `number`, `номер`, `счёт` и др.

## Шаблон

Шаблоны — обычный HTML с синтаксисом Jinja2. Данные подставляются в **плоские**
placeholders (имена полей в файле распознаются автоматически):

```html
{{ invoice_id }}       <!-- ID счёта -->
{{ customer_name }}    <!-- имя покупателя (customer, client, покупатель...) -->
{{ date }}             <!-- дата -->
{{ email }} {{ phone }} {{ address }} {{ status }}

{% for item in items %}
  {{ item["#"] }}      <!-- номер строки -->
  {{ item.name }}      <!-- наименование товара/услуги -->
  {{ item.qty }}       <!-- количество -->
  {{ item.unit }}      <!-- единица измерения -->
  {{ item.price }}     <!-- цена -->
  {{ item.sum }}       <!-- сумма по строке (считается автоматически) -->
{% endfor %}

{{ total }}            <!-- итоговая сумма -->
```

Полный словарь реквизитов также доступен как `invoice` (синоним `header`).
Если поля нет в данных — placeholder рендерится как `None` (используйте
`{{ customer_name or "—" }}` для значения по умолчанию).
