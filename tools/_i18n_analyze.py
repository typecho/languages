#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import datetime

# ============================================================
# 配置项
# ============================================================

# Typecho 根目录（默认为当前目录）
TYPECHO_DIR = os.path.normpath(r'.')

# 扫描的目标文件扩展名（仅扫描 PHP 文件）
SOURCE_EXTENSIONS = {'.php'}

# 忽略的目录
IGNORE_DIRS = {
    '.git',
    '.svn',
    '.hg',
    'node_modules',
    'vendor',
    '__pycache__',
    'usr/uploads',  # 上传目录
    'usr/langs',    # 语言包目录
}

# 输出的 POT 文件路径
OUTPUT_POT = './original/messages.pot'


# ============================================================
# 字符串反转义与 POT 格式化
# ============================================================

def unescape_literal(lit):
    """
    将 PHP 单引号/双引号字符串字面量还原为真实字符串。
    例如:
        '"hello\\nworld"' -> 'hello\nworld'
        "'it\\'s'"         -> "it's"
    """
    lit = lit.strip()
    if len(lit) < 2:
        return lit

    quote = lit[0]
    inner = lit[1:-1]

    if quote == "'":
        inner = inner.replace(r"\'", "'").replace(r"\\", "\\")
    elif quote == '"':
        inner = (
            inner
            .replace(r'\"', '"')
            .replace(r'\n', '\n')
            .replace(r'\r', '\r')
            .replace(r'\t', '\t')
            .replace(r'\\', '\\')
        )

    return inner


def format_po_string(label, text):
    """
    将文本转换为符合 POT 规范的多行/单行格式。
    """
    escaped = (
        text
        .replace('\\', '\\\\')
        .replace('"', '\\"')
        .replace('\r', '\\r')
        .replace('\t', '\\t')
    )

    if '\n' in escaped:
        lines = escaped.split('\n')
        res = [f'{label} ""']
        for i, line in enumerate(lines):
            suffix = '\\n' if i < len(lines) - 1 else ''
            res.append(f'"{line}{suffix}"')
        return '\n'.join(res)
    else:
        return f'{label} "{escaped}"'


# ============================================================
# 去除 PHP 注释（保留行号）
# ============================================================

def strip_comments(content):
    """
    移除 //、/* ... */、# 等注释，同时保留换行符以确保代码行号精确。
    """
    result = []
    i = 0
    n = len(content)
    state = 'code'
    quote = None

    while i < n:
        ch = content[i]

        if state == 'string':
            result.append(ch)
            if ch == '\\' and i + 1 < n:
                result.append(content[i + 1])
                i += 2
                continue
            if ch == quote:
                state = 'code'
                quote = None
            i += 1
            continue

        if state == 'block_comment':
            if ch == '*' and i + 1 < n and content[i + 1] == '/':
                state = 'code'
                result.extend('  ')
                i += 2
            else:
                result.append('\n' if ch == '\n' else ' ')
                i += 1
            continue

        if state == 'line_comment':
            if ch == '\n':
                state = 'code'
                result.append('\n')
            else:
                result.append(' ')
            i += 1
            continue

        # 进入字符串
        if ch in ("'", '"'):
            state = 'string'
            quote = ch
            result.append(ch)
            i += 1
            continue

        # /* ... */ 多行注释
        if ch == '/' and i + 1 < n and content[i + 1] == '*':
            state = 'block_comment'
            result.extend('  ')
            i += 2
            continue

        # // 单行注释
        if ch == '/' and i + 1 < n and content[i + 1] == '/':
            state = 'line_comment'
            result.extend('  ')
            i += 2
            continue

        # # 单行注释 (PHP 支持)
        if ch == '#':
            state = 'line_comment'
            result.append(' ')
            i += 1
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


# ============================================================
# 提取 i18n 词条
# ============================================================

STRING_LITERAL_RE = r"""('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")"""


def find_i18n_strings(content, rel_path):
    """
    提取文件中的 _t('...'), _e('...'), _n('single', 'plural', ...)
    返回匹配项字典：
        {
            (msgid, msgid_plural): {
                'locations': [(rel_path, line_no), ...],
                'plural': str or None
            }
        }
    """
    cleaned = strip_comments(content)
    entries = {}

    # 1. 匹配 _n('one', 'many', ...)
    n_pattern = re.compile(
        rf'\b_n\s*\(\s*({STRING_LITERAL_RE})\s*,\s*({STRING_LITERAL_RE})',
        re.MULTILINE | re.DOTALL
    )

    for m in n_pattern.finditer(cleaned):
        pos = m.start()
        line_no = cleaned[:pos].count('\n') + 1
        msgid = unescape_literal(m.group(1))
        msgid_plural = unescape_literal(m.group(2))

        key = (msgid, msgid_plural)
        if key not in entries:
            entries[key] = {'locations': [], 'plural': msgid_plural}
        entries[key]['locations'].append((rel_path, line_no))

    # 2. 匹配 _t('...') / _e('...')
    single_pattern = re.compile(
        rf'\b_(?:t|e)\s*\(\s*({STRING_LITERAL_RE})',
        re.MULTILINE | re.DOTALL
    )

    for m in single_pattern.finditer(cleaned):
        pos = m.start()
        line_no = cleaned[:pos].count('\n') + 1
        msgid = unescape_literal(m.group(1))

        key = (msgid, None)
        if key not in entries:
            entries[key] = {'locations': [], 'plural': None}
        entries[key]['locations'].append((rel_path, line_no))

    return entries


# ============================================================
# 文件遍历
# ============================================================

def iter_source_files(root):
    """
    递归遍历并过滤目录
    """
    for dirpath, dirnames, filenames in os.walk(root):
        # 过滤忽略目录
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS and not any(
                os.path.normpath(os.path.join(dirpath, d)).endswith(os.path.normpath(ign))
                for ign in IGNORE_DIRS
            )
        ]

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in SOURCE_EXTENSIONS:
                yield os.path.join(dirpath, filename)


# ============================================================
# POT 生成与写入
# ============================================================

def build_pot_content(all_entries):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M%z')

    header = f'''#, fuzzy
msgid ""
msgstr ""
"Project-Id-Version: Typecho\\n"
"POT-Creation-Date: {now}\\n"
"PO-Revision-Date: YEAR-MO-DA HO:MI+ZONE\\n"
"Last-Translator: FULL NAME <EMAIL@ADDRESS>\\n"
"Language-Team: Typecho Team <team@typecho.org>\\n"
"Language: \\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=n != 1;\\n"
'''

    body = []
    # 按照字母顺序排序
    sorted_keys = sorted(all_entries.keys(), key=lambda k: k[0])

    for key in sorted_keys:
        item = all_entries[key]
        msgid, msgid_plural = key

        # 生成位置注释 #: path/file.php:123
        loc_lines = []
        for path, line in item['locations']:
            # 统一使用 POSIX 格式路径
            posix_path = path.replace('\\', '/')
            loc_lines.append(f'#: {posix_path}:{line}')

        entry_text = '\n'.join(loc_lines) + '\n'
        entry_text += format_po_string('msgid', msgid) + '\n'

        if msgid_plural:
            entry_text += format_po_string('msgid_plural', msgid_plural) + '\n'
            entry_text += 'msgstr[0] ""\n'
            entry_text += 'msgstr[1] ""\n'
        else:
            entry_text += 'msgstr ""\n'

        body.append(entry_text)

    return header + '\n' + '\n'.join(body)


# ============================================================
# 主程序
# ============================================================

def main():
    abs_typecho_dir = os.path.abspath(TYPECHO_DIR)
    print(f'=== Typecho i18n POT Generator ===')
    print(f'Root Directory : {abs_typecho_dir}')
    print(f'Output Target  : {os.path.abspath(OUTPUT_POT)}')
    print('Scanning PHP files...')

    if not os.path.isdir(TYPECHO_DIR):
        raise FileNotFoundError(f'Directory does not exist: {abs_typecho_dir}')

    all_entries = {}
    scanned_count = 0
    failed_count = 0

    for filepath in iter_source_files(TYPECHO_DIR):
        scanned_count += 1
        rel_path = os.path.relpath(filepath, TYPECHO_DIR)

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            file_entries = find_i18n_strings(content, rel_path)

            for key, val in file_entries.items():
                if key not in all_entries:
                    all_entries[key] = {
                        'locations': [],
                        'plural': val['plural']
                    }
                all_entries[key]['locations'].extend(val['locations'])

        except OSError as e:
            failed_count += 1
            print(f'Error reading {rel_path}: {e}')

    # 生成并写入 POT
    pot_content = build_pot_content(all_entries)

    with open(OUTPUT_POT, 'w', encoding='utf-8') as f:
        f.write(pot_content)

    print()
    print(f'Scan completed:')
    print(f'  - PHP files scanned : {scanned_count}')
    print(f'  - Read failures     : {failed_count}')
    print(f'  - Unique strings    : {len(all_entries)}')
    print(f'  - POT generated at  : {os.path.abspath(OUTPUT_POT)}')


if __name__ == '__main__':
    main()