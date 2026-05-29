import base64
import hashlib
import html
import hmac
import json
import os
import re
import secrets
import sqlite3
import ssl
import smtplib
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from copy import deepcopy
from email.message import EmailMessage
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from datetime import datetime
from xml.etree import ElementTree as etree
from flask import Flask, render_template, request, redirect, url_for, session, send_file, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from jinja2 import Template
from docxhtml_converter.htmldocx import docxifier_from_html_string

app = Flask(__name__)
app.secret_key = 'SecretMegaKey'

# Конфигурация
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'users.db')
TEMPLATE_DOCS_DIR = os.path.join(BASE_DIR, 'template_docs')
GENERATED_DIR = os.path.join(BASE_DIR, 'generated')
CERTS_DIR = os.path.join(BASE_DIR, 'certs')
AUTH_TOKEN_TTL_SECONDS = 12 * 60 * 60
PASSWORD_RESET_TTL_SECONDS = int(os.environ.get('RPD_PASSWORD_RESET_TTL_SECONDS', str(30 * 60)))
APP_BASE_URL = os.environ.get('RPD_APP_BASE_URL', '').rstrip('/')
SMTP_HOST = os.environ.get('RPD_SMTP_HOST', '').strip()
SMTP_PORT = int(os.environ.get('RPD_SMTP_PORT', '587'))
SMTP_USERNAME = os.environ.get('RPD_SMTP_USERNAME', '').strip()
SMTP_PASSWORD = os.environ.get('RPD_SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('RPD_SMTP_FROM', SMTP_USERNAME).strip()
SMTP_USE_SSL = os.environ.get('RPD_SMTP_USE_SSL', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
SMTP_USE_TLS = os.environ.get('RPD_SMTP_USE_TLS', '1').strip().lower() in {'1', 'true', 'yes', 'on'}
GIGACHAT_CA_BUNDLE_PATH = os.path.join(CERTS_DIR, 'gigachat_ca_bundle.pem')
GIGACHAT_CERT_URLS = [
    'https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt',
    'https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt',
]

os.makedirs(TEMPLATE_DOCS_DIR, exist_ok=True)
os.makedirs(GENERATED_DIR, exist_ok=True)
os.makedirs(CERTS_DIR, exist_ok=True)

OP_COMPETENCY_INDICES = [
    f'ОП.{index:02d}'
    for index in range(1, 15)
]

SG_COMPETENCY_INDICES = [
    f'СГ.{index:02d}'
    for index in range(1, 6)
]

PROF_DISCIPLINE_TYPES = {
    'ОП': {
        'label': 'Общепрофессиональная (ОП)',
        'download_label': 'Рабочая программа профессиональной дисциплины (ОП)',
    },
    'СГ': {
        'label': 'Социально-гуманитарная (СГ)',
        'download_label': 'Рабочая программа социально-гуманитарной дисциплины (СГ)',
    },
}

MDK_COMPETENCY_INDICES = [
    'МДК.01.01', 'МДК.01.02', 'МДК.01.03', 'МДК.01.04', 'МДК.01.05',
    'МДК.02.01', 'МДК.02.02', 'МДК.02.03', 'МДК.02.04', 'МДК.02.05',
    'МДК.02.06', 'МДК.02.07',
    'МДК.03.01', 'МДК.03.02', 'МДК.03.03', 'МДК.03.04', 'МДК.03.05',
    'МДК.03.06',
    'МДК.04.01', 'МДК.04.02', 'МДК.04.03', 'МДК.04.04',
]

MDK_PROFESSIONAL_MODULES = {
    'ПМ.01': 'Разработка кода для обучения искусственного интеллекта',
    'ПМ.02': 'Администрирование баз данных',
    'ПМ.03': 'Обучение готовых моделей искусственного интеллекта',
    'ПМ.04': 'Управление и работа с большими данными в системах искусственного интеллекта',
}

MDK_PROFESSIONAL_COMPETENCIES = [
    {
        'code': 'ПК 1.1.',
        'description': 'Формировать алгоритмы разработки программных модулей в соответствии с техническим заданием',
    },
    {
        'code': 'ПК 1.2.',
        'description': 'Разрабатывать программные модули в соответствии с техническим заданием',
    },
    {
        'code': 'ПК 1.3.',
        'description': 'Оформлять программный код в соответствии с техническим заданием',
    },
    {
        'code': 'ПК 1.4.',
        'description': 'Использовать систему контроля версий программного кода с учетом обеспечения возможности организации групповой разработки',
    },
    {
        'code': 'ПК 1.5.',
        'description': 'Выполнять отладку программных модулей с использованием специализированных программных средств',
    },
    {
        'code': 'ПК 1.6.',
        'description': 'Выполнять тестирование программного кода',
    },
    {
        'code': 'ПК 1.7.',
        'description': 'Составлять тестовые сценарии',
    },
    {
        'code': 'ПК 2.1.',
        'description': 'Выявлять проблемы, возникающие в процессе эксплуатации баз данных',
    },
    {
        'code': 'ПК 2.2.',
        'description': 'Осуществлять процедуры администрирования баз данных',
    },
    {
        'code': 'ПК 2.3.',
        'description': 'Проводить аудит систем безопасности баз данных с использованием регламентов по защите информации',
    },
    {
        'code': 'ПК 2.4.',
        'description': 'Формировать требования хранилищ банка данных для обучения',
    },
    {
        'code': 'ПК 2.5.',
        'description': 'Подготавливать данные для базы знаний',
    },
    {
        'code': 'ПК 3.1.',
        'description': 'Осуществлять выбор готовых моделей искусственного интеллекта',
    },
    {
        'code': 'ПК 3.2.',
        'description': 'Формировать сценарии обучения готовых моделей искусственного интеллекта',
    },
    {
        'code': 'ПК 3.3.',
        'description': 'Проводить обучение и последующую калибровку готовых моделей искусственного интеллекта',
    },
    {
        'code': 'ПК 3.4.',
        'description': 'Контролировать результат обучения',
    },
    {
        'code': 'ПК 3.5.',
        'description': 'Оформлять результат проведения процедуры обучения',
    },
    {
        'code': 'ПК 3.6.',
        'description': 'Формировать запросы для работы с искусственным интеллектом с целью визуализации данных',
    },
    {
        'code': 'ПК 4.1',
        'description': 'Осуществлять подбор и настройку готовых моделей искусственного интеллекта',
    },
    {
        'code': 'ПК 4.2',
        'description': 'Разрабатывать и настраивать сценарии и процесс обучения',
    },
    {
        'code': 'ПК 4.3',
        'description': 'Проводить оценку эффективности обученных моделей',
    },
    {
        'code': 'ПК 4.4',
        'description': 'Формировать запросы для получения и анализа данных',
    },
    {
        'code': 'ПК 4.5',
        'description': 'Внедрять программную интеграцию нейросетей в бизнес-процессы и приложения',
    },
]

MDK_PC_DESCRIPTION_BY_CODE = {
    item['code']: item['description']
    for item in MDK_PROFESSIONAL_COMPETENCIES
}

W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
XML_NS = 'http://www.w3.org/XML/1998/namespace'

etree.register_namespace('w', W_NS)
etree.register_namespace('m', M_NS)

LATEX_SYMBOL_MAP = {
    r'\pm': '±', r'\mp': '∓',
    r'\to': '→', r'\rightarrow': '→',
    r'\leftarrow': '←', r'\leftrightarrow': '↔',
    r'\equiv': '≡', r'\ne': '≠', r'\neq': '≠',
    r'\le': '≤', r'\leq': '≤', r'\ge': '≥', r'\geq': '≥',
    r'\approx': '≈', r'\cdot': '·', r'\times': '×', r'\div': '÷',
    r'\land': '∧', r'\wedge': '∧', r'\lor': '∨', r'\vee': '∨',
    r'\neg': '¬', r'\forall': '∀', r'\exists': '∃',
    r'\in': '∈', r'\notin': '∉', r'\subset': '⊂', r'\subseteq': '⊆',
    r'\cup': '∪', r'\cap': '∩', r'\emptyset': '∅',
    r'\infty': '∞', r'\sum': '∑', r'\int': '∫',
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ',
    r'\lambda': 'λ', r'\mu': 'μ', r'\pi': 'π',
    r'\sigma': 'σ', r'\Sigma': 'Σ', r'\omega': 'ω', r'\Omega': 'Ω',
}

SUPERSCRIPT_MAP = str.maketrans({
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    'n': 'ⁿ', 'i': 'ⁱ',
})

SUBSCRIPT_MAP = str.maketrans({
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    'a': 'ₐ', 'e': 'ₑ', 'h': 'ₕ', 'i': 'ᵢ', 'j': 'ⱼ',
    'k': 'ₖ', 'l': 'ₗ', 'm': 'ₘ', 'n': 'ₙ', 'o': 'ₒ',
    'p': 'ₚ', 'r': 'ᵣ', 's': 'ₛ', 't': 'ₜ', 'u': 'ᵤ',
    'v': 'ᵥ', 'x': 'ₓ',
})


def _read_latex_group(text, open_index):
    if open_index >= len(text) or text[open_index] != '{':
        return None

    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
        if depth == 0:
            return {'content': text[open_index + 1:index], 'end': index + 1}

    return None


def _split_top_level_over(content):
    depth = 0
    for index, char in enumerate(content):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
        elif depth == 0 and content.startswith(r'\over', index):
            return content[:index].strip(), content[index + 5:].strip()

    return None


def _replace_latex_command_with_groups(text, command, group_count, renderer):
    result = []
    index = 0

    while index < len(text):
        command_index = text.find(command, index)
        if command_index == -1:
            result.append(text[index:])
            break

        result.append(text[index:command_index])
        cursor = command_index + len(command)
        groups = []

        for _ in range(group_count):
            while cursor < len(text) and text[cursor] == ' ':
                cursor += 1
            group = _read_latex_group(text, cursor)
            if not group:
                result.append(command)
                index = command_index + len(command)
                break
            groups.append(group['content'])
            cursor = group['end']
        else:
            result.append(renderer(groups))
            index = cursor

    return ''.join(result)


def _replace_latex_over(text):
    result = []
    index = 0

    while index < len(text):
        open_index = text.find('{', index)
        if open_index == -1:
            result.append(text[index:])
            break

        group = _read_latex_group(text, open_index)
        if not group:
            result.append(text[index:])
            break

        split = _split_top_level_over(group['content'])
        if not split:
            result.append(text[index:group['end']])
            index = group['end']
            continue

        numerator, denominator = split
        result.append(text[index:open_index])
        result.append(format_fraction_text(numerator, denominator))
        index = group['end']

    return ''.join(result)


def _needs_fraction_parens(value):
    text = str(value or '').strip()
    if len(text) <= 1:
        return False
    return True


def format_fraction_text(numerator, denominator):
    left = normalize_formula_text(numerator)
    right = normalize_formula_text(denominator)
    safe_left = f'({left})' if _needs_fraction_parens(left) else left
    safe_right = f'({right})' if _needs_fraction_parens(right) else right
    return f'{safe_left}⁄{safe_right}'


def _matrix_to_text(match):
    body = match.group(1)
    rows = []
    for row in re.split(r'\\\\', body):
        if not row.strip():
            continue
        cells = [
            normalize_formula_text(cell.strip())
            for cell in row.split('&')
        ]
        rows.append('|'.join(cells))

    return f"[[MATRIX:{';'.join(rows)}]]" if rows else ''


def normalize_formula_text(value):
    """Переводит частые LaTeX-команды в символы, которые стабильно видны в DOCX."""
    text = str(value or '').strip()
    text = re.sub(r'^\\\(|\\\)$', '', text)
    text = re.sub(r'^\$|\$$', '', text)
    text = re.sub(
        r'\\begin\{[pbvB]?matrix\}(.+?)\\end\{[pbvB]?matrix\}',
        _matrix_to_text,
        text,
        flags=re.DOTALL,
    )
    text = text.replace('\\\\', '\\')

    text = _replace_latex_command_with_groups(
        text,
        r'\frac',
        2,
        lambda groups: format_fraction_text(groups[0], groups[1]),
    )
    text = _replace_latex_command_with_groups(
        text,
        r'\sqrt',
        1,
        lambda groups: f'√({normalize_formula_text(groups[0])})',
    )
    text = _replace_latex_over(text)

    for command, symbol in sorted(LATEX_SYMBOL_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(command, symbol)

    text = re.sub(r'\^\{([^{}]+)\}', lambda match: match.group(1).translate(SUPERSCRIPT_MAP), text)
    text = re.sub(r'\^([A-Za-z0-9+\-=()])', lambda match: match.group(1).translate(SUPERSCRIPT_MAP), text)
    text = re.sub(r'_\{([^{}]+)\}', lambda match: match.group(1).translate(SUBSCRIPT_MAP), text)
    text = re.sub(r'_([A-Za-z0-9+\-=()])', lambda match: match.group(1).translate(SUBSCRIPT_MAP), text)
    text = text.replace('{', '').replace('}', '')

    return re.sub(r'\s+', ' ', text).strip()


def _w_tag(name):
    return f'{{{W_NS}}}{name}'


def _m_tag(name):
    return f'{{{M_NS}}}{name}'


def _strip_wrapping_parens(value):
    text = str(value or '').strip()
    if len(text) < 2 or text[0] != '(' or text[-1] != ')':
        return text

    depth = 0
    for index, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                return text

    return text[1:-1].strip()


def _find_matching_left_paren(text, close_index):
    depth = 0
    for index in range(close_index, -1, -1):
        if text[index] == ')':
            depth += 1
        elif text[index] == '(':
            depth -= 1
            if depth == 0:
                return index
    return None


def _find_matching_right_paren(text, open_index):
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == '(':
            depth += 1
        elif text[index] == ')':
            depth -= 1
            if depth == 0:
                return index
    return None


def _is_fraction_token_char(char):
    return char.isalnum() or char in '√¬±∓∞παβγδλμΣσΩω²³⁰¹⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ'


def _find_fraction_left(text, slash_index):
    end = slash_index
    index = slash_index - 1
    while index >= 0 and text[index].isspace():
        index -= 1
    if index < 0:
        return None

    if text[index] == ')':
        start = _find_matching_left_paren(text, index)
        return (start, end) if start is not None else None

    while index >= 0 and _is_fraction_token_char(text[index]):
        index -= 1
    start = index + 1
    return (start, end) if start < end else None


def _find_fraction_right(text, slash_index):
    index = slash_index + 1
    while index < len(text) and text[index].isspace():
        index += 1
    if index >= len(text):
        return None

    if text[index] == '(':
        end = _find_matching_right_paren(text, index)
        return (index, end + 1) if end is not None else None

    start = index
    while index < len(text) and _is_fraction_token_char(text[index]):
        index += 1
    return (start, index) if start < index else None


def _split_fraction_text(text):
    parts = []
    cursor = 0

    while True:
        slash_index = text.find('⁄', cursor)
        if slash_index == -1:
            parts.append(('text', text[cursor:]))
            break

        left = _find_fraction_left(text, slash_index)
        right = _find_fraction_right(text, slash_index)
        if not left or not right:
            parts.append(('text', text[cursor:slash_index + 1]))
            cursor = slash_index + 1
            continue

        left_start, left_end = left
        right_start, right_end = right
        if left_start < cursor:
            parts.append(('text', text[cursor:slash_index + 1]))
            cursor = slash_index + 1
            continue

        parts.append(('text', text[cursor:left_start]))
        parts.append((
            'fraction',
            _strip_wrapping_parens(text[left_start:left_end]),
            _strip_wrapping_parens(text[right_start:right_end]),
        ))
        cursor = right_end

    return [part for part in parts if part[0] != 'text' or part[1]]


def _make_docx_text_run(text, run_pr=None):
    run = etree.Element(_w_tag('r'))
    if run_pr is not None:
        run.append(deepcopy(run_pr))
    text_el = etree.SubElement(run, _w_tag('t'))
    if text.startswith(' ') or text.endswith(' '):
        text_el.set(f'{{{XML_NS}}}space', 'preserve')
    text_el.text = text
    return run


def _make_math_run(text):
    run = etree.Element(_m_tag('r'))
    text_el = etree.SubElement(run, _m_tag('t'))
    text_el.text = text
    return run


def _make_docx_fraction(numerator, denominator):
    math = etree.Element(_m_tag('oMath'))
    fraction = etree.SubElement(math, _m_tag('f'))
    fraction_pr = etree.SubElement(fraction, _m_tag('fPr'))
    etree.SubElement(fraction_pr, _m_tag('type'), {_m_tag('val'): 'bar'})

    num = etree.SubElement(fraction, _m_tag('num'))
    num.append(_make_math_run(numerator))

    den = etree.SubElement(fraction, _m_tag('den'))
    den.append(_make_math_run(denominator))

    return math


def _paragraph_text(paragraph):
    return ''.join(text_el.text or '' for text_el in paragraph.findall(f'.//{_w_tag("t")}'))


def _replace_paragraph_with_fraction_math(paragraph, text):
    paragraph_pr = paragraph.find(_w_tag('pPr'))
    run_pr = paragraph.find(f'.//{_w_tag("rPr")}')
    for child in list(paragraph):
        if child is not paragraph_pr:
            paragraph.remove(child)

    for part in _split_fraction_text(text):
        if part[0] == 'text':
            paragraph.append(_make_docx_text_run(part[1], run_pr))
        else:
            _, numerator, denominator = part
            paragraph.append(_make_docx_fraction(numerator, denominator))


def fix_docx_fractions(docx_bytes):
    source = BytesIO(docx_bytes)
    target = BytesIO()

    with ZipFile(source, 'r') as zin, ZipFile(target, 'w', ZIP_DEFLATED) as zout:
        document_xml = zin.read('word/document.xml')
        root = etree.fromstring(document_xml)
        changed = False

        for paragraph in root.findall(f'.//{_w_tag("p")}'):
            text = _paragraph_text(paragraph)
            if '⁄' in text:
                _replace_paragraph_with_fraction_math(paragraph, text)
                changed = True

        fixed_document_xml = etree.tostring(root, xml_declaration=True, encoding='UTF-8')

        for item in zin.infolist():
            data = fixed_document_xml if changed and item.filename == 'word/document.xml' else zin.read(item.filename)
            zout.writestr(item, data)

    return target.getvalue()


def _estimate_svg_text_width(text):
    width = 0.0
    for char in str(text or ''):
        if char.isspace():
            width += 3.0
        elif char in '()[]{}':
            width += 3.8
        elif char in '+-=±∓×÷·→←↔≡∧∨¬':
            width += 7.0
        elif char in '√∑∫':
            width += 8.0
        elif char in '²³⁰¹⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ':
            width += 4.0
        elif char.isupper():
            width += 7.2
        elif char.isdigit():
            width += 5.6
        else:
            width += 5.7

    return max(width, 5.7)


def fraction_to_svg_html(numerator, denominator):
    numerator = str(numerator or '').strip()
    denominator = str(denominator or '').strip()
    width = max(_estimate_svg_text_width(numerator), _estimate_svg_text_width(denominator)) + 6.0
    width = max(12.0, min(width, 240.0))
    center = width / 2

    return (
        '<svg class="math-frac-svg" xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.2f}pt" height="29pt" viewBox="0 0 {width:.2f} 29" '
        'style="vertical-align:-9pt; margin:0 1pt;">'
        f'<text x="{center:.2f}" y="10.5" text-anchor="middle" '
        'font-family="Times New Roman" font-size="12" xml:space="preserve">'
        f'{html.escape(numerator)}</text>'
        f'<line x1="1" y1="14" x2="{width - 1:.2f}" y2="14" '
        'stroke="#000" stroke-width="0.8"/>'
        f'<text x="{center:.2f}" y="26" text-anchor="middle" '
        'font-family="Times New Roman" font-size="12" xml:space="preserve">'
        f'{html.escape(denominator)}</text>'
        '</svg>'
    )


def matrix_to_svg_html(matrix_rows):
    rows = [
        [str(cell or '').strip() for cell in row]
        for row in matrix_rows
        if any(str(cell or '').strip() for cell in row)
    ]
    if not rows:
        return ''

    column_count = max(len(row) for row in rows)
    rows = [row + [''] * (column_count - len(row)) for row in rows]

    column_widths = []
    for column_index in range(column_count):
        cell_width = max(_estimate_svg_text_width(row[column_index]) for row in rows) + 7.0
        column_widths.append(max(10.0, min(cell_width, 70.0)))

    bracket_width = 7.0
    row_height = 14.0
    vertical_padding = 3.0
    inner_width = sum(column_widths)
    width = inner_width + bracket_width * 2 + 2.0
    height = max(18.0, len(rows) * row_height + vertical_padding * 2)
    center_y = height / 2

    text_parts = []
    x_cursor = bracket_width + 1.0
    for column_index, column_width in enumerate(column_widths):
        x = x_cursor + column_width / 2
        for row_index, row in enumerate(rows):
            y = vertical_padding + 10.5 + row_index * row_height
            text_parts.append(
                f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" '
                'font-family="Times New Roman" font-size="12" xml:space="preserve">'
                f'{html.escape(row[column_index])}</text>'
            )
        x_cursor += column_width

    left_x = bracket_width
    right_x = width - bracket_width
    return (
        '<svg class="math-matrix-svg" xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.2f}pt" height="{height:.2f}pt" viewBox="0 0 {width:.2f} {height:.2f}" '
        'style="vertical-align:middle; margin:0 2pt; overflow:visible;">'
        f'<path d="M {left_x:.2f} 2 C 1.20 2 1.20 {center_y:.2f} {left_x:.2f} {height - 2:.2f}" '
        'fill="none" stroke="#000" stroke-width="0.8" stroke-linecap="round"/>'
        f'<path d="M {right_x:.2f} 2 C {width - 1.20:.2f} 2 {width - 1.20:.2f} {center_y:.2f} {right_x:.2f} {height - 2:.2f}" '
        'fill="none" stroke="#000" stroke-width="0.8" stroke-linecap="round"/>'
        + ''.join(text_parts)
        + '</svg>'
    )


def matrix_marker_to_html(value):
    def rows_from_marker(content):
        rows = []
        for row in content.split(';'):
            cells = [cell.strip() for cell in row.split('|')]
            if any(cells):
                rows.append(cells)
        return rows

    def rows_from_bracket(content):
        rows = []
        for row in re.split(r'[;\n]+', content):
            cells = [cell.strip() for cell in row.split() if cell.strip()]
            if cells:
                rows.append(cells)
        return rows

    def render_matrix(matrix_rows):
        return matrix_to_svg_html(matrix_rows)

    matrix_tokens = {}

    def make_token(rows):
        token = f'__MATRIX_{len(matrix_tokens)}__'
        matrix_tokens[token] = render_matrix(rows)
        return token

    text = str(value or '')
    text = re.sub(
        r'\[\[MATRIX:(.+?)\]\]',
        lambda match: make_token(rows_from_marker(match.group(1))),
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r'⎛(.+?)⎞',
        lambda match: make_token(rows_from_bracket(match.group(1))),
        text,
        flags=re.DOTALL,
    )

    return text, matrix_tokens


def matrix_marker_to_docx_text(value):
    def render_rows(rows):
        rows = [
            ' '.join(cell.strip() for cell in row)
            for row in rows
            if any(cell.strip() for cell in row)
        ]
        if not rows:
            return ''
        if len(rows) == 1:
            return f'({rows[0]})'

        rendered_rows = []
        for index, row in enumerate(rows):
            if index == 0:
                left_bracket, right_bracket = '⎛', '⎞'
            elif index == len(rows) - 1:
                left_bracket, right_bracket = '⎝', '⎠'
            else:
                left_bracket, right_bracket = '⎜', '⎟'
            rendered_rows.append(f'{left_bracket} {row} {right_bracket}')

        return '<br>'.join(rendered_rows)

    def replace_marker(match):
        rows = [
            [cell.strip() for cell in row.split('|')]
            for row in match.group(1).split(';')
            if row.strip()
        ]
        return render_rows(rows)

    def replace_bracket(match):
        rows = [
            row.split()
            for row in re.split(r'[;\n]+', match.group(1))
            if row.strip()
        ]
        return render_rows(rows)

    text = str(value or '')
    if re.search(r'\[\[MATRIX:(.+?)\]\]', text, flags=re.DOTALL):
        return re.sub(r'\[\[MATRIX:(.+?)\]\]', replace_marker, text, flags=re.DOTALL)

    return re.sub(r'⎛(.+?)⎞', replace_bracket, text, flags=re.DOTALL)


def fraction_text_to_html(value):
    text, matrix_tokens = matrix_marker_to_html(value)
    if '⁄' not in text:
        escaped = html.escape(text)
        for token, matrix_html in matrix_tokens.items():
            escaped = escaped.replace(token, matrix_html)
        return escaped

    html_parts = []
    for part in _split_fraction_text(text):
        if part[0] == 'text':
            html_parts.append(html.escape(part[1]))
        else:
            _, numerator, denominator = part
            html_parts.append(fraction_to_svg_html(numerator, denominator))

    result = ''.join(html_parts)
    for token, matrix_html in matrix_tokens.items():
        result = result.replace(token, matrix_html)
    return result


def build_docx_context(context):
    docx_context = deepcopy(context)
    docx_context['oral_questions'] = [
        matrix_marker_to_docx_text(question)
        for question in docx_context.get('oral_questions', [])
    ]

    for test in docx_context.get('test_examples', []):
        test['question'] = matrix_marker_to_docx_text(test.get('question', ''))
        for answer in test.get('answers', []):
            answer['text'] = matrix_marker_to_docx_text(answer.get('text', ''))

    for work in docx_context.get('control_works', []):
        work['topic'] = matrix_marker_to_docx_text(work.get('topic', ''))
        for variant in work.get('variants', []):
            for task in variant.get('tasks', []):
                task['text'] = matrix_marker_to_docx_text(task.get('text', ''))
                for answer in task.get('answers', []):
                    answer['text'] = matrix_marker_to_docx_text(answer.get('text', ''))

    docx_context['practical_examples'] = [
        matrix_marker_to_docx_text(task)
        for task in docx_context.get('practical_examples', [])
    ]

    return docx_context


def build_pdf_context(context):
    pdf_context = deepcopy(context)
    pdf_context['oral_questions'] = [
        fraction_text_to_html(question)
        for question in pdf_context.get('oral_questions', [])
    ]

    for test in pdf_context.get('test_examples', []):
        test['question'] = fraction_text_to_html(test.get('question', ''))
        for answer in test.get('answers', []):
            answer['text'] = fraction_text_to_html(answer.get('text', ''))

    for work in pdf_context.get('control_works', []):
        work['topic'] = fraction_text_to_html(work.get('topic', ''))
        for variant in work.get('variants', []):
            for task in variant.get('tasks', []):
                task['text'] = fraction_text_to_html(task.get('text', ''))
                for answer in task.get('answers', []):
                    answer['text'] = fraction_text_to_html(answer.get('text', ''))

    pdf_context['practical_examples'] = [
        fraction_text_to_html(task)
        for task in pdf_context.get('practical_examples', [])
    ]

    return pdf_context


def parse_mdk_activities(raw_value):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    activities = []
    for activity in payload[:100]:
        if not isinstance(activity, dict):
            continue

        vd_code = str(activity.get('vd_code', '')).strip()
        vd_desc = str(activity.get('vd_desc', '')).strip()
        pcs = []
        seen_codes = set()

        for pc_item in activity.get('pcs', [])[:100]:
            if isinstance(pc_item, dict):
                pc_code = str(pc_item.get('code', '')).strip()
            else:
                pc_code = str(pc_item).strip()

            if not pc_code or pc_code in seen_codes:
                continue

            pc_desc = MDK_PC_DESCRIPTION_BY_CODE.get(pc_code)
            if not pc_desc:
                continue

            pcs.append({
                'code': pc_code,
                'description': pc_desc,
            })
            seen_codes.add(pc_code)

        if vd_code or vd_desc or pcs:
            activities.append({
                'vd_code': vd_code,
                'vd_desc': vd_desc,
                'pcs': pcs,
            })

    return activities


def parse_mdk_pc_results(raw_value, activities):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    result_by_code = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        code = str(item.get('code', '')).strip()
        if not code:
            continue
        result_by_code[code] = {
            'skills': str(item.get('skills', '')).strip(),
            'knowledge': str(item.get('knowledge', '')).strip(),
            'mastery': str(item.get('mastery', '')).strip(),
        }

    rows = []
    seen_codes = set()
    for activity in activities:
        for pc in activity.get('pcs', []):
            code = str(pc.get('code', '')).strip()
            if not code or code in seen_codes:
                continue
            values = result_by_code.get(code, {})
            rows.append({
                'code': code,
                'code_display': code.rstrip('.'),
                'skills': values.get('skills', ''),
                'knowledge': values.get('knowledge', ''),
                'mastery': values.get('mastery', ''),
            })
            seen_codes.add(code)
            if len(rows) >= 100:
                return rows

    return rows


def _parse_hours_value(value):
    text = str(value or '').strip().replace(',', '.')
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_hours_total(value):
    if value is None:
        return ''
    if float(value).is_integer():
        return str(int(value))
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def build_mdk_workload(form):
    row_specs = [
        ('classes', 'Учебные занятия'),
        ('self', 'Самостоятельная работа'),
        ('consultations', 'Консультации'),
        ('attestation', 'Промежуточная аттестация'),
    ]
    rows = []
    total_hours = 0.0
    total_practice = 0.0
    has_hours = False
    has_practice = False

    for key, label in row_specs:
        hours = form.get(f'mdk_workload_{key}_hours', '').strip()
        practice = form.get(f'mdk_workload_{key}_practice', '').strip()
        hours_number = _parse_hours_value(hours)
        practice_number = _parse_hours_value(practice)

        if hours_number is not None:
            total_hours += hours_number
            has_hours = True
        if practice_number is not None:
            total_practice += practice_number
            has_practice = True

        rows.append({
            'label': label,
            'hours': hours,
            'practice': practice,
        })

    rows.append({
        'label': 'Всего',
        'hours': _format_hours_total(total_hours) if has_hours else '',
        'practice': _format_hours_total(total_practice) if has_practice else '',
        'total': True,
    })
    return rows


def _format_mdk_hours(value):
    number = _parse_hours_value(value)
    if number is None:
        return ''
    return _format_hours_total(number)


def normalize_study_plan_index(value):
    text = str(value or '').strip().upper()
    text = text.replace(' ', '').replace('\u00a0', '')
    # Частая путаница при ручном вводе: латинские C/O/P/M вместо кириллицы.
    translation = str.maketrans({
        'C': 'С',
        'O': 'О',
        'P': 'П',
        'M': 'М',
        'Y': 'У',
        'X': 'Х',
    })
    return text.translate(translation)


def _study_plan_display_value(value):
    if value in (None, ''):
        return ''
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return f'{float(value):.2f}'.rstrip('0').rstrip('.')
    text = str(value).strip()
    number = _parse_hours_value(text)
    if number is not None and text.replace(',', '.').replace('.', '', 1).isdigit():
        return _format_hours_total(number)
    return text


def _study_plan_number(value):
    number = _parse_hours_value(value)
    return number if number is not None else 0.0


def _find_default_study_plan_path():
    configured = os.environ.get('RPD_STUDY_PLAN_FILE', '').strip()
    if configured:
        path = configured if os.path.isabs(configured) else os.path.join(BASE_DIR, configured)
        if os.path.exists(path):
            return path

    candidates = []
    for filename in os.listdir(BASE_DIR):
        lower_name = filename.lower()
        if lower_name.endswith('.xls') and not lower_name.startswith('~$'):
            candidates.append(os.path.join(BASE_DIR, filename))
    return sorted(candidates)[0] if candidates else None


def _open_study_plan_workbook():
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError('Для чтения учебного плана нужен пакет xlrd.') from exc

    path = _find_default_study_plan_path()
    if not path:
        raise FileNotFoundError('В корне проекта не найден учебный план .xls/.xlsx.')
    return xlrd.open_workbook(path), os.path.basename(path)


def _study_plan_sheet(workbook, name, fallback_index):
    try:
        return workbook.sheet_by_name(name)
    except Exception:
        return workbook.sheet_by_index(fallback_index)


def _build_study_plan_item(row):
    lecture = _study_plan_number(row[14]) if len(row) > 14 else 0.0
    practice = _study_plan_number(row[15]) if len(row) > 15 else 0.0
    classes = _study_plan_number(row[13]) if len(row) > 13 else 0.0
    if not classes and (lecture or practice):
        classes = lecture + practice

    return {
        'index': _study_plan_display_value(row[1]) if len(row) > 1 else '',
        'name': _study_plan_display_value(row[2]) if len(row) > 2 else '',
        'semester': _study_plan_display_value(row[5]) if len(row) > 5 else '',
        'control_semester': _study_plan_display_value(row[9]) if len(row) > 9 else '',
        'total': _study_plan_display_value(row[10]) if len(row) > 10 else '',
        'self': _study_plan_display_value(row[11]) if len(row) > 11 else '',
        'consultations': _study_plan_display_value(row[12]) if len(row) > 12 else '',
        'classes': _format_hours_total(classes) if classes else '',
        'lecture': _study_plan_display_value(row[14]) if len(row) > 14 else '',
        'practice': _study_plan_display_value(row[15]) if len(row) > 15 else '',
        'course_project': _study_plan_display_value(row[16]) if len(row) > 16 else '',
        'attestation': _study_plan_display_value(row[17]) if len(row) > 17 else '',
    }


def parse_study_plan_workbook():
    workbook, source_name = _open_study_plan_workbook()
    items = {}
    practices = {}

    plan_sheet = _study_plan_sheet(workbook, 'План', 2)
    for row_index in range(plan_sheet.nrows):
        row = plan_sheet.row_values(row_index)
        if len(row) < 11:
            continue
        raw_index = _study_plan_display_value(row[1])
        normalized_index = normalize_study_plan_index(raw_index)
        if not re.match(r'^(?:СГ|ОП|МДК|УП|ПП|ПДП)\.?\d', normalized_index):
            continue
        item = _build_study_plan_item(row)
        item['index'] = raw_index
        item['kind'] = 'practice' if normalized_index.startswith(('УП', 'ПП', 'ПДП')) else 'course'
        items[normalized_index] = item

    try:
        practice_sheet = _study_plan_sheet(workbook, 'СпецПрактики', 6)
    except Exception:
        practice_sheet = None

    if practice_sheet is not None:
        for row_index in range(practice_sheet.nrows):
            row = practice_sheet.row_values(row_index)
            if len(row) < 8:
                continue
            raw_index = _study_plan_display_value(row[2])
            normalized_index = normalize_study_plan_index(raw_index)
            if not re.match(r'^(?:УП|ПП|ПДП)\.?\d', normalized_index):
                continue
            entry = practices.setdefault(normalized_index, {
                'index': raw_index,
                'name': _study_plan_display_value(row[3]),
                'kind': 'practice',
                'total': '',
                'weeks': '',
                'semester': '',
                'parts': [],
            })
            part = {
                'semester': _study_plan_display_value(row[4]),
                'weeks': _study_plan_display_value(row[5]),
                'hours': _study_plan_display_value(row[7]),
            }
            entry['parts'].append(part)

        for normalized_index, entry in practices.items():
            hours_total = sum(_study_plan_number(part['hours']) for part in entry['parts'])
            weeks_total = sum(_study_plan_number(part['weeks']) for part in entry['parts'])
            semesters = []
            for part in entry['parts']:
                if part['semester'] and part['semester'] not in semesters:
                    semesters.append(part['semester'])
            entry['total'] = _format_hours_total(hours_total) if hours_total else ''
            entry['weeks'] = _format_hours_total(weeks_total) if weeks_total else ''
            entry['semester'] = ', '.join(semesters)
            items[normalized_index] = entry

    return {
        'source': source_name,
        'items': items,
        'practices': practices,
    }


def parse_mdk_thematic_plan(raw_value):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    sections = []
    for section_index, section in enumerate(payload[:100], start=1):
        if not isinstance(section, dict):
            continue

        section_title = str(section.get('section_title', '')).strip()
        topics = []

        for topic_index, topic in enumerate(section.get('topics', [])[:100], start=1):
            if not isinstance(topic, dict):
                continue

            topic_title = str(topic.get('topic_title', '')).strip()
            content = str(topic.get('content', '')).strip()
            practical = str(topic.get('practical', '')).strip()
            self_work = str(topic.get('self_work', '')).strip()
            content_hours = _format_mdk_hours(topic.get('content_hours', ''))
            practical_hours = _format_mdk_hours(topic.get('practical_hours', ''))
            self_hours = _format_mdk_hours(topic.get('self_hours', ''))
            content_competencies = str(topic.get('content_competencies', '')).strip()
            practical_competencies = str(topic.get('practical_competencies', '')).strip()
            self_competencies = str(topic.get('self_competencies', '')).strip()

            has_practical = any((practical, practical_hours, practical_competencies))
            has_self = any((self_work, self_hours, self_competencies))
            if not any((
                topic_title,
                content,
                content_hours,
                content_competencies,
                has_practical,
                has_self,
            )):
                continue

            topic_display = topic_title
            if topic_display and not topic_display.lower().startswith('тема'):
                topic_display = f'Тема {section_index}.{topic_index}. {topic_display}'

            topics.append({
                'topic_title': topic_title,
                'topic_display': topic_display,
                'content': content,
                'content_hours': content_hours,
                'content_competencies': content_competencies,
                'practical': practical,
                'practical_hours': practical_hours,
                'practical_competencies': practical_competencies,
                'self_work': self_work,
                'self_hours': self_hours,
                'self_competencies': self_competencies,
                'has_practical': has_practical,
                'has_self': has_self,
                'rowspan': 2 + (2 if has_practical else 0) + (1 if has_self else 0),
            })

        if not section_title and not topics:
            continue

        section_display = section_title
        if section_display and not section_display.lower().startswith('раздел'):
            section_display = f'Раздел {section_index}. {section_display}'

        sections.append({
            'section_title': section_title,
            'section_display': section_display,
            'topics': topics,
        })

    return sections


def parse_mdk_rooms(raw_value):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    rooms = []
    for room in payload[:100]:
        if not isinstance(room, dict):
            continue

        name = str(room.get('name', '')).strip()
        equipment = str(room.get('equipment', '')).strip()
        software = str(room.get('software', '')).strip()
        if not any((name, equipment, software)):
            continue

        rooms.append({
            'name': name,
            'equipment': equipment,
            'software': software,
        })

    return rooms


def parse_mdk_sources(raw_value):
    try:
        payload = json.loads(raw_value or '{}')
    except (TypeError, json.JSONDecodeError):
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    result = {
        'main': [],
        'additional': [],
        'electronic': [],
    }
    total = 0

    for key in ('main', 'additional', 'electronic'):
        items = payload.get(key, [])
        if not isinstance(items, list):
            continue

        for item in items:
            if total >= 100:
                return result
            text = str(item or '').strip()
            if not text:
                continue
            result[key].append(text)
            total += 1

    return result


def parse_mdk_assessments(raw_value, activities):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    values_by_code = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            code = str(item.get('code', '')).strip()
            if not code:
                continue
            values_by_code[code] = {
                'excellent_enabled': bool(item.get('excellent_enabled')),
                'excellent': str(item.get('excellent', '')).strip(),
                'good_enabled': bool(item.get('good_enabled')),
                'good': str(item.get('good', '')).strip(),
                'satisfactory_enabled': bool(item.get('satisfactory_enabled')),
                'satisfactory': str(item.get('satisfactory', '')).strip(),
                'control_methods': str(item.get('control_methods', '')).strip(),
            }

    rows = []
    seen_codes = set()
    for activity in activities:
        for pc in activity.get('pcs', []):
            code = str(pc.get('code', '')).strip()
            if not code or code in seen_codes:
                continue

            values = values_by_code.get(code, {})
            criteria = []
            if values.get('excellent_enabled'):
                criteria.append({
                    'label': 'Оценка "отлично":',
                    'text': values.get('excellent', ''),
                })
            if values.get('good_enabled'):
                criteria.append({
                    'label': 'Оценка "хорошо":',
                    'text': values.get('good', ''),
                })
            if values.get('satisfactory_enabled'):
                criteria.append({
                    'label': 'Оценка "удовлетворительно":',
                    'text': values.get('satisfactory', ''),
                })

            rows.append({
                'code': code,
                'code_display': code.rstrip('.'),
                'criteria': criteria,
                'control_methods': values.get('control_methods', ''),
            })
            seen_codes.add(code)
            if len(rows) >= 100:
                return rows

    return rows


def parse_mdk_kos_results(raw_value, activities):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    groups_by_code = {}
    if isinstance(payload, list):
        for group in payload:
            if not isinstance(group, dict):
                continue
            code = str(group.get('code', '')).strip()
            if not code:
                continue
            items = []
            for item in group.get('items', [])[:100]:
                if not isinstance(item, dict):
                    continue
                result_code = str(item.get('result_code', '')).strip()
                result_name = str(item.get('result_name', '')).strip()
                if result_code or result_name:
                    items.append({
                        'result_code': result_code,
                        'result_name': result_name,
                    })
            groups_by_code[code] = items

    rows = []
    seen_codes = set()
    for activity in activities:
        for pc in activity.get('pcs', []):
            code = str(pc.get('code', '')).strip()
            if not code or code in seen_codes:
                continue
            items = groups_by_code.get(code, [])
            if items:
                rows.append({
                    'code': code,
                    'code_display': code.rstrip('.'),
                    'items': items[:100],
                })
            seen_codes.add(code)
            if len(rows) >= 100:
                return rows

    return rows


def parse_mdk_kos_questions(raw_value):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    if not isinstance(payload, list):
        return []

    questions = []
    for item in payload[:100]:
        text = str(item or '').strip()
        if text:
            questions.append(text)

    return questions


def parse_mdk_kos_tickets(raw_value):
    try:
        payload = json.loads(raw_value or '[]')
    except (TypeError, json.JSONDecodeError):
        payload = []

    if not isinstance(payload, list):
        return []

    tickets = []
    for item in payload[:100]:
        if not isinstance(item, dict):
            continue
        raw_questions = item.get('questions', [])
        if not isinstance(raw_questions, list):
            continue
        questions = []
        for question in raw_questions[:100]:
            text = str(question or '').strip()
            if text:
                questions.append(text)
        if questions:
            tickets.append({'questions': questions})

    return tickets


AI_ASSISTANT_SYSTEM_PROMPT = (
    "Ты специализированный ИИ-помощник конструктора РПД и КОС для СПО. "
    "Пиши официальным методическим стилем, без разговорных оборотов. "
    "Учитывай структуру РПД, КОС, ОП, МДК, профессиональные компетенции, темы, "
    "планируемые результаты, тесты, билеты и формулы. "
    "Жесткие ограничения: отвечай только на поставленное действие; не добавляй пояснения, "
    "предисловия, комментарии, Markdown, ссылки и советы вне запроса; не задавай уточняющих "
    "вопросов; если данных мало, верни минимальный пригодный черновик; не придумывай реквизиты "
    "приказов, ФИО и официальные номера; возвращай только валидный json."
)

AI_RESPONSE_MAX_TOKENS = {
    'suggest_text': 900,
    'check_document': 1400,
    'generate_kos': 2600,
    'formula': 450,
}

GIGACHAT_TOKEN_CACHE = {
    'access_token': None,
    'expires_at': 0,
}


def compact_text(value, fallback=''):
    text = str(value or '').strip()
    return re.sub(r'\s+', ' ', text) if text else fallback


def first_context_value(context, *keys, fallback=''):
    for key in keys:
        value = compact_text(context.get(key))
        if value:
            return value
    return fallback


def strip_code_fence(text):
    value = str(text or '').strip()
    value = re.sub(r'^```(?:json)?\s*', '', value, flags=re.IGNORECASE)
    value = re.sub(r'\s*```$', '', value)
    return value.strip()


def parse_ai_json(text):
    value = strip_code_fence(text)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        start = value.find('{')
        end = value.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(value[start:end + 1])
            except json.JSONDecodeError:
                return None
    return None


def get_default_ca_bundle_text():
    possible_paths = []
    try:
        import certifi
        possible_paths.append(certifi.where())
    except ImportError:
        pass

    default_paths = ssl.get_default_verify_paths()
    if default_paths.cafile:
        possible_paths.append(default_paths.cafile)

    for path in possible_paths:
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except OSError:
                continue

    return ''


def download_gigachat_certificate(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'rpd-constructor/1.0'})
    unverified_context = ssl._create_unverified_context()
    with urllib.request.urlopen(request, timeout=30, context=unverified_context) as response:
        return response.read().decode('utf-8')


def ensure_gigachat_ca_bundle():
    custom_bundle = os.environ.get('GIGACHAT_CA_BUNDLE')
    if custom_bundle and os.path.exists(custom_bundle):
        return custom_bundle

    if os.path.exists(GIGACHAT_CA_BUNDLE_PATH):
        return GIGACHAT_CA_BUNDLE_PATH

    bundle_parts = [get_default_ca_bundle_text()]
    for url in GIGACHAT_CERT_URLS:
        try:
            cert_text = download_gigachat_certificate(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            app.logger.warning(f'GigaChat certificate download failed from {url}: {exc}')
            continue
        if 'BEGIN CERTIFICATE' in cert_text:
            bundle_parts.append(cert_text)

    bundle_text = '\n'.join(part.strip() for part in bundle_parts if part and part.strip())
    if 'BEGIN CERTIFICATE' not in bundle_text:
        return None

    with open(GIGACHAT_CA_BUNDLE_PATH, 'w', encoding='utf-8', newline='\n') as f:
        f.write(bundle_text)
        f.write('\n')

    return GIGACHAT_CA_BUNDLE_PATH


def build_gigachat_ssl_context():
    ca_bundle = ensure_gigachat_ca_bundle()
    if ca_bundle:
        return ssl.create_default_context(cafile=ca_bundle)
    return ssl.create_default_context()


def get_gigachat_config():
    return {
        'auth_key': os.environ.get('GIGACHAT_AUTH_KEY') or os.environ.get('RPD_AI_API_KEY'),
        'model': os.environ.get('GIGACHAT_MODEL') or os.environ.get('RPD_AI_MODEL') or 'GigaChat',
        'scope': os.environ.get('GIGACHAT_SCOPE') or 'GIGACHAT_API_PERS',
        'oauth_url': os.environ.get('GIGACHAT_OAUTH_URL') or 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth',
        'api_url': (os.environ.get('GIGACHAT_API_URL') or 'https://gigachat.devices.sberbank.ru/api/v1').rstrip('/'),
    }


def get_gigachat_access_token(config):
    now_ms = int(time.time() * 1000)
    cached_token = GIGACHAT_TOKEN_CACHE.get('access_token')
    cached_expiry = int(GIGACHAT_TOKEN_CACHE.get('expires_at') or 0)
    if cached_token and cached_expiry - 60_000 > now_ms:
        return cached_token

    form_data = urllib.parse.urlencode({'scope': config['scope']}).encode('utf-8')
    req = urllib.request.Request(
        config['oauth_url'],
        data=form_data,
        headers={
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'RqUID': str(uuid.uuid4()),
            'Authorization': f"Basic {config['auth_key']}",
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=30, context=build_gigachat_ssl_context()) as response:
            raw = response.read().decode('utf-8')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        app.logger.warning(f'GigaChat OAuth failed: {exc}')
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    access_token = data.get('access_token')
    expires_at = int(data.get('expires_at') or 0)
    if not access_token:
        return None

    GIGACHAT_TOKEN_CACHE['access_token'] = access_token
    GIGACHAT_TOKEN_CACHE['expires_at'] = expires_at
    return access_token


def read_http_error_body(exc):
    try:
        body = exc.read().decode('utf-8', errors='replace')
    except Exception:
        body = ''
    return compact_text(body)[:500]


def send_gigachat_chat_request(config, access_token, body):
    url = f"{config['api_url']}/chat/completions"
    request_data = json.dumps(body, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=request_data,
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )

    with urllib.request.urlopen(req, timeout=30, context=build_gigachat_ssl_context()) as response:
        return response.read().decode('utf-8')


def call_external_ai(action, payload, response_hint):
    config = get_gigachat_config()
    if not config.get('auth_key'):
        return None

    access_token = get_gigachat_access_token(config)
    if not access_token:
        return None

    user_prompt = (
        f'Действие: {action}\n'
        f'Ожидаемый json: {response_hint}\n'
        f'Если передан active_context, отвечай строго для указанного поля active_context.field_label '
        f'и указанного пункта active_context.card_title или active_context.section_title.\n'
        f'Верни только json-объект, без текста вокруг него.\n'
        f'Данные формы: {json.dumps(payload, ensure_ascii=False)}'
    )
    body = {
        'model': config['model'],
        'temperature': 0.15,
        'max_tokens': AI_RESPONSE_MAX_TOKENS.get(action, 1200),
        'stream': False,
        'repetition_penalty': 1.08,
        'messages': [
            {'role': 'system', 'content': AI_ASSISTANT_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt},
        ],
    }
    try:
        raw = send_gigachat_chat_request(config, access_token, body)
    except urllib.error.HTTPError as exc:
        error_body = read_http_error_body(exc)
        app.logger.warning(f'GigaChat external call failed: HTTP {exc.code}: {error_body or exc.reason}')
        if exc.code == 404 and body.get('model') != 'GigaChat':
            app.logger.warning(f"GigaChat model '{body.get('model')}' is unavailable, retrying with 'GigaChat'.")
            body['model'] = 'GigaChat'
            try:
                raw = send_gigachat_chat_request(config, access_token, body)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as retry_exc:
                app.logger.warning(f'GigaChat retry failed: {retry_exc}')
                return None
        else:
            return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        app.logger.warning(f'GigaChat external call failed: {exc}')
        return None

    try:
        data = json.loads(raw)
        content = data['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None

    parsed = parse_ai_json(content)
    if isinstance(parsed, dict):
        parsed.setdefault('provider', 'gigachat')
        parsed.setdefault('model', config['model'])
    return parsed


def build_ai_context(payload):
    context = payload.get('context') if isinstance(payload.get('context'), dict) else {}
    fields = payload.get('fields') if isinstance(payload.get('fields'), list) else []
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = compact_text(field.get('name'))
        value = compact_text(field.get('value'))
        if name and value and name not in context:
            context[name] = value
    return context


def local_ai_suggest_text(payload):
    context = build_ai_context(payload)
    active_context = payload.get('active_context') if isinstance(payload.get('active_context'), dict) else {}
    label = compact_text(payload.get('label')).lower()
    placeholder = compact_text(payload.get('placeholder')).lower()
    field_hint = f'{label} {placeholder}'
    discipline = first_context_value(context, 'discipline_name', fallback='дисциплина')
    index = first_context_value(context, 'mdk_index', 'competency_index')
    speciality = first_context_value(context, 'speciality_name', fallback='соответствующей специальности')
    module = first_context_value(context, 'professional_module_text', 'professional_module_title', fallback='профессионального модуля')
    topic = compact_text(active_context.get('card_title')) or first_context_value(context, 'topic_title', fallback=discipline)

    if 'цель' in field_hint:
        text = (
            f'формирование у обучающихся знаний, умений и практических навыков, необходимых для освоения '
            f'{index + " " if index else ""}«{discipline}», выполнения профессиональных задач по специальности '
            f'{speciality}, а также применения изученных методов и инструментов в условиях будущей профессиональной деятельности.'
        )
    elif 'уметь' in field_hint or 'умение' in field_hint:
        text = (
            f'анализировать условия профессиональных задач по дисциплине «{discipline}», выбирать рациональные методы '
            f'их решения, применять изученные алгоритмы и инструменты, оформлять результаты работы в соответствии с '
            f'требованиями образовательной программы.'
        )
    elif 'знать' in field_hint or 'знание' in field_hint:
        text = (
            f'основные понятия, методы и принципы дисциплины «{discipline}», требования к выполнению учебных и '
            f'профессиональных задач, способы анализа результатов и критерии оценки качества выполненной работы.'
        )
    elif 'владеть' in field_hint or 'навык' in field_hint:
        text = (
            f'навыками применения методов дисциплины «{discipline}» при решении практических задач, подготовки '
            f'обоснованных решений, проверки результатов и представления выполненной работы в профессиональном формате.'
        )
    elif 'описание вд' in field_hint or 'вид' in field_hint:
        text = f'Выполнение работ в рамках {module}, направленных на решение профессиональных задач по специальности {speciality}.'
    elif 'содержание' in field_hint:
        text = (
            f'Изучение темы «{topic}»: основные понятия, назначение, область применения, типовые методы решения задач, '
            f'практические примеры и анализ результатов.'
        )
    elif 'практи' in field_hint:
        text = f'Выполнение практических заданий по теме «{topic}»: анализ условий задачи, выбор метода решения, оформление и проверка результата.'
    elif 'самостоятель' in field_hint:
        text = f'Самостоятельное изучение теоретического материала по теме «{topic}», подготовка краткого конспекта и выполнение тренировочных заданий.'
    elif 'оборуд' in field_hint:
        text = 'Компьютеризированные рабочие места обучающихся с выходом в сеть Интернет, рабочее место преподавателя, мультимедийное оборудование, комплект учебной мебели.'
    elif 'программ' in field_hint:
        text = 'Операционная система, офисный пакет, среда разработки, браузер, средства работы с данными и специализированное программное обеспечение по профилю дисциплины.'
    elif 'результат' in field_hint:
        text = f'Способность применять знания и умения по дисциплине «{discipline}» для решения учебных и профессиональных задач.'
    elif 'вопрос' in field_hint or 'задание' in field_hint:
        text = f'Раскройте основные понятия темы «{topic}» и приведите пример их применения в профессиональной деятельности.'
    else:
        text = (
            f'Сформулируйте содержание по дисциплине «{discipline}» в соответствии с требованиями образовательной '
            f'программы, указанными компетенциями и тематическим планом.'
        )

    return {
        'ok': True,
        'source': 'local',
        'text': text,
        'notice': 'Использован локальный помощник. Для генерации GigaChat задайте GIGACHAT_AUTH_KEY или RPD_AI_API_KEY.',
    }


def local_ai_check_document(payload):
    fields = payload.get('fields') if isinstance(payload.get('fields'), list) else []
    context = build_ai_context(payload)
    issues = []
    suggestions = []
    required_empty = []

    for field in fields:
        if not isinstance(field, dict):
            continue
        label = compact_text(field.get('label') or field.get('name') or 'Поле')
        value = compact_text(field.get('value'))
        if field.get('required') and not value:
            required_empty.append(label)
        if field.get('type') == 'textarea' and value and len(value) < 18:
            suggestions.append(f'Поле «{label}» заполнено слишком кратко. Проверьте, достаточно ли текста для документа.')

    if required_empty:
        issues.append('Не заполнены обязательные поля: ' + ', '.join(required_empty[:12]) + ('.' if len(required_empty) <= 12 else ' и другие.'))

    topics = payload.get('topics') if isinstance(payload.get('topics'), list) else []
    pcs = payload.get('pcs') if isinstance(payload.get('pcs'), list) else []
    kos = payload.get('kos') if isinstance(payload.get('kos'), dict) else {}

    if not topics:
        suggestions.append('Не обнаружены темы тематического плана. Если раздел 2.2 уже заполнен, проверьте, что данные не пустые.')
    if first_context_value(context, 'template') == 'mdk' and not pcs:
        issues.append('Для МДК не обнаружены выбранные ПК. Добавьте профессиональные компетенции в разделе видов деятельности.')
    if not kos.get('questions') and not kos.get('tests') and not kos.get('tickets'):
        suggestions.append('В КОС пока не обнаружены вопросы, тесты или билеты. Можно сгенерировать черновик по темам.')

    if not issues:
        issues.append('Критичных проблем в заполнении не найдено.')
    if not suggestions:
        suggestions.append('Перед генерацией проверьте смысловую точность формулировок и соответствие выбранным компетенциям.')

    return {
        'ok': True,
        'source': 'local',
        'issues': issues,
        'suggestions': suggestions,
        'notice': 'Проверка выполнена локальным помощником. При наличии API-ключа будет доступна более глубокая ИИ-проверка.',
    }


def make_topic_list(payload):
    topics = payload.get('topics') if isinstance(payload.get('topics'), list) else []
    clean_topics = []
    for item in topics[:20]:
        if isinstance(item, dict):
            title = compact_text(item.get('title') or item.get('section') or item.get('content'))
        else:
            title = compact_text(item)
        if title:
            clean_topics.append(title)
    return clean_topics or ['ключевые темы дисциплины']


def local_ai_generate_kos(payload):
    context = build_ai_context(payload)
    topics = make_topic_list(payload)
    discipline = first_context_value(context, 'discipline_name', fallback='дисциплина')
    template_type = first_context_value(context, 'template')
    competency_index = first_context_value(context, 'competency_index', 'mdk_index')
    pcs = payload.get('pcs') if isinstance(payload.get('pcs'), list) else []
    pc_codes = [compact_text(item.get('code') if isinstance(item, dict) else item) for item in pcs]
    default_code = competency_index or ('ОК.01' if template_type == 'prof' else 'ПК 1.1')
    pc_codes = [code for code in pc_codes if code][:5] or [default_code]

    questions = [
        f'Раскройте содержание темы «{topic}» и приведите пример ее применения в рамках дисциплины «{discipline}».'
        for topic in topics[:10]
    ]
    test_examples = [
        {
            'question': f'Какое утверждение наиболее точно характеризует тему «{topic}»?',
            'answers': [
                f'основные понятия и методы темы «{topic}»',
                'случайный набор несвязанных действий',
                'только оформление отчета без анализа',
                'действие, не связанное с профессиональной задачей',
            ],
        }
        for topic in topics[:6]
    ]
    tickets = [
        {
            'questions': [
                questions[index % len(questions)],
                f'Опишите порядок решения практической задачи по теме «{topics[index % len(topics)]}».',
            ]
        }
        for index in range(min(10, max(1, len(topics))))
    ]
    control_works = [
        {
            'topic': topic,
            'variants': [
                {
                    'tasks': [
                        {
                            'text': f'Выполните практическое задание по теме «{topic}» и обоснуйте выбранный способ решения.',
                            'answers': [
                                f'применение основных методов темы «{topic}»',
                                'выбор случайного решения без анализа',
                                'оформление ответа без выполнения задания',
                                'использование не относящихся к теме данных',
                            ],
                        },
                        {
                            'text': f'Проанализируйте ситуацию по теме «{topic}» и сформулируйте вывод.',
                            'answers': [],
                        },
                    ],
                },
            ],
        }
        for topic in topics[:5]
    ]
    kos_results = [
        {
            'code': code,
            'items': [
                {
                    'result_code': f'З{idx + 1}',
                    'result_name': f'Знать основные понятия и методы темы «{topics[idx % len(topics)]}».',
                },
                {
                    'result_code': f'У{idx + 1}',
                    'result_name': f'Уметь применять методы темы «{topics[idx % len(topics)]}» при решении практических задач.',
                },
            ],
        }
        for idx, code in enumerate(pc_codes)
    ]

    return {
        'ok': True,
        'source': 'local',
        'data': {
            'questions': questions,
            'test_examples': test_examples,
            'tickets': tickets,
            'control_works': control_works,
            'kos_results': kos_results,
        },
        'notice': 'Сгенерирован черновик. Проверьте формулировки перед созданием документа.',
    }


def normalize_ai_text_list(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            text = compact_text(item.get('text') or item.get('question') or item.get('title') or item.get('name'))
        else:
            text = compact_text(item)
        if text:
            result.append(text)
    return result


def normalize_ai_test_examples(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            question = compact_text(item.get('question') or item.get('text') or item.get('title'))
            answers = item.get('answers') or item.get('options') or []
            if not isinstance(answers, list):
                answers = []
            if not answers:
                answers = [
                    item.get('answer_a') or item.get('a'),
                    item.get('answer_b') or item.get('b'),
                    item.get('answer_c') or item.get('c'),
                    item.get('answer_d') or item.get('d'),
                ]
            answers = [compact_text(answer) for answer in answers if compact_text(answer)]
        else:
            question = compact_text(item)
            answers = []
        if question:
            result.append({'question': question, 'answers': answers[:4]})
    return result


def normalize_ai_tickets(value):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        raw_questions = []
        if isinstance(item, dict):
            raw_questions = item.get('questions') or item.get('items') or []
        elif isinstance(item, list):
            raw_questions = item
        else:
            raw_questions = [item]
        questions = normalize_ai_text_list(raw_questions)
        if questions:
            result.append({'questions': questions[:100]})
    return result


def normalize_ai_kos_results(value):
    if not isinstance(value, list):
        return []
    result = []
    for group in value:
        if not isinstance(group, dict):
            continue
        code = compact_text(group.get('code') or group.get('pc') or group.get('competency'))
        raw_items = group.get('items') or group.get('results') or []
        if not isinstance(raw_items, list):
            raw_items = []
        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            result_code = compact_text(item.get('result_code') or item.get('code') or item.get('rescode'))
            result_name = compact_text(item.get('result_name') or item.get('name') or item.get('desc') or item.get('description'))
            if result_code or result_name:
                items.append({'result_code': result_code, 'result_name': result_name})
        if code and items:
            result.append({'code': code, 'items': items})
    return result


def normalize_ai_control_works(value):
    if not isinstance(value, list):
        return []
    result = []
    for work in value:
        if not isinstance(work, dict):
            continue
        topic = compact_text(work.get('topic') or work.get('title') or work.get('name'))
        raw_variants = work.get('variants') or []
        if not isinstance(raw_variants, list):
            raw_variants = []

        variants = []
        for variant in raw_variants:
            raw_tasks = []
            if isinstance(variant, dict):
                raw_tasks = variant.get('tasks') or variant.get('questions') or []
            elif isinstance(variant, list):
                raw_tasks = variant
            if not isinstance(raw_tasks, list):
                raw_tasks = []

            tasks = []
            for task in raw_tasks:
                if isinstance(task, dict):
                    text = compact_text(task.get('text') or task.get('question') or task.get('title'))
                    raw_answers = task.get('answers') or task.get('options') or []
                    if not isinstance(raw_answers, list):
                        raw_answers = []
                    answers = [
                        compact_text(answer.get('text') if isinstance(answer, dict) else answer)
                        for answer in raw_answers
                    ]
                    answers = [answer for answer in answers if answer][:4]
                else:
                    text = compact_text(task)
                    answers = []
                if text or answers:
                    tasks.append({'text': text, 'answers': answers})
            if tasks:
                variants.append({'tasks': tasks})

        if topic or variants:
            result.append({'topic': topic, 'variants': variants})
    return result


def normalize_generated_kos_response(external, fallback):
    fallback_data = fallback.get('data') if isinstance(fallback, dict) else {}
    if not isinstance(fallback_data, dict):
        fallback_data = {}

    raw_data = external.get('data') if isinstance(external, dict) and isinstance(external.get('data'), dict) else external
    if not isinstance(raw_data, dict):
        raw_data = {}

    normalized = {
        'questions': normalize_ai_text_list(raw_data.get('questions')),
        'test_examples': normalize_ai_test_examples(raw_data.get('test_examples') or raw_data.get('tests')),
        'tickets': normalize_ai_tickets(raw_data.get('tickets')),
        'control_works': normalize_ai_control_works(raw_data.get('control_works') or raw_data.get('works')),
        'kos_results': normalize_ai_kos_results(raw_data.get('kos_results') or raw_data.get('results')),
    }

    missing_keys = []
    for key in ('questions', 'test_examples', 'tickets', 'control_works', 'kos_results'):
        if not normalized[key]:
            fallback_value = fallback_data.get(key)
            normalized[key] = fallback_value if isinstance(fallback_value, list) else []
            missing_keys.append(key)

    has_content = any(normalized[key] for key in ('questions', 'test_examples', 'tickets', 'control_works', 'kos_results'))
    if not has_content:
        return fallback

    notice = compact_text(external.get('notice') if isinstance(external, dict) else '')
    if missing_keys:
        notice = notice or 'Часть ответа AI была пустой, поэтому недостающие блоки дополнены локальным генератором.'

    return {
        'ok': True,
        'source': external.get('source', 'ai') if isinstance(external, dict) else 'ai',
        'provider': external.get('provider') if isinstance(external, dict) else None,
        'model': external.get('model') if isinstance(external, dict) else None,
        'data': normalized,
        'notice': notice,
    }


def local_ai_formula(payload):
    prompt = compact_text(payload.get('prompt')).lower()
    raw = compact_text(payload.get('prompt'))
    if 'квадрат' in prompt or 'дискриминант' in prompt:
        latex = r'x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}'
    elif 'матриц' in prompt and '4' in prompt:
        latex = r'\begin{pmatrix}0&1&0&1\\1&0&1&0\\0&1&0&1\\1&0&1&0\end{pmatrix}'
    elif 'матриц' in prompt:
        latex = r'\begin{pmatrix}0&1&0\\1&0&1\\0&1&0\end{pmatrix}'
    elif 'кор' in prompt:
        latex = r'\sqrt{x^2 + y^2}'
    elif 'импликац' in prompt or 'следует' in prompt:
        latex = r'A \to B'
    elif 'эквивал' in prompt or 'тождеств' in prompt:
        latex = r'(X \to Y) \equiv ((\neg X) \lor Y)'
    elif 'дроб' in prompt:
        latex = r'\frac{a}{b}'
    else:
        latex = raw or r'\frac{a}{b}'

    return {
        'ok': True,
        'source': 'local',
        'latex': latex,
        'notice': 'Формула подготовлена локальным помощником. Проверьте предпросмотр MathJax.',
    }


def ai_response_with_external(action, payload, local_builder, response_hint):
    external = call_external_ai(action, payload, response_hint)
    if isinstance(external, dict):
        external.setdefault('ok', True)
        external.setdefault('source', 'ai')
        return external
    return local_builder(payload)


# ---------- Работа с базой данных ----------
def _ensure_user_columns(cur):
    cur.execute('PRAGMA table_info(users)')
    existing_columns = {row[1] for row in cur.fetchall()}
    required_columns = {
        'created_at': 'TEXT',
        'email': 'TEXT',
        'session_token_hash': 'TEXT',
        'session_jti': 'TEXT',
        'token_issued_at': 'INTEGER',
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            cur.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_type}')


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT,
            email TEXT,
            session_token_hash TEXT,
            session_jti TEXT,
            token_issued_at INTEGER
        )
    ''')
    _ensure_user_columns(cur)
    cur.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
        ON users(email COLLATE NOCASE)
        WHERE email IS NOT NULL AND email <> ''
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_password_reset_user_id ON password_reset_tokens(user_id)')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_password_reset_expires_at ON password_reset_tokens(expires_at)')
    cur.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] == 0:
        created_at = datetime.now().isoformat(timespec='seconds')
        test_users = [
            ('SimpleTeach', generate_password_hash('12345678'), created_at),
            ('SimpleTeach2', generate_password_hash('123456789'), created_at),
            ('SimpleTeach3', generate_password_hash('1234567890'), created_at)
        ]
        cur.executemany('INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)', test_users)
    conn.commit()
    conn.close()


def get_user(username):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,))
    user = cur.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        'SELECT id, username, password_hash, session_token_hash, session_jti, token_issued_at FROM users WHERE id = ?',
        (user_id,)
    )
    user = cur.fetchone()
    conn.close()
    return user


def get_user_for_password_reset(identifier):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT id, username, email
        FROM users
        WHERE username = ? OR lower(email) = lower(?)
        ''',
        (identifier, identifier)
    )
    user = cur.fetchone()
    conn.close()
    return user


def create_user(username, password, email):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            'INSERT INTO users (username, password_hash, email, created_at) VALUES (?, ?, ?, ?)',
            (username, generate_password_hash(password), email, datetime.now().isoformat(timespec='seconds'))
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return False, 'Пользователь с таким логином или email уже существует.'
    finally:
        conn.close()
    return True, None


def _b64url_encode(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _b64url_decode(value):
    padding = '=' * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode('ascii'))


def _json_b64(data):
    return _b64url_encode(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def _token_signature(unsigned_token):
    secret = app.secret_key.encode('utf-8')
    return _b64url_encode(hmac.new(secret, unsigned_token.encode('ascii'), hashlib.sha256).digest())


def create_auth_token(payload):
    header = {'alg': 'HS256', 'typ': 'JWT'}
    unsigned_token = f'{_json_b64(header)}.{_json_b64(payload)}'
    return f'{unsigned_token}.{_token_signature(unsigned_token)}'


def verify_auth_token(token):
    try:
        header_part, payload_part, signature = token.split('.', 2)
        unsigned_token = f'{header_part}.{payload_part}'
        expected_signature = _token_signature(unsigned_token)
        if not hmac.compare_digest(signature, expected_signature):
            return None
        payload = json.loads(_b64url_decode(payload_part).decode('utf-8'))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError, base64.binascii.Error):
        return None
    if payload.get('typ') != 'rpd-session':
        return None
    if int(payload.get('exp', 0)) < int(time.time()):
        return None
    return payload


def token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def store_session_token(user_id, token, jti, issued_at):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        'UPDATE users SET session_token_hash = ?, session_jti = ?, token_issued_at = ? WHERE id = ?',
        (token_hash(token), jti, issued_at, user_id)
    )
    conn.commit()
    conn.close()


def clear_session_token(user_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        'UPDATE users SET session_token_hash = NULL, session_jti = NULL, token_issued_at = NULL WHERE id = ?',
        (user_id,)
    )
    conn.commit()
    conn.close()


def create_password_reset_token(user_id):
    raw_token = secrets.token_urlsafe(36)
    now = int(time.time())
    expires_at = now + PASSWORD_RESET_TTL_SECONDS
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        'UPDATE password_reset_tokens SET used_at = ? WHERE user_id = ? AND used_at IS NULL',
        (now, user_id)
    )
    cur.execute(
        '''
        INSERT INTO password_reset_tokens (user_id, token_hash, created_at, expires_at)
        VALUES (?, ?, ?, ?)
        ''',
        (user_id, token_hash(raw_token), now, expires_at)
    )
    cur.execute(
        'DELETE FROM password_reset_tokens WHERE expires_at < ? OR used_at IS NOT NULL',
        (now - 24 * 60 * 60,)
    )
    conn.commit()
    conn.close()
    return raw_token


def get_password_reset_user(token):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT prt.id, prt.user_id, users.username
        FROM password_reset_tokens prt
        JOIN users ON users.id = prt.user_id
        WHERE prt.token_hash = ?
          AND prt.used_at IS NULL
          AND prt.expires_at >= ?
        ''',
        (token_hash(token), int(time.time()))
    )
    row = cur.fetchone()
    conn.close()
    return row


def mark_password_reset_token_used(token_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('UPDATE password_reset_tokens SET used_at = ? WHERE id = ?', (int(time.time()), token_id))
    conn.commit()
    conn.close()


def update_user_password(user_id, password):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        '''
        UPDATE users
        SET password_hash = ?, session_token_hash = NULL, session_jti = NULL, token_issued_at = NULL
        WHERE id = ?
        ''',
        (generate_password_hash(password), user_id)
    )
    conn.commit()
    conn.close()


def build_password_reset_url(token):
    if APP_BASE_URL:
        return f'{APP_BASE_URL}{url_for("reset_password", token=token)}'
    return url_for('reset_password', token=token, _external=True)


def send_password_reset_email(email, username, reset_url):
    if not SMTP_HOST or not SMTP_FROM:
        app.logger.warning('SMTP is not configured. Password reset link for %s: %s', username, reset_url)
        return False

    message = EmailMessage()
    message['Subject'] = 'Восстановление пароля в конструкторе РПД'
    message['From'] = SMTP_FROM
    message['To'] = email
    message.set_content(
        '\n'.join([
            f'Здравствуйте, {username}!',
            '',
            'Для восстановления пароля в конструкторе РПД перейдите по ссылке:',
            reset_url,
            '',
            f'Ссылка действует {PASSWORD_RESET_TTL_SECONDS // 60} минут.',
            'Если вы не запрашивали восстановление пароля, просто проигнорируйте это письмо.',
        ])
    )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
    return True


def issue_session(user_id, username):
    issued_at = int(time.time())
    jti = secrets.token_urlsafe(18)
    account_hash = hashlib.sha256(f'{user_id}:{username}'.encode('utf-8')).hexdigest()[:30]
    payload = {
        'typ': 'rpd-session',
        'sub': str(user_id),
        'username': username,
        'jti': jti,
        'iat': issued_at,
        'exp': issued_at + AUTH_TOKEN_TTL_SECONDS,
        'account_hash': account_hash,
    }
    token = create_auth_token(payload)
    store_session_token(user_id, token, jti, issued_at)
    session.clear()
    session.permanent = False
    session['user_id'] = user_id
    session['username'] = username
    session['auth_token'] = token


def is_current_session_token(user_id, token, payload):
    user = get_user_by_id(user_id)
    if not user or not user[3] or not user[4]:
        return False
    return (
        hmac.compare_digest(user[3], token_hash(token))
        and hmac.compare_digest(user[4], str(payload.get('jti', '')))
    )


def validate_email(email):
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        return 'Введите корректный email для восстановления доступа.'
    return None


def validate_registration(username, email, password, password_confirm):
    if not re.fullmatch(r'[A-Za-zА-Яа-яЁё0-9_.-]{3,40}', username):
        return 'Логин должен содержать от 3 до 40 символов: буквы, цифры, точка, дефис или подчёркивание.'
    email_error = validate_email(email)
    if email_error:
        return email_error
    if len(password) < 8:
        return 'Пароль должен быть не короче 8 символов.'
    if password != password_confirm:
        return 'Пароли не совпадают.'
    return None

# ---------- Декоратор авторизации ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get('user_id')
        token = session.get('auth_token')
        payload = verify_auth_token(token) if token else None
        if not user_id or not token or not payload:
            session.clear()
            return redirect(url_for('login'))
        if str(user_id) != str(payload.get('sub')) or not is_current_session_token(user_id, token, payload):
            session.clear()
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------- Маршруты ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    success = request.args.get('success')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_user(username)
        if user and check_password_hash(user[2], password):
            issue_session(user[0], user[1])
            return redirect(url_for('index'))
        else:
            error = 'Неверное имя пользователя или пароль'
    return render_template('login.html', error=error, success=success)


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    error = None
    success = None
    identifier = ''
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        if not identifier:
            error = 'Введите логин или email учётной записи.'
        else:
            user = get_user_for_password_reset(identifier)
            if user and user[2]:
                reset_token = create_password_reset_token(user[0])
                reset_url = build_password_reset_url(reset_token)
                try:
                    send_password_reset_email(user[2], user[1], reset_url)
                except Exception as exc:
                    app.logger.warning('Password reset email failed for %s: %s', user[1], exc)
            success = (
                'Если учётная запись найдена и к ней привязан email, '
                'мы отправили ссылку для восстановления пароля.'
            )
    return render_template('forgot_password.html', error=error, success=success, identifier=identifier)


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    reset_user = get_password_reset_user(token)
    if not reset_user:
        return render_template(
            'reset_password.html',
            token_valid=False,
            error='Ссылка восстановления недействительна или срок её действия истёк.'
        )

    error = None
    if request.method == 'POST':
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        if len(password) < 8:
            error = 'Пароль должен быть не короче 8 символов.'
        elif password != password_confirm:
            error = 'Пароли не совпадают.'
        else:
            update_user_password(reset_user[1], password)
            mark_password_reset_token_used(reset_user[0])
            session.clear()
            return redirect(url_for('login', success='Пароль обновлён. Войдите с новым паролем.'))

    return render_template(
        'reset_password.html',
        token_valid=True,
        token=token,
        username=reset_user[2],
        error=error
    )


@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('register_username', '').strip()
    email = request.form.get('register_email', '').strip().lower()
    password = request.form.get('register_password', '')
    password_confirm = request.form.get('register_password_confirm', '')
    error = validate_registration(username, email, password, password_confirm)
    if error:
        return render_template(
            'login.html',
            error=None,
            register_error=error,
            register_username=username,
            register_email=email
        )
    ok, error = create_user(username, password, email)
    if not ok:
        return render_template(
            'login.html',
            error=None,
            register_error=error,
            register_username=username,
            register_email=email
        )
    user = get_user(username)
    issue_session(user[0], user[1])
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id:
        clear_session_token(user_id)
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('select_template.html', username=session.get('username'))


@app.route('/ai-assistant', methods=['POST'])
@login_required
def ai_assistant():
    payload = request.get_json(silent=True) or {}
    action = compact_text(payload.get('action'))

    if action == 'suggest_text':
        return jsonify(ai_response_with_external(
            action,
            payload,
            local_ai_suggest_text,
            '{"text": "готовая формулировка для поля"}',
        ))

    if action == 'check_document':
        return jsonify(ai_response_with_external(
            action,
            payload,
            local_ai_check_document,
            '{"issues": ["замечание"], "suggestions": ["рекомендация"]}',
        ))

    if action == 'generate_kos':
        fallback = local_ai_generate_kos(payload)
        external = call_external_ai(
            action,
            payload,
            (
                '{"data": {"questions": ["вопрос"], '
                '"test_examples": [{"question": "тестовое задание", "answers": ["а", "б", "в", "г"]}], '
                '"tickets": [{"questions": ["вопрос 1", "вопрос 2"]}], '
                '"control_works": [{"topic": "тема", "variants": [{"tasks": [{"text": "задача", "answers": ["а", "б", "в", "г"]}]}]}], '
                '"kos_results": [{"code": "ПК 1.1", "items": [{"result_code": "З1", "result_name": "результат обучения"}]}]}}'
            ),
        )
        if isinstance(external, dict):
            external.setdefault('ok', True)
            external.setdefault('source', 'ai')
            return jsonify(normalize_generated_kos_response(external, fallback))
        return jsonify(fallback)

    if action == 'formula':
        return jsonify(ai_response_with_external(
            action,
            payload,
            local_ai_formula,
            '{"latex": "\\\\frac{a}{b}"}',
        ))

    return jsonify({'ok': False, 'error': 'Неизвестное действие ИИ-помощника.'}), 400


@app.route('/template/prof')
@login_required
def prof_form():
    return render_template(
        'prof_form.html',
        competency_indices=OP_COMPETENCY_INDICES,
        competency_indices_by_type={
            'ОП': OP_COMPETENCY_INDICES,
            'СГ': SG_COMPETENCY_INDICES,
        },
        discipline_type_options=PROF_DISCIPLINE_TYPES,
    )

@app.route('/template/mdk')
@login_required
def mdk_form():
    return render_template(
        'mdk_form.html',
        mdk_indices=MDK_COMPETENCY_INDICES,
        professional_modules=MDK_PROFESSIONAL_MODULES,
        pc_options=MDK_PROFESSIONAL_COMPETENCIES,
    )


@app.route('/template/prac')
@login_required
def prac_form():
    return render_template('prac_form.html')


@app.route('/study-plan-hours', methods=['GET', 'POST'])
@login_required
def study_plan_hours():
    index = (
        request.form.get('index')
        or request.args.get('index')
        or request.form.get('competency_index')
        or request.args.get('competency_index')
        or ''
    ).strip()
    try:
        data = parse_study_plan_workbook()
    except FileNotFoundError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 404
    except RuntimeError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 500
    except Exception as exc:
        app.logger.warning('Study plan parser failed: %s', exc)
        return jsonify({'ok': False, 'error': 'Не удалось прочитать учебный план. Проверьте формат Excel-файла.'}), 400

    if index:
        normalized_index = normalize_study_plan_index(index)
        item = data['items'].get(normalized_index)
        if not item:
            return jsonify({
                'ok': False,
                'error': f'Индекс {index} не найден в учебном плане.',
                'source': data['source'],
            }), 404
        return jsonify({
            'ok': True,
            'source': data['source'],
            'index': normalized_index,
            'item': item,
        })

    return jsonify({
        'ok': True,
        'source': data['source'],
        'items': list(data['items'].values()),
    })


@app.route('/generate', methods=['POST'])
@login_required
def generate_document():
    template_type = request.form.get('template')

    # --- Учебная / производственная практика (HTML + DOCX/PDF) ---
    if template_type == 'prac':
        speciality = request.form.get('speciality', '').strip()
        speciality_name = request.form.get('speciality_name', '').strip()
        speciality_display = ' '.join(part for part in (speciality, speciality_name) if part)
        practice_kind = request.form.get('practice_kind', 'учебной').strip() or 'учебной'
        practice_kind_lower = practice_kind.lower()
        practice_kind_sentence = 'Производственная' if 'производ' in practice_kind_lower else 'Учебная'
        professional_module_index = request.form.get('professional_module_index', '').strip()
        professional_module_name = request.form.get('professional_module_name', '').strip()
        professional_module_display = ' '.join(
            part for part in (professional_module_index, f'«{professional_module_name}»' if professional_module_name else '')
            if part
        )
        practice_task_values = request.form.getlist('practice_task')
        if practice_task_values:
            practice_tasks = [
                value.strip(' \t\r\n–-') for value in practice_task_values
                if value.strip(' \t\r\n–-')
            ]
        else:
            raw_practice_tasks = request.form.get('practice_tasks', '')
            practice_tasks = [
                line.strip(' \t\r\n–-') for line in raw_practice_tasks.splitlines()
                if line.strip(' \t\r\n–-')
            ]
        practice_pk_codes = request.form.getlist('practice_pk_code')
        practice_pk_descs = request.form.getlist('practice_pk_desc')
        practice_pk_competencies = [
            {'code': code.strip(), 'desc': desc.strip()}
            for code, desc in zip(practice_pk_codes, practice_pk_descs)
            if code.strip() or desc.strip()
        ][:100]

        def clean_practice_list(field_name, limit=100):
            items = []
            for value in request.form.getlist(field_name):
                text = ' '.join(value.split())
                if text:
                    items.append(text)
            return items[:limit]

        practice_eval_results = request.form.getlist('practice_eval_result')
        practice_eval_criteria = request.form.getlist('practice_eval_criteria')
        practice_eval_methods = request.form.getlist('practice_eval_method')
        practice_evaluation_rows = []
        for result, criteria, method in zip(practice_eval_results, practice_eval_criteria, practice_eval_methods):
            result_text = ' '.join(result.split())
            criteria_text = ' '.join(criteria.split())
            method_text = ' '.join(method.split())
            if result_text or criteria_text or method_text:
                practice_evaluation_rows.append({
                    'result': result_text,
                    'criteria': criteria_text,
                    'method': method_text,
                })
        practice_evaluation_rows = practice_evaluation_rows[:100]

        def format_practice_hours(value):
            value = (value or '').strip()
            if not value:
                return '', 0
            normalized = value.replace(',', '.')
            try:
                number = float(normalized)
            except ValueError:
                return value, 0
            if number.is_integer():
                return str(int(number)), number
            return normalized.rstrip('0').rstrip('.'), number

        practice_stage_groups = []
        practice_stage_total = 0
        for stage_index in range(1, 4):
            stage_title = request.form.get(f'practice_stage_{stage_index}_title', '').strip()
            works = request.form.getlist(f'practice_stage_{stage_index}_work')
            hours_values = request.form.getlist(f'practice_stage_{stage_index}_hours')
            codes_values = request.form.getlist(f'practice_stage_{stage_index}_codes')
            row_count = max(len(works), len(hours_values), len(codes_values))
            stage_rows = []
            for row_index in range(row_count):
                work = works[row_index].strip() if row_index < len(works) else ''
                work_lines = [line.strip() for line in work.splitlines() if line.strip()]
                hours_raw = hours_values[row_index].strip() if row_index < len(hours_values) else ''
                codes = codes_values[row_index].strip() if row_index < len(codes_values) else ''
                if not (work or hours_raw or codes):
                    continue
                hours_display, hours_number = format_practice_hours(hours_raw)
                practice_stage_total += hours_number
                stage_rows.append({
                    'work': work,
                    'work_lines': work_lines,
                    'hours': hours_display,
                    'codes': codes,
                })
            if stage_title and stage_rows:
                practice_stage_groups.append({
                    'title': stage_title,
                    'rows': stage_rows,
                })
        practice_stage_total_hours = (
            str(int(practice_stage_total))
            if float(practice_stage_total).is_integer()
            else f'{practice_stage_total:.2f}'.rstrip('0').rstrip('.')
        )
        if 'производ' in practice_kind_lower:
            practice_goal_paragraph = (
                'Целью производственной практики (по профилю специальности)'
                f' по профессиональному модулю {professional_module_display} является формирование у обучающихся'
                ' общих и профессиональных компетенций, соответствующих виду профессиональной деятельности,'
                ' приобретение практического опыта работы по специальности.'
            )
        else:
            practice_goal_paragraph = (
                'Целью учебной практики является формирование у обучающихся умений,'
                ' приобретение первоначального практического опыта для последующего освоения общих'
                ' и профессиональных компетенций по специальности.'
            )
        approval_name = request.form.get('approval_name', '').strip()
        approval_position = request.form.get('approval_position', '').strip()
        approval_workplace = request.form.get('approval_workplace', '').strip()
        approval_person = ', '.join(
            part for part in (approval_name, approval_position, approval_workplace) if part
        )

        context = {
            'template_kind': request.form.get('template_kind', 'practice').strip(),
            'practice_kind_text': practice_kind,
            'practice_kind_title': practice_kind.upper(),
            'practice_kind_sentence': practice_kind_sentence,
            'speciality': speciality,
            'speciality_name': speciality_name,
            'speciality_display': speciality_display,
            'study_form': request.form.get('study_form', 'очная').strip() or 'очная',
            'year': request.form.get('year', '').strip(),
            'practice_semester': request.form.get('practice_semester', '').strip(),
            'practice_hours': request.form.get('practice_hours', '').strip(),
            'practice_weeks': request.form.get('practice_weeks', '').strip(),
            'practice_delivery': request.form.get('practice_delivery', 'концентрированно').strip() or 'концентрированно',
            'professional_module_index': professional_module_index,
            'professional_module_name': professional_module_name,
            'professional_module_display': professional_module_display,
            'practice_goal_paragraph': practice_goal_paragraph,
            'practice_tasks': practice_tasks,
            'practice_main_activity': request.form.get('practice_main_activity', '').strip(),
            'practice_experience': request.form.get('practice_experience', '').strip(),
            'practice_skills': request.form.get('practice_skills', '').strip(),
            'practice_pk_competencies': practice_pk_competencies,
            'practice_stage_groups': practice_stage_groups,
            'practice_stage_total_hours': practice_stage_total_hours,
            'practice_assignments': clean_practice_list('practice_assignment'),
            'practice_rooms': clean_practice_list('practice_room'),
            'practice_main_literature': clean_practice_list('practice_main_lit'),
            'practice_additional_literature': clean_practice_list('practice_additional_lit'),
            'practice_electronic_resources': clean_practice_list('practice_electronic_resource'),
            'practice_normative_docs': clean_practice_list('practice_normative_doc'),
            'practice_evaluation_rows': practice_evaluation_rows,
            'practice_places': clean_practice_list('practice_place'),
            'order_day': request.form.get('order_day', '24').strip() or '24',
            'order_month': request.form.get('order_month', 'декабря').strip() or 'декабря',
            'order_year': request.form.get('order_year', '2024').strip() or '2024',
            'order_number': request.form.get('order_number', '1025').strip() or '1025',
            'developer_name': request.form.get('developer_name', '').strip(),
            'developer_position': request.form.get('developer_position', '').strip(),
            'protocol_number': request.form.get('protocol_number', '2').strip() or '2',
            'protocol_day': request.form.get('protocol_day', '25').strip() or '25',
            'protocol_month': request.form.get('protocol_month', 'ноября').strip() or 'ноября',
            'protocol_year': request.form.get('protocol_year', '2025').strip() or '2025',
            'cmk_chair': request.form.get('cmk_chair', '').strip(),
            'approval_name': approval_name,
            'approval_position': approval_position,
            'approval_workplace': approval_workplace,
            'approval_person': approval_person,
        }

        template_path = os.path.join(TEMPLATE_DOCS_DIR, 'prac_template.html')
        if not os.path.exists(template_path):
            return "Ошибка: файл шаблона prac_template.html не найден.", 500

        with open(template_path, 'r', encoding='utf-8') as f:
            html_template_str = f.read()

        jinja_template = Template(html_template_str)
        rendered_html = jinja_template.render(build_docx_context(context))
        rendered_pdf_html = jinja_template.render(build_pdf_context(context))

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"prac_{session['user_id']}_{timestamp}"

        docx_binary = docxifier_from_html_string(rendered_html)
        docx_filename = base_filename + '.docx'
        docx_path = os.path.join(GENERATED_DIR, docx_filename)
        docx_bytes = fix_docx_fractions(docx_binary.read())
        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        pdf_filename = base_filename + '.pdf'
        pdf_path = os.path.join(GENERATED_DIR, pdf_filename)
        weasyprint_exe = r"C:\Users\Windows\Desktop\ДИПЛОМ\weasyprint.exe"

        with open(pdf_path, 'wb') as pdf_file:
            result = subprocess.run(
                [weasyprint_exe, '-', '-'],
                input=rendered_pdf_html,
                stdout=pdf_file,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )

        if result.returncode != 0:
            app.logger.error(f"WeasyPrint error: {result.stderr}")

        return render_template(
            'download_link.html',
            docx_filename=docx_filename,
            pdf_filename=pdf_filename,
            template_label='Рабочая программа учебной (производственной) практики',
        )

    # --- Междисциплинарный курс (HTML + DOCX/PDF) ---
    if template_type == 'mdk':
        speciality = request.form.get('speciality', '').strip()
        speciality_name = request.form.get('speciality_name', '').strip()
        speciality_display = ' '.join(part for part in (speciality, speciality_name) if part)

        mdk_index = request.form.get('mdk_index', '').strip()
        discipline_name = request.form.get('discipline_name', '').strip()
        module_code = request.form.get('professional_module', 'ПМ.01').strip() or 'ПМ.01'
        module_title = MDK_PROFESSIONAL_MODULES.get(module_code, '')
        mdk_activities = parse_mdk_activities(request.form.get('mdk_activities_json', ''))
        mdk_pc_results = parse_mdk_pc_results(
            request.form.get('mdk_pc_results_json', ''),
            mdk_activities,
        )

        context = {
            'discipline_type': 'МДК',
            'mdk_index': mdk_index,
            'competency_index': mdk_index,
            'discipline_name': discipline_name,
            'mdk_title': ' '.join(part for part in (mdk_index, discipline_name) if part),
            'mdk_title_quoted': f'{mdk_index} «{discipline_name}»' if discipline_name else mdk_index,
            'professional_module': module_code,
            'professional_module_title': module_title,
            'professional_module_display': ' '.join(part for part in (module_code, module_title) if part),
            'professional_module_display_quoted': f'{module_code} «{module_title}»' if module_title else module_code,
            'speciality': speciality,
            'speciality_name': speciality_name,
            'speciality_display': speciality_display,
            'course_goal': request.form.get('course_goal', '').strip(),
            'mdk_activities': mdk_activities,
            'mdk_pc_results': mdk_pc_results,
            'mdk_workload_rows': build_mdk_workload(request.form),
            'mdk_thematic_plan': parse_mdk_thematic_plan(request.form.get('mdk_thematic_plan_json', '')),
            'mdk_rooms': parse_mdk_rooms(request.form.get('mdk_rooms_json', '')),
            'mdk_sources': parse_mdk_sources(request.form.get('mdk_sources_json', '')),
            'mdk_assessments': parse_mdk_assessments(request.form.get('mdk_assessment_json', ''), mdk_activities),
            'mdk_kos_results': parse_mdk_kos_results(request.form.get('mdk_kos_results_json', ''), mdk_activities),
            'mdk_kos_questions': parse_mdk_kos_questions(request.form.get('mdk_kos_questions_json', '')),
            'mdk_kos_tickets': parse_mdk_kos_tickets(request.form.get('mdk_kos_tickets_json', '')),
            'year': request.form.get('year', '').strip(),
            'order_day': request.form.get('order_day', '24').strip() or '24',
            'order_month': request.form.get('order_month', 'декабря').strip() or 'декабря',
            'order_year': request.form.get('order_year', '2024').strip() or '2024',
            'order_number': request.form.get('order_number', '1025').strip() or '1025',
            'protocol_number': request.form.get('protocol_number', '2').strip() or '2',
            'protocol_day': request.form.get('protocol_day', '25').strip() or '25',
            'protocol_month': request.form.get('protocol_month', 'ноября').strip() or 'ноября',
            'protocol_year': request.form.get('protocol_year', '2025').strip() or '2025',
            'developer_name': request.form.get('developer_name', '').strip(),
            'developer_position': request.form.get('developer_position', '').strip(),
            'pcc_chair': request.form.get('pcc_chair', '').strip(),
        }

        template_path = os.path.join(TEMPLATE_DOCS_DIR, 'mdk_template.html')
        if not os.path.exists(template_path):
            return "Ошибка: файл шаблона mdk_template.html не найден.", 500

        with open(template_path, 'r', encoding='utf-8') as f:
            html_template_str = f.read()

        jinja_template = Template(html_template_str)
        rendered_html = jinja_template.render(build_docx_context(context))
        rendered_pdf_html = jinja_template.render(build_pdf_context(context))

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"mdk_{session['user_id']}_{timestamp}"

        docx_binary = docxifier_from_html_string(rendered_html)
        docx_filename = base_filename + '.docx'
        docx_path = os.path.join(GENERATED_DIR, docx_filename)
        docx_bytes = fix_docx_fractions(docx_binary.read())
        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        pdf_filename = base_filename + '.pdf'
        pdf_path = os.path.join(GENERATED_DIR, pdf_filename)
        weasyprint_exe = r"C:\Users\Windows\Desktop\ДИПЛОМ\weasyprint.exe"

        with open(pdf_path, 'wb') as pdf_file:
            result = subprocess.run(
                [weasyprint_exe, '-', '-'],
                input=rendered_pdf_html,
                stdout=pdf_file,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )

        if result.returncode != 0:
            app.logger.error(f"WeasyPrint error: {result.stderr}")

        return render_template(
            'download_link.html',
            docx_filename=docx_filename,
            pdf_filename=pdf_filename,
            template_label='Рабочая программа междисциплинарного курса (МДК)',
        )

    # --- Профессиональный шаблон (HTML + DOCX/PDF) ---
    elif template_type == 'prof':
        # --- Сбор данных из формы ---
        speciality = request.form['speciality'].strip()
        speciality_name = request.form.get('speciality_name', '').strip()
        speciality_display = ' '.join(part for part in (speciality, speciality_name) if part)

        discipline_type = request.form.get('discipline_type', 'ОП').strip()
        if discipline_type not in PROF_DISCIPLINE_TYPES:
            discipline_type = 'ОП'

        context = {
            'discipline_type': discipline_type,
            'discipline_type_label': PROF_DISCIPLINE_TYPES[discipline_type]['label'],
            'competency_index': request.form.get('competency_index', '').strip(),
            'discipline_name': request.form['discipline_name'].strip(),
            'speciality': speciality,
            'speciality_name': speciality_name,
            'speciality_display': speciality_display,
            'order_day': request.form.get('order_day', '24').strip() or '24',
            'order_month': request.form.get('order_month', 'декабря').strip() or 'декабря',
            'order_year': request.form.get('order_year', '2024').strip() or '2024',
            'order_number': request.form.get('order_number', '1025').strip() or '1025',
            'protocol_number': request.form.get('protocol_number', '3').strip() or '3',
            'protocol_day': request.form.get('protocol_day', '20').strip() or '20',
            'protocol_month': request.form.get('protocol_month', 'ноября').strip() or 'ноября',
            'protocol_year': request.form.get('protocol_year', '2025').strip() or '2025',
            'year': request.form['year'],
        }

        # Часы (раздел 2.1)
        hours_lecture = int(request.form.get('hours_lecture', 0))
        hours_practice = int(request.form.get('hours_practice', 0))
        hours_self = int(request.form.get('hours_self', 0))
        hours_exam = int(request.form.get('hours_exam', 0))
        hours_total = hours_lecture + hours_practice + hours_self + hours_exam
        context['hours'] = {
            'total': str(hours_total),
            'lecture': str(hours_lecture),
            'practice': str(hours_practice),
            'self': str(hours_self),
            'exam': str(hours_exam)
        }

        # Результаты (1.2)
        results = []
        i = 0
        while f'result_code_{i}' in request.form:
            code = request.form[f'result_code_{i}'].strip()
            desc = request.form.get(f'result_desc_{i}', '').strip()
            skills = []
            knowledge = []
            for j in range(3):
                skill = request.form.get(f'skill_{i}_{j}', '').strip()
                if skill:
                    skills.append(skill)
                know = request.form.get(f'knowledge_{i}_{j}', '').strip()
                if know:
                    knowledge.append(know)
            # Добавляем только если есть код, описание, хотя бы одно умение и одно знание
            if code and desc and skills and knowledge:
                max_len = max(len(skills), len(knowledge))
                # Формируем текст для ячейки: "ОК.01\nОписание"
                results.append({
                    'code_desc': f"{code}\n{desc}",
                    'skills': skills,
                    'knowledge': knowledge,
                    'max_len': max_len
                })
            i += 1
        context['results'] = results

        # Контроль и оценка результатов освоения учебной дисциплины (раздел 5)

        sec5_result_skills = (
            "доказывать математические утверждения\n"
            "выполнять основные операции над булевыми функциями\n"
            "строить логические схемы\n"
            "вычислять основные элементы рекуррентных последовательностей\n"
            "решать задачи с использованием рекуррентных отношений\n"
            "выполнять построение графов и реализовывать простейшие операции над ними\n"
            "строить подграфы для данного графа\n"
            "строить минимальное остовное дерево с использованием алгоритмов Прима и Краскала\n"
            "находить кратчайший путь в графе\n"
            "выполнять обход графа\n"
            "производить анализ графовой модели"
        )

        sec5_result_knowledge = (
            "основные методы доказательства математических теорем\n"
            "основные понятия булевой алгебры\n"
            "понятие логической схемы\n"
            "определение рекуррентной последовательности\n"
            "линейное рекуррентное отношение\n"
            "основные подходы к моделированию рекуррентных отношений\n"
            "основные понятия, связанные с графами\n"
            "понятие подграфа для данного графа\n"
            "понятие эйлерова графа и гамильтонова графа\n"
            "основные подходы, связанные с построением графовой модели\n"
            "понятие взвешенного графа и минимального остовного дерева\n"
            "основные подходы к решению задачи нахождения кратчайшего пути в графе"
        )

        criteria_map = {
            "excellent": "«Отлично» - теоретическое содержание курса освоено полностью, без пробелов, умения сформированы, все предусмотренные программой учебные задания выполнены, качество их выполнения оценено высоко.",
            "good": "«Хорошо» - теоретическое содержание курса освоено полностью, без пробелов, некоторые умения сформированы недостаточно, все предусмотренные программой учебные задания выполнены, некоторые виды заданий выполнены с ошибками.",
            "satisfactory": "«Удовлетворительно» - теоретическое содержание курса освоено частично, но пробелы не носят существенного характера, необходимые умения работы с освоенным материалом в основном сформированы, большинство предусмотренных программой обучения учебных заданий выполнено, некоторые из выполненных заданий содержат ошибки.",
            "unsatisfactory": "«Неудовлетворительно» - теоретическое содержание курса не освоено, необходимые умения не сформированы, выполненные учебные задания содержат грубые ошибки."
        }

        selected_criteria = request.form.getlist('sec5_criteria[]')
        selected_methods = request.form.getlist('sec5_methods[]')

        context['sec5_result_skills'] = sec5_result_skills
        context['sec5_result_knowledge'] = sec5_result_knowledge
        context['sec5_criteria'] = [criteria_map[key] for key in selected_criteria if key in criteria_map]
        context['sec5_methods'] = selected_methods

        def normalize_multiline(value):
            return "\n".join(
                line.strip()
                for line in value.splitlines()
                if line.strip()
            )


        # КОС результаты
        kos_results = []

        kos_group_indexes = sorted(
            {
                key.replace('kos_ok_', '')
                for key in request.form.keys()
                if key.startswith('kos_ok_')
            },
            key=lambda x: int(x) if x.isdigit() else 0
        )

        for group_idx in kos_group_indexes:
            ok_code = normalize_multiline(request.form.get(f'kos_ok_{group_idx}', ''))

            if not ok_code:
                continue

            item_indexes = sorted(
                {
                    key.replace(f'kos_rescode_{group_idx}_', '')
                    for key in request.form.keys()
                    if key.startswith(f'kos_rescode_{group_idx}_')
                },
                key=lambda x: int(x) if x.isdigit() else 0
            )

            items = []

            for item_idx in item_indexes:
                rescode = normalize_multiline(request.form.get(f'kos_rescode_{group_idx}_{item_idx}', ''))
                desc = normalize_multiline(request.form.get(f'kos_desc_{group_idx}_{item_idx}', ''))

                if rescode or desc:
                    items.append({
                        'rescode': rescode,
                        'desc': desc
                    })

            if items:
                kos_results.append({
                    'code': ok_code,
                    'items': items
                })

        context['kos_results'] = kos_results

        # Тематический план (2.2) – новая структура с поддержкой практических и самостоятельных работ
        sections = []
        section_idx = 0
        while f'section_title_{section_idx}' in request.form:
            section_title = request.form.get(f'section_title_{section_idx}', '').strip()
            if not section_title:
                section_idx += 1
                continue
            topics = []
            topic_idx = 0
            # Собираем темы в разделе
            while f'topic_title_{section_idx}_{topic_idx}' in request.form:
                topic_title = request.form.get(f'topic_title_{section_idx}_{topic_idx}', '').strip()
                if not topic_title:
                    topic_idx += 1
                    continue
        
                # Обязательное содержание
                topic_content = request.form.get(f'topic_content_{section_idx}_{topic_idx}', '').strip()
                topic_hours = int(request.form.get(f'topic_hours_{section_idx}_{topic_idx}', 0) or 0)
        
                # Опционально: практическое занятие
                practical_content = request.form.get(f'practical_content_{section_idx}_{topic_idx}', '').strip()
                practical_hours = int(request.form.get(f'practical_hours_{section_idx}_{topic_idx}', 0) or 0)
        
                # Опционально: самостоятельная работа
                selfwork_content = request.form.get(f'selfwork_content_{section_idx}_{topic_idx}', '').strip()
                selfwork_hours = int(request.form.get(f'selfwork_hours_{section_idx}_{topic_idx}', 0) or 0)
        
                # Формируем список пунктов для темы
                items = []
                if topic_content:
                    items.append({
                        'type': 'content',
                        'description': topic_content,
                        'hours': topic_hours
                    })
                if practical_content:
                    items.append({
                        'type': 'practical',
                        'description': practical_content,
                        'hours': practical_hours
                    })

                if selfwork_content:
                    items.append({
                        'type': 'selfwork',
                        'description': selfwork_content,
                        'hours': selfwork_hours
                    })
        
                if items:  # если есть хотя бы содержание (должно быть по логике)
                    topics.append({
                        'title': topic_title,
                        'items': items
                    })
                topic_idx += 1
    
            if topics:
                sections.append({
                    'title': section_title,
                    'topics': topics
                })
            section_idx += 1

        # Вычисляем общее количество часов по всем темам и сумму для каждого раздела
        total_hours_sum = 0
        for section in sections:
            section_total = 0
            for topic in section['topics']:
                for item in topic['items']:
                    section_total += item['hours']
            section['section_total_hours'] = section_total
            total_hours_sum += section_total

        context['sections'] = sections
        context['total_hours_sum'] = total_hours_sum

        # Литература
        context['basic_lit'] = request.form.getlist('basic_lit[]')
        context['additional_lit'] = request.form.getlist('additional_lit[]')
        context['el_res'] = request.form.getlist('el_res[]')

        # Вопросы, тесты, задания
        context['oral_questions'] = [
            normalize_formula_text(q)
            for q in request.form.getlist('oral_question[]')
            if q.strip()
        ]
        test_questions = request.form.getlist('test_question[]')
        test_answer_a = request.form.getlist('test_answer_a[]')
        test_answer_b = request.form.getlist('test_answer_b[]')
        test_answer_c = request.form.getlist('test_answer_c[]')
        test_answer_d = request.form.getlist('test_answer_d[]')
        test_examples = []

        for index, question in enumerate(test_questions):
            question = normalize_formula_text(question)
            answers = [
                {'label': 'а', 'text': normalize_formula_text(test_answer_a[index]) if index < len(test_answer_a) else ''},
                {'label': 'б', 'text': normalize_formula_text(test_answer_b[index]) if index < len(test_answer_b) else ''},
                {'label': 'в', 'text': normalize_formula_text(test_answer_c[index]) if index < len(test_answer_c) else ''},
                {'label': 'г', 'text': normalize_formula_text(test_answer_d[index]) if index < len(test_answer_d) else ''},
            ]

            if question or any(answer['text'] for answer in answers):
                test_examples.append({
                    'question': question,
                    'answers': answers,
                })

        if not test_examples:
            test_examples = [
                {'question': normalize_formula_text(test), 'answers': []}
                for test in request.form.getlist('test_example[]')
                if test.strip()
            ]

        context['test_examples'] = test_examples
        context['practical_examples'] = request.form.getlist('practical_example[]')

        control_works = []
        control_work_indexes = sorted(
            {
                key.replace('control_topic_', '')
                for key in request.form.keys()
                if key.startswith('control_topic_')
            },
            key=lambda x: int(x) if x.isdigit() else 0
        )

        for work_idx in control_work_indexes:
            topic = normalize_formula_text(request.form.get(f'control_topic_{work_idx}', ''))
            variants = []
            variant_indexes = sorted(
                {
                    key.replace(f'control_variant_marker_{work_idx}_', '')
                    for key in request.form.keys()
                    if key.startswith(f'control_variant_marker_{work_idx}_')
                },
                key=lambda x: int(x) if x.isdigit() else 0
            )

            for variant_idx in variant_indexes:
                tasks = []
                task_indexes = sorted(
                    {
                        key.replace(f'control_task_{work_idx}_{variant_idx}_', '')
                        for key in request.form.keys()
                        if key.startswith(f'control_task_{work_idx}_{variant_idx}_')
                    },
                    key=lambda x: int(x) if x.isdigit() else 0
                )

                for task_idx in task_indexes:
                    task_text = normalize_formula_text(
                        request.form.get(f'control_task_{work_idx}_{variant_idx}_{task_idx}', '')
                    )
                    answers = []

                    for answer_idx, label in enumerate(('а', 'б', 'в', 'г')):
                        answer_text = normalize_formula_text(
                            request.form.get(f'control_answer_{work_idx}_{variant_idx}_{task_idx}_{answer_idx}', '')
                        )
                        if answer_text:
                            answers.append({
                                'label': label,
                                'text': answer_text,
                            })

                    if task_text or answers:
                        tasks.append({
                            'text': task_text,
                            'answers': answers,
                        })

                if tasks:
                    variants.append({
                        'tasks': tasks,
                    })

            if topic or variants:
                control_works.append({
                    'topic': topic,
                    'variants': variants,
                })

        context['control_works'] = control_works

        # Материально-техническое обеспечение (3.1)
        classrooms = []
        i = 0
        while f'classroom_name_{i}' in request.form:
            name = request.form.get(f'classroom_name_{i}', '').strip()
            equipment = request.form.get(f'classroom_equipment_{i}', '').strip()
            software = request.form.get(f'classroom_software_{i}', '').strip()
            if name or equipment or software:
                classrooms.append({
                    'name': name,
                    'equipment': equipment,
                    'software': software
                })
            i += 1
        context['classrooms'] = classrooms

        # Названия контрольных работ
        context['kr2_topic'] = request.form.get('kr2_topic', '')
        context['kr3_topic'] = request.form.get('kr3_topic', '')

        # --- ПРИНУДИТЕЛЬНОЕ ПРИВЕДЕНИЕ К СПИСКАМ (с рекурсивной обработкой sections) ---
        list_keys = ['results', 'sections', 'kos_results', 'basic_lit',
                     'additional_lit', 'el_res', 'oral_questions', 'test_examples',
                     'practical_examples', 'control_works']
        for key in list_keys:
            if key in context:
                if not isinstance(context[key], (list, tuple)):
                    # Если это словарь, берём его значения
                    if isinstance(context[key], dict):
                        context[key] = list(context[key].values())
                    else:
                        try:
                            context[key] = list(context[key])
                        except TypeError:
                            context[key] = []
            else:
                context[key] = []

        # Дополнительная обработка для sections: гарантируем, что items каждого раздела — список
        if 'sections' in context and isinstance(context['sections'], list):
            for sec in context['sections']:
                if not isinstance(sec.get('items'), list):
                    if 'items' in sec:
                        try:
                            sec['items'] = list(sec['items'])
                        except TypeError:
                            sec['items'] = []
                    else:
                        sec['items'] = []

        # Аналогично для results: skills и knowledge уже списки, но на всякий случай проверим
        if 'results' in context and isinstance(context['results'], list):
            for row in context['results']:
                if not isinstance(row.get('skills'), list):
                    row['skills'] = []
                if not isinstance(row.get('knowledge'), list):
                    row['knowledge'] = []

        # Логирование для отладки
        app.logger.debug(f"results: {context['results']}")
        app.logger.debug(f"sections: {context['sections']}")
        app.logger.debug(f"kos_results: {context['kos_results']}")
        app.logger.debug(f"basic_lit: {context['basic_lit']}")

        # --- Генерация HTML ---
        template_path = os.path.join(TEMPLATE_DOCS_DIR, 'prof_template.html')
        if not os.path.exists(template_path):
            return f"Ошибка: файл шаблона prof_template.html не найден.", 500

        with open(template_path, 'r', encoding='utf-8') as f:
            html_template_str = f.read()

        jinja_template = Template(html_template_str)
        rendered_html = jinja_template.render(build_docx_context(context))
        rendered_pdf_html = jinja_template.render(build_pdf_context(context))

        # Уникальное имя файла
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_filename = f"rpd_{session['user_id']}_{timestamp}"

        # --- Конвертация в DOCX ---
        docx_binary = docxifier_from_html_string(rendered_html)
        docx_filename = base_filename + '.docx'
        docx_path = os.path.join(GENERATED_DIR, docx_filename)
        docx_bytes = fix_docx_fractions(docx_binary.read())
        with open(docx_path, 'wb') as f:
            f.write(docx_bytes)

        # --- Конвертация в PDF через weasyprint.exe ---
        pdf_filename = base_filename + '.pdf'
        pdf_path = os.path.join(GENERATED_DIR, pdf_filename)

        # Путь к weasyprint.exe (измените при необходимости)
        weasyprint_exe = r"C:\Users\Windows\Desktop\ДИПЛОМ\weasyprint.exe"

        with open(pdf_path, 'wb') as pdf_file:
            result = subprocess.run(
                [weasyprint_exe, '-', '-'],
                input=rendered_pdf_html,
                stdout=pdf_file,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )

        if result.returncode != 0:
            app.logger.error(f"WeasyPrint error: {result.stderr}")

        return render_template(
            'download_link.html',
            docx_filename=docx_filename,
            pdf_filename=pdf_filename,
            template_label=PROF_DISCIPLINE_TYPES[discipline_type]['download_label'],
        )

    else:
        return "Неизвестный шаблон", 400


@app.route('/download/<filename>')
@login_required
def download_file(filename):
    safe_path = os.path.join(GENERATED_DIR, filename)
    if not os.path.exists(safe_path):
        abort(404)
    return send_file(safe_path, as_attachment=True, download_name=filename)


@app.route('/instruction')
@login_required
def instruction():
    return render_template('instruction.html')


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
