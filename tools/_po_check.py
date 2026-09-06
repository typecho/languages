#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Typecho 语言包校验工具

检查所有 .po 文件的：
    1. 翻译完整度 —— 是否覆盖 original/messages.pot 的全部词条；
       是否仍有空译文、或与原文（简体中文）完全相同的未翻译回退项。
    2. 占位符正确性 —— 译文是否完整保留 msgid 中的
       %s / %d / %{name} / {name} / HTML 标签 / HTML 实体等占位符。
    3. POT 对齐 —— 是否存在 POT 已删除的陈旧词条（extra）。
    4. 复数表单一致性 —— 复数条目的 msgstr 数量是否与头部 Plural-Forms 一致。
    5. 中文残留 —— 非中文目标语言中是否仍混入了简体中文。
    6. HTML 结构完整性 —— 译文是否破坏了原文的 HTML 标签结构
       （如 ``<a>链接</a>`` 在译文中被清空为 ``<a></a>``，导致标签内文本丢失）。
    7. 未翻译副本 —— msgstr 与 msgid（简体中文原文）完全相同，
       疑似机器翻译遗漏、原样搬入的未翻译项。
       （繁体中文跳过：简→繁转换后与原文逐字相同是正确结果，非漏译。）

默认只检查 original/projects/（维护中、由工具链同步的语言包）。
original/achieves/ 是 2018 年的历史参考包，按设计不与当前模板同步，
默认跳过，以免把其预期的陈旧 / 缺失词条误报为问题；需要时可用
--dir achieves 显式检查。

结果输出为 JSON 报告，统一写入 tools/runtime/po_check_report.json，
同时在终端打印一份人类可读的汇总。

用法：
    python tools/_po_check.py                  # 仅检查 projects/（维护中的语言包）
    python tools/_po_check.py --dir achieves    # 额外检查 achieves/（历史参考包）
    python tools/_po_check.py --dir projects achieves  # 同时检查两者
    python tools/_po_check.py --no-json         # 只打印，不写报告文件
"""

import os
import re
import json
import sys
import argparse
from datetime import datetime, timezone, timedelta

# 复用翻译工具里的解析与占位符校验能力，避免逻辑分叉
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tmt_translate import (parse_po, count_placeholders, is_safe_translation,
                            parse_plural_forms, check_html_integrity)

# ============================================================
# 基础路径
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POT_FILE = os.path.join(BASE_DIR, 'original', 'messages.pot')
ORIGINAL_DIR = os.path.join(BASE_DIR, 'original')
# 所有运行产物（json）统一收纳在 tools/runtime/ 内
RUNTIME_DIR = os.path.join(BASE_DIR, 'tools', 'runtime')
REPORT_FILE = os.path.join(RUNTIME_DIR, '_po_check_report.json')

# 简体中文（CJK 统一表意文字）残留检测
CJK_RE = re.compile(r'[\u4e00-\u9fff]')

# 目标语言本身就是 CJK 文字（中文 / 日文 / 韩文），其正常译文里本就含
# 中日韩统一表意文字，无法可靠区分「未翻译的中文」与「本语种文字」，
# 因此这类语言跳过「中文残留」检查。
CJK_LANGS = {'zh_TW', 'zh_Hant', 'zh_CN', 'zh_cn', 'zh_Hans',
             'ja_JP', 'ja', 'ko_KR', 'ko'}

# 「未译副本」（msgstr 与简体原文完全相同）检查对繁体中文没有意义：
# 简→繁只是字形转换，大量词条（如「作者」「保存文件」「%d年」）在两岸
# 写法本就一致，转换后与原文逐字相同是**正确结果**，不是漏译。
# 因此繁体中文直接跳过该项检查；日文的汉字同理，但日文仍保留
# OpenCC 判定（见 is_verbatim_copy），只豁免纯汉字串。
VERBATIM_COPY_SKIP_LANGS = {'zh_TW', 'zh_Hant', 'zh_HK', 'zh_MO',
                            'zh-hant', 'zh-tw', 'zh-hk'}


def is_translated(entry):
    """msgstr 是否真正有译文（非空白、复数则全部非空）。"""
    if entry.is_plural:
        return all(s.strip() for s in entry.msgstr)
    return bool(entry.msgstr[0].strip())


def has_chinese(text):
    return bool(CJK_RE.search(text))


def is_verbatim_copy(msgid, msgstr, lang_code=None):
    """译文与原文（简体中文）完全相同，疑似未翻译。

    仅当原文含 CJK 表意文字时才判定，避免误报纯 ASCII 的
    URL / 专有名词 / 数字等本就应与原文一致的字符串。

    对于 zh_TW / ja_JP 等本就使用汉字的语言，若原文经
    简→繁（s2t）转换后与自身完全相同（即该串在两岸/中日
    写法一致，如「年/月/日」「提交」），说明它本就无需转换，
    视为已正确翻译，不再误报。
    """
    if not msgstr or not msgid:
        return False
    if msgstr.strip() != msgid.strip():
        return False
    if lang_code in ('zh_TW', 'ja_JP'):
        try:
            from opencc import OpenCC
            if OpenCC('s2t').convert(msgid) == msgid:
                return False
        except Exception:
            pass
    return bool(CJK_RE.search(msgid))


def check_file(po_path, pot_by_msgid):
    """校验单个 .po 文件，返回报告片段。"""
    entries, header_fields = parse_po(po_path)
    po_by_msgid = {}
    for e in entries:
        if e.is_header:
            continue
        po_by_msgid.setdefault(e.msgid, []).append(e)

    lang_code = os.path.splitext(os.path.basename(po_path))[0]
    _, nplurals = parse_plural_forms(header_fields)
    is_cjk = lang_code in CJK_LANGS
    # 繁体中文跳过「未译副本」检查（见 VERBATIM_COPY_SKIP_LANGS 说明）
    check_verbatim = lang_code not in VERBATIM_COPY_SKIP_LANGS

    result = {
        'file': os.path.relpath(po_path, BASE_DIR),
        'language': lang_code,
        'nplurals_header': nplurals,
        'total': 0,
        'translated': 0,
        'untranslated': [],
        'missing': [],
        'extra': [],
        'placeholder_issues': [],
        'chinese_residual': [],
        'plural_count_issues': [],
        'html_integrity': [],
        'untranslated_copy': [],
    }

    # 1. 以 POT 词条为准，核对完整度 / 占位符 / 中文残留
    for msgid, _pot_entry in pot_by_msgid.items():
        result['total'] += 1
        matches = po_by_msgid.get(msgid)
        if not matches:
            result['missing'].append(msgid)
            continue

        entry = matches[0]

        # 复数表单数量与头部声明一致？
        if entry.is_plural and len(entry.msgstr) != nplurals:
            result['plural_count_issues'].append({
                'msgid': msgid,
                'expected': nplurals,
                'actual': len(entry.msgstr),
            })

        if not is_translated(entry):
            result['untranslated'].append(msgid)
            continue
        result['translated'] += 1

        # 占位符完整性：逐字段比对 msgid / msgid_plural 与对应 msgstr
        sources = [entry.msgid]
        if entry.is_plural:
            sources.append(entry.msgid_plural)
        for src, tgt in zip(sources, entry.msgstr):
            if tgt and not is_safe_translation(src, tgt):
                result['placeholder_issues'].append({
                    'msgid': src,
                    'msgstr': tgt,
                })
            # HTML 结构完整性：标签内文本是否被清空（如 <a>…</a> 变空）
            if tgt:
                problems = check_html_integrity(src, tgt)
                if problems:
                    result['html_integrity'].append({
                        'msgid': src,
                        'msgstr': tgt,
                        'problems': problems,
                    })
                # 与原文完全相同的疑似未翻译项
                if check_verbatim and is_verbatim_copy(src, tgt, lang_code):
                    result['untranslated_copy'].append(src)

        # 非 CJK 语言才检查中文残留（中日韩文自身就含表意文字）
        if not is_cjk:
            for tgt in entry.msgstr:
                if has_chinese(tgt):
                    result['chinese_residual'].append({
                        'msgid': entry.msgid,
                        'msgstr': tgt,
                    })
                    break

    # 2. 陈旧词条：POT 已无、但 po 里仍存在的条目
    for e in entries:
        if e.is_header:
            continue
        if e.msgid not in pot_by_msgid:
            result['extra'].append(e.msgid)

    # 派生计数
    result['untranslated_count'] = len(result['untranslated'])
    result['missing_count'] = len(result['missing'])
    result['extra_count'] = len(result['extra'])
    result['placeholder_count'] = len(result['placeholder_issues'])
    result['chinese_count'] = len(result['chinese_residual'])
    result['plural_count'] = len(result['plural_count_issues'])
    result['html_count'] = len(result['html_integrity'])
    result['untranslated_copy_count'] = len(result['untranslated_copy'])
    result['completeness_pct'] = round(
        (result['translated'] / result['total'] * 100.0)
        if result['total'] else 0.0, 2)
    result['ok'] = not (
        result['missing_count'] or result['untranslated_count']
        or result['placeholder_count'] or result['chinese_count']
        or result['plural_count'] or result['extra_count']
        or result['html_count'] or result['untranslated_copy_count'])
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Typecho 语言包 .po 校验工具')
    parser.add_argument('--dir', nargs='*', default=['projects'],
                        help='待检查的 original/ 子目录，默认仅 projects（achieves 为历史参考包，默认跳过）')
    parser.add_argument('--no-json', action='store_true',
                        help='只打印汇总，不写入报告文件')
    args = parser.parse_args()

    if not os.path.isfile(POT_FILE):
        print(f'未找到模板文件：{POT_FILE}')
        return 1

    pot_entries, _ = parse_po(POT_FILE)
    pot_entries = [e for e in pot_entries if not e.is_header]
    pot_by_msgid = {e.msgid: e for e in pot_entries}
    print(f'模板文件：{POT_FILE}')
    print(f'POT 词条数量：{len(pot_by_msgid)}')

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    languages = []
    for sub in args.dir:
        dpath = os.path.join(ORIGINAL_DIR, sub)
        if not os.path.isdir(dpath):
            print(f'（跳过不存在的目录：{dpath}）')
            continue
        for fn in sorted(os.listdir(dpath)):
            if fn.endswith('.po'):
                print(f'检查：{os.path.relpath(os.path.join(dpath, fn), BASE_DIR)}')
                languages.append(check_file(os.path.join(dpath, fn), pot_by_msgid))

    # 汇总
    summary = {
        'files_checked': len(languages),
        'files_ok': sum(1 for r in languages if r['ok']),
        'total_untranslated': sum(r['untranslated_count'] for r in languages),
        'total_missing': sum(r['missing_count'] for r in languages),
        'total_extra': sum(r['extra_count'] for r in languages),
        'total_placeholder_issues': sum(r['placeholder_count'] for r in languages),
        'total_chinese_residual': sum(r['chinese_count'] for r in languages),
        'total_plural_issues': sum(r['plural_count'] for r in languages),
        'total_html_integrity': sum(r['html_count'] for r in languages),
        'total_untranslated_copy': sum(r['untranslated_copy_count'] for r in languages),
    }

    report = {
        'generated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'pot': os.path.relpath(POT_FILE, BASE_DIR),
        'pot_entries': len(pot_by_msgid),
        'summary': summary,
        'languages': languages,
    }

    # 终端汇总
    print()
    print('=== 校验汇总 ===')
    print(f'  检查文件数：{summary["files_checked"]}（全部通过：{summary["files_ok"]}）')
    print(f'  未翻译：{summary["total_untranslated"]}  缺失词条：{summary["total_missing"]}')
    print(f'  陈旧词条：{summary["total_extra"]}  占位符问题：{summary["total_placeholder_issues"]}')
    print(f'  中文残留：{summary["total_chinese_residual"]}  复数问题：{summary["total_plural_issues"]}')
    print(f'  HTML结构：{summary["total_html_integrity"]}  未译副本：{summary["total_untranslated_copy"]}')
    print()
    header = f'{"语言":<10}{"完整度":>9}{"未译":>7}{"缺失":>7}{"占位符":>8}{"中文":>6}{"陈旧":>6}{"复数":>6}{"HTML":>7}{"副本":>6}'
    print(header)
    print('-' * len(header))
    for r in languages:
        print(f'{r["language"]:<10}'
              f'{r["completeness_pct"]:>8}%'
              f'{r["untranslated_count"]:>7}'
              f'{r["missing_count"]:>7}'
              f'{r["placeholder_count"]:>8}'
              f'{r["chinese_count"]:>6}'
              f'{r["extra_count"]:>6}'
              f'{r["plural_count"]:>6}'
              f'{r["html_count"]:>7}'
              f'{r["untranslated_copy_count"]:>6}'
              f'{"  OK" if r["ok"] else ""}')

    if not args.no_json:
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print()
        print(f'报告已写入：{os.path.relpath(REPORT_FILE, BASE_DIR)}')

    # 有任一问题则返回一个非零退出码，便于 CI 判定
    if summary['total_untranslated'] or summary['total_missing'] \
            or summary['total_placeholder_issues'] or summary['total_chinese_residual'] \
            or summary['total_plural_issues'] or summary['total_html_integrity'] \
            or summary['total_untranslated_copy']:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
