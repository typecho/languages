#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性脚本：根据 original/projects/*.po 的现有译文，生成 TMT 翻译缓存
tools/runtime/_tmt_cache.json。

目的：下次运行 `python tools/_tmt_translate.py` 时，每条词条都能直接命中
缓存并返回已有译文，从而**无需再请求腾讯云翻译 API**（节省配额、可离线重跑）。

缓存键与 _tmt_translate.py 的 TMTTranslator._cache_key 完全一致：
    f'{target}\\x00{source_text}'
其中 target 为各语言对应的 TMT 目标语言代码（见 FILE_TO_TARGET）。

注意：
  - 仅收录译文非空、且非 `lang`（语言名由脚本直接写入，不走翻译）的条目；
  - 复数条目会同时缓存 msgid 与 msgid_plural 两个键。
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _tmt_translate import (parse_po, BASE_DIR, is_safe_translation,
                            check_html_integrity)

PROJECTS_DIR = os.path.join(BASE_DIR, 'original', 'projects')
RUNTIME_DIR = os.path.join(BASE_DIR, 'tools', 'runtime')
CACHE_FILE = os.path.join(RUNTIME_DIR, '_tmt_cache.json')

# .po 文件名主干 -> TMT 目标语言代码（与 _tmt_translate.py 的 LANGUAGES 对应）
FILE_TO_TARGET = {
    'de_DE': 'de', 'en_US': 'en', 'es_ES': 'es', 'fr_FR': 'fr',
    'ja_JP': 'ja', 'ko_KR': 'ko', 'pt_BR': 'pt', 'ru_RU': 'ru',
    'tr_TR': 'tr', 'zh_TW': 'zh-TW',
}


def main():
    os.makedirs(RUNTIME_DIR, exist_ok=True)
    cache = {}

    for fn in sorted(os.listdir(PROJECTS_DIR)):
        if not fn.endswith('.po'):
            continue
        lang_code = os.path.splitext(fn)[0]
        target = FILE_TO_TARGET.get(lang_code)
        if not target:
            print(f'  （跳过未知语言，无 TMT 代码：{fn}）')
            continue

        path = os.path.join(PROJECTS_DIR, fn)
        entries, _ = parse_po(path)
        count = 0
        skipped = 0
        for e in entries:
            if e.is_header:
                continue
            if e.msgid == 'lang':
                continue  # 语言名由脚本直接写入，不走翻译，无需缓存
            pairs = []
            if e.is_plural:
                if e.msgstr and e.msgstr[0].strip():
                    pairs.append((e.msgid, e.msgstr[0]))
                if e.msgid_plural:
                    idx = 1 if len(e.msgstr) > 1 else 0
                    pairs.append((e.msgid_plural, e.msgstr[idx]))
            elif e.msgstr and e.msgstr[0].strip():
                pairs.append((e.msgid, e.msgstr[0]))

            for source, value in pairs:
                # 与 _tmt_translate.py 的缓存自检保持一致：占位符缺失或
                # HTML 标签内文字为空的译文不入库，否则下次重跑会一直命中
                # 这些坏译文，问题再也修不掉。
                if not is_safe_translation(source, value) \
                        or check_html_integrity(source, value):
                    skipped += 1
                    continue
                cache[f'{target}\x00{source}'] = value
                count += 1
        print(f'  {fn}: 写入 {count} 条缓存'
              + (f'（跳过 {skipped} 条不合格译文）' if skipped else ''))

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)

    print(f'缓存已写入：{os.path.relpath(CACHE_FILE, BASE_DIR)}'
          f'（共 {len(cache)} 条，下次翻译将直接命中、不请求 API）')


if __name__ == '__main__':
    main()
