#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Typecho 语言包翻译工具（基于腾讯云机器翻译 TMT）

功能：
    1. 读取 original/messages.pot（词条与源码引用注释的唯一来源）；
    2. 调用腾讯云 TMT TextTranslate 接口，把全部词条翻译为目标语言；
    3. 覆写生成各语言的 .po 文件（结构、顺序、引用注释均与 POT 保持一致）；
    4. msgid "lang" 统一写入该语言的「本语种名称」（如 en_US -> English）；
    5. 译者信息统一写入 Deyong Huang <coolerxde@gt.ac.cn>；
    6. 运行后输出 tools/_tmt_report.json，记录回退/异常的译文，便于后续补译。

用法：
    # 翻译并覆写全部语言文件
    python tools/_tmt_translate.py

    # 只处理指定语言
    python tools/_tmt_translate.py --lang en_US ja_JP ko_KR

    # 保留已有译文（仅补齐空缺），不覆写已有翻译
    python tools/_tmt_translate.py --keep-existing

    # 每个语言只翻译前 20 条（用于验证凭证与接口）
    python tools/_tmt_translate.py --lang en_US --limit 20 --no-write

凭证：
    优先读取环境变量 TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY，
    未设置时使用脚本内的默认值。
"""

import os
import re
import sys
import json
import time
import argparse
import threading
from datetime import datetime, timezone, timedelta
from collections import Counter

# ============================================================
# 基础路径
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POT_FILE = os.path.join(BASE_DIR, 'original', 'messages.pot')
PROJECTS_DIR = os.path.join(BASE_DIR, 'original', 'projects')
CACHE_FILE = os.path.join(BASE_DIR, 'tools', '_tmt_cache.json')
REPORT_FILE = os.path.join(BASE_DIR, 'tools', '_tmt_report.json')

# ============================================================
# 腾讯云凭证（可通过环境变量覆盖）
# ============================================================

SECRET_ID = os.environ.get('TENCENTCLOUD_SECRET_ID', '')
SECRET_KEY = os.environ.get('TENCENTCLOUD_SECRET_KEY', '')
REGION = os.environ.get('TENCENTCLOUD_REGION', 'ap-guangzhou')

# TMT 文本翻译接口
TMT_SERVICE = 'tmt'
TMT_VERSION = '2018-03-21'
TMT_ACTION = 'TextTranslate'

# ============================================================
# 贡献者信息
# ============================================================

TRANSLATOR_NAME = 'Deyong Huang'
TRANSLATOR_MAIL = 'coolerxde@gt.ac.cn'
TRANSLATOR = f'{TRANSLATOR_NAME} <{TRANSLATOR_MAIL}>'
GENERATOR = 'Typecho Languages TMT Tool'

# ============================================================
# 语言配置表
#   file   : 仓库根目录下的 .po 文件名
#   target : TMT 接口的目标语言代码
#   name   : msgid "lang" 对应的译文（该语言在自身语言中的名称）
# ============================================================

LANGUAGES = [
    #{'file': 'zh_TW.po',  'target': 'zh-TW', 'name': '繁體中文'},
    #{'file': 'tr_TR.po',  'target': 'tr',    'name': 'Türkçe'},
    #{'file': 'ru_RU.po',  'target': 'ru',    'name': 'Русский'},
    #{'file': 'pt_BR.po',  'target': 'pt',    'name': 'Português (Brasil)'},
    #{'file': 'ja_JP.po',  'target': 'ja',    'name': '日本語'},
    #{'file': 'ko_KR.po',  'target': 'ko',    'name': '한국어'},
    #{'file': 'fr_FR.po',  'target': 'fr',    'name': 'Français'},
    #{'file': 'es_ES.po',  'target': 'es',    'name': 'Español'},
    {'file': 'de_DE.po',  'target': 'de',    'name': 'Deutsch'},
    #{'file': 'en_US.po',  'target': 'en',    'name': 'English'},
]

# 语言代码（文件名去扩展名）-> Plural-Forms，仅在原文件缺失时使用
DEFAULT_PLURAL_FORMS = {
    'ru_RU': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && '
             '(n%100<10 || n%100>=20) ? 1 : 2);',
    'ja_JP': 'nplurals=2; plural=n==1?0:1;',
    'ko_KR': 'nplurals=2; plural=(n != 1);',
    'ug_CN': 'nplurals=2; plural=n == 1 ? 0 : 1;',
    'zh_TW': 'nplurals=2; plural=(n != 1);',
    'ceb':   'nplurals=2; plural=(n > 1);',
    'fil_PH': 'nplurals=2; plural=(n > 1);',
    'fr_FR': 'nplurals=2; plural=(n > 1);',
    'de_DE': 'nplurals=2; plural=(n != 1);',
    'pt_BR': 'nplurals=2; plural=(n > 1);',
    'fa_IR': 'nplurals=2; plural=(n==0 || n==1);',
}

DEFAULT_PLURAL_FORMS_FALLBACK = 'nplurals=2; plural=(n != 1);'

# TMT 单次请求的最大文本长度（字符数），留出安全余量
MAX_TEXT_LENGTH = 1800

# 需要被原样保留的占位符 / 标记，用于校验译文是否被翻译引擎破坏
PLACEHOLDER_PATTERNS = [
    r'%(?:\d+\$)?[sd]',      # %s / %d / %1$s
    r'%\{[^}]*\}',           # %{name}
    r'\{\{?[^}]+\}?\}',      # {name} / {{name}}
    r'</?[A-Za-z][^>]*>',    # HTML 标签
    r'&#?\w+;',              # HTML 实体
]


# ============================================================
# PO 文件读写
# ============================================================

class Entry:
    """一个 PO 词条。"""

    def __init__(self, comments=None):
        self.comments = comments or []   # 词条上方的注释行（#: 引用等）
        self.msgid = ''
        self.msgid_plural = None
        self.msgstr = ['']               # 单数为 1 项，复数按 nplurals 展开

    @property
    def is_plural(self):
        return self.msgid_plural is not None

    @property
    def is_header(self):
        return self.msgid == ''


def unescape(text):
    """还原 PO 字符串中的转义。"""
    mapping = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text) and text[i + 1] in mapping:
            out.append(mapping[text[i + 1]])
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def escape(text):
    """转义 PO 字符串。"""
    return (text
            .replace('\\', '\\\\')
            .replace('"', '\\"')
            .replace('\r', '\\r')
            .replace('\t', '\\t')
            .replace('\n', '\\n'))


def format_po_string(label, text):
    """按 PO 规范输出一行（含换行时输出多行格式）。"""
    escaped = escape(text)
    if '\n' in text:
        lines = escaped.split('\\n')
        res = [f'{label} ""']
        for i, line in enumerate(lines):
            suffix = '\\n' if i < len(lines) - 1 else ''
            res.append(f'"{line}{suffix}"')
        return '\n'.join(res)
    return f'{label} "{escaped}"'


TOKEN_RE = re.compile(r'^(msgid|msgid_plural|msgstr|msgstr\[\d+\])\s*"(.*)"\s*$')
CONT_RE = re.compile(r'^"(.*)"\s*$')


def parse_po(path):
    """
    解析 .po / .pot 文件。
    返回 (entries, header_fields)
        header_fields 为头部 msgid "" 条目的多行字段原始文本列表。
    """
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')

    entries = []
    header_fields = []
    pending_comments = []
    current = None
    state = None
    in_header = False

    for line in lines:
        stripped = line.strip()

        # 空行：结束当前词条
        if not stripped:
            if current is not None:
                entries.append(current)
                current = None
            pending_comments = []
            state = None
            in_header = False
            continue

        # 注释行
        if stripped.startswith('#'):
            if current is None:
                # 仅保留引用注释与翻译注释，丢弃废弃词条（#~）
                if not stripped.startswith('#~'):
                    pending_comments.append(stripped)
            continue

        m = TOKEN_RE.match(stripped)
        if m:
            keyword, value = m.group(1), unescape(m.group(2))
            if current is None:
                current = Entry(pending_comments)
                in_header = (keyword == 'msgid' and value == '')
            state = keyword

            if keyword == 'msgid':
                current.msgid = value
            elif keyword == 'msgid_plural':
                current.msgid_plural = value
                current.msgstr = ['', '']
            elif keyword.startswith('msgstr['):
                idx = int(keyword[len('msgstr['):-1])
                while len(current.msgstr) <= idx:
                    current.msgstr.append('')
                current.msgstr[idx] = value
            else:  # msgstr
                current.msgstr = [value]
            continue

        m = CONT_RE.match(stripped)
        if m and current is not None and state:
            value = unescape(m.group(1))
            if state == 'msgid':
                current.msgid += value
            elif state == 'msgid_plural':
                current.msgid_plural += value
            elif state.startswith('msgstr['):
                idx = int(state[len('msgstr['):-1])
                current.msgstr[idx] += value
            elif state == 'msgstr':
                if in_header:
                    header_fields.append(value)
                else:
                    current.msgstr[0] += value
            continue

    if current is not None:
        entries.append(current)

    return entries, header_fields


def parse_plural_forms(header_fields):
    """从头部字段中提取 Plural-Forms 与 nplurals。"""
    for field in header_fields:
        if field.lower().startswith('plural-forms:'):
            value = field.split(':', 1)[1].strip()
            m = re.search(r'nplurals\s*=\s*(\d+)', value)
            return value, (int(m.group(1)) if m else 2)
    return None, 2


def get_header_value(header_fields, key):
    key = key.lower()
    for field in header_fields:
        if field.lower().startswith(key + ':'):
            return field.split(':', 1)[1].strip()
    return ''


def build_header(lang_code, pot_header_fields, plural_forms, pot_creation_date):
    """生成 .po 头部文本。"""
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M%z')
    version = get_header_value(pot_header_fields, 'Project-Id-Version') or 'Typecho'

    fields = [
        f'Project-Id-Version: {version}',
        f'POT-Creation-Date: {pot_creation_date}',
        f'PO-Revision-Date: {now}',
        f'Last-Translator: {TRANSLATOR}',
        f'Language-Team: {TRANSLATOR}',
        f'Language: {lang_code}',
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
        f'Plural-Forms: {plural_forms}',
        f'X-Generator: {GENERATOR}',
    ]

    text = 'msgid ""\nmsgstr ""\n'
    text += '\n'.join(f'"{f}\\n"' for f in fields)
    return text


def dump_po(path, header_text, entries):
    """写入 .po 文件。"""
    blocks = [header_text]
    for entry in entries:
        block = []
        if entry.comments:
            block.extend(entry.comments)
        block.append(format_po_string('msgid', entry.msgid))
        if entry.is_plural:
            block.append(format_po_string('msgid_plural', entry.msgid_plural))
            for i, value in enumerate(entry.msgstr):
                block.append(format_po_string(f'msgstr[{i}]', value))
        else:
            block.append(format_po_string('msgstr', entry.msgstr[0]))
        blocks.append('\n'.join(block))

    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n\n'.join(blocks) + '\n')


# ============================================================
# 译文安全校验
# ============================================================

def count_placeholders(text):
    """统计文本中的占位符/标记数量。"""
    counter = Counter()
    for pattern in PLACEHOLDER_PATTERNS:
        for m in re.findall(pattern, text):
            counter[m] += 1
    return counter


def is_safe_translation(source, translated):
    """校验译文未丢失占位符。"""
    if not translated:
        return False
    src, dst = count_placeholders(source), count_placeholders(translated)
    for token, num in src.items():
        if dst.get(token, 0) < num:
            return False
    return True


def repair_placeholder_spacing(text):
    """修复机器翻译在占位符中插入的空格。

    机器翻译常把 ``%s`` / ``%d`` / ``{slug}`` 拆成
    ``% s`` / ``% d`` / ``{sl ug}``。这里只把**断开的占位符**拼回，
    不会改动译文里正常的词间空格。
    """
    # %s / %d / %1$s 之间被插入的空格
    text = re.sub(r'%(\s+)([sd])', r'%\2', text)
    text = re.sub(r'%(\d+)\s*\$\s*([sd])', r'%\1$\2', text)
    # {name} / {slug} 等花括号内被插入的空格
    text = re.sub(r'(\{)([^}]*?)(\})',
                  lambda m: m.group(1) + m.group(2).replace(' ', '') + m.group(3),
                  text)
    return text


# ============================================================
# 腾讯云 TMT 翻译客户端
# ============================================================

class RateLimiter:
    """简单的全局限速器（TMT TextTranslate 默认 5 次/秒）。"""

    def __init__(self, qps):
        self.interval = 1.0 / max(qps, 0.1)
        self.lock = threading.Lock()
        self.next_time = 0.0

    def acquire(self):
        with self.lock:
            now = time.time()
            wait = max(0.0, self.next_time - now)
            self.next_time = max(now, self.next_time) + self.interval
        if wait:
            time.sleep(wait)


class TMTTranslator:
    def __init__(self, qps=4.0, max_retries=3):
        from tencentcloud.common import credential
        from tencentcloud.common.common_client import CommonClient
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
            TencentCloudSDKException,
        )

        self._credential = credential.Credential(SECRET_ID, SECRET_KEY)
        self._common_client = CommonClient
        self._sdk_exception = TencentCloudSDKException
        self.limiter = RateLimiter(qps)
        self.max_retries = max_retries
        self.local = threading.local()

        self.cache = {}
        self.cache_dirty = 0
        self.cache_lock = threading.Lock()
        self._load_cache()

        self.stats = Counter()
        self.unsupported_targets = set()
        self.print_lock = threading.Lock()
        # 回退/修复事件，用于生成翻译报告（见 _tmt_report.json）
        self.fallback_events = []
        self.report_lock = threading.Lock()

    # ---------- 缓存 ----------

    def _load_cache(self):
        if os.path.isfile(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except (ValueError, OSError):
                self.cache = {}

    def save_cache(self, force=False):
        with self.cache_lock:
            if not self.cache_dirty and not force:
                return
            tmp = CACHE_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=0)
            os.replace(tmp, CACHE_FILE)
            self.cache_dirty = 0

    @staticmethod
    def _cache_key(target, text):
        return f'{target}\x00{text}'

    # ---------- 客户端 ----------

    def _client(self):
        # 新版 SDK 已移除 TMT 的 TextTranslate 类型化模型，
        # 这里用官方 CommonClient 直接按 Action 调用（签名、重试、错误处理均由 SDK 负责）。
        client = getattr(self.local, 'client', None)
        if client is None:
            client = self._common_client('tmt', TMT_VERSION,
                                         self._credential, REGION)
            self.local.client = client
        return client

    def log(self, message):
        with self.print_lock:
            print(message, flush=True)

    def _record_fallback(self, target, source, raw_tmt, reason):
        """记录一条回退事件（接口失败 / 占位符被破坏），供报告使用。"""
        with self.report_lock:
            self.fallback_events.append({
                'target': target,
                'source': source,
                'raw_tmt': raw_tmt,
                'reason': reason,
            })

    def drain_fallback_events(self):
        """取出并清空累计的回退事件。"""
        with self.report_lock:
            events = self.fallback_events
            self.fallback_events = []
        return events

    def translate(self, text, target):
        """翻译单条文本。

        返回译文；若接口报错或译文占位符不完整，则回退为原文（source）。
        回退与「占位符被机翻断开后自动修复」都会记入报告，便于后续排查。
        """
        if not text.strip():
            return text

        key = self._cache_key(target, text)
        with self.cache_lock:
            if key in self.cache:
                self.stats['cache'] += 1
                return self.cache[key]

        if target in self.unsupported_targets:
            self._record_fallback(target, text, '', 'unsupported')
            return None

        result = None
        for attempt in range(1, self.max_retries + 1):
            self.limiter.acquire()
            try:
                params = {
                    'SourceText': text[:MAX_TEXT_LENGTH],
                    'Source': 'zh',
                    'Target': target,
                    'ProjectId': 0,
                }
                resp = self._client().call_json(TMT_ACTION, params)
                result = (resp.get('Response') or {}).get('TargetText')
                if result is None:
                    raise RuntimeError(f'接口未返回译文：{resp}')
                break
            except self._sdk_exception as err:
                code = getattr(err, 'code', '') or ''
                if 'Unsupported' in code or 'Language' in code:
                    self.unsupported_targets.add(target)
                    self.log(f'  [warn] 目标语言 {target} 不受 TMT 支持，已跳过：{err}')
                    self._record_fallback(target, text, '', 'unsupported')
                    return None
                if attempt >= self.max_retries:
                    self.log(f'  [warn] 翻译失败（{code}），已回退原文：{text[:40]}')
                    self._record_fallback(target, text, '', 'api_error')
                    return None
                time.sleep(0.6 * attempt)
            except Exception as err:  # 网络异常等
                if attempt >= self.max_retries:
                    self.log(f'  [warn] 请求异常，已回退原文：{text[:40]}（{err}）')
                    self._record_fallback(target, text, '', 'api_error')
                    return None
                time.sleep(0.6 * attempt)

        if result is None:
            self._record_fallback(target, text, '', 'api_error')
            return None

        result = result.strip()

        # 机器翻译偶尔会把占位符拆开，例如 "% s" / "% d" / "{sl ug}"。
        # 先尝试把断开的占位符拼回（%s / %d / {slug}），再做完整性校验。
        repaired = repair_placeholder_spacing(result)
        if repaired != result:
            self.log(f'  [hint] 检测到占位符被断开，已自动修复'
                     f'（如 "% s" → "%s"）：{text[:30]}')
            result = repaired
            self.stats['repaired'] += 1

        if not is_safe_translation(text, result):
            self.log(f'  [warn] 占位符仍不完整，已回退原文：{text[:40]}')
            self._record_fallback(target, text, result, 'placeholder_broken')
            result = text
            self.stats['fallback'] += 1

        with self.cache_lock:
            self.cache[key] = result
            self.cache_dirty += 1
        self.stats['api'] += 1
        return result


# ============================================================
# 主流程
# ============================================================

def load_existing(po_path):
    """读取已有 .po，返回 (msgid -> msgstr 列表, Plural-Forms, nplurals)。"""
    if not os.path.isfile(po_path):
        return {}, None, 2
    entries, header_fields = parse_po(po_path)
    mapping = {}
    for entry in entries:
        if entry.is_header:
            continue
        mapping[entry.msgid] = list(entry.msgstr)
    plural_forms, nplurals = parse_plural_forms(header_fields)
    return mapping, plural_forms, nplurals


def process_language(lang, pot_entries, pot_header_fields, pot_creation_date,
                     translator, args, idx, total, reports):
    """翻译并写入单个语言文件。"""
    po_path = os.path.join(PROJECTS_DIR, os.path.basename(lang['file']))
    lang_code = os.path.splitext(lang['file'])[0]
    target = lang['target']
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    # 清空上一语言遗留的回退事件，只收集本语言的结果
    translator.drain_fallback_events()

    existing, plural_forms, nplurals = load_existing(po_path)
    if not plural_forms:
        plural_forms = DEFAULT_PLURAL_FORMS.get(
            lang_code, DEFAULT_PLURAL_FORMS_FALLBACK)
        nplurals = 2
        m = re.search(r'nplurals\s*=\s*(\d+)', plural_forms)
        if m:
            nplurals = int(m.group(1))

    print(f'\n[{idx}/{total}] {lang["file"]}  (target={target}, nplurals={nplurals})',
          flush=True)

    out_entries = []
    todo = []       # (entry, field_index, source_text)
    for entry in pot_entries:
        if entry.is_header:
            continue
        out = Entry(list(entry.comments))
        out.msgid = entry.msgid
        if entry.is_plural:
            out.msgid_plural = entry.msgid_plural
            out.msgstr = [''] * nplurals
        else:
            out.msgstr = ['']
        out_entries.append(out)

        # msgid "lang"：写入该语言的本语种名称，不调用接口
        if entry.msgid == 'lang':
            out.msgstr[0] = lang['name']
            continue

        if args.keep_existing and entry.msgid in existing:
            saved = existing[entry.msgid]
            if saved and saved[0]:
                if out.is_plural:
                    for i in range(min(nplurals, len(saved))):
                        out.msgstr[i] = saved[i]
                    for i in range(len(saved), nplurals):
                        out.msgstr[i] = saved[-1] if saved else ''
                else:
                    out.msgstr[0] = saved[0]
                continue

        sources = [entry.msgid]
        if entry.is_plural:
            sources.append(entry.msgid_plural)
        for i, src in enumerate(sources):
            todo.append((out, i, src))

    if args.limit:
        todo = todo[:args.limit]

    print(f'  待翻译：{len(todo)} 条', flush=True)
    if not todo:
        return 0

    if args.no_write:
        # 只做连通性验证
        ok = translator.translate(todo[0][2], target)
        print(f'  连通性测试：{ok!r}', flush=True)
        return 0

    from concurrent.futures import ThreadPoolExecutor

    done = 0
    lock = threading.Lock()

    def worker(item):
        nonlocal done
        out, field_index, src = item
        result = translator.translate(src, target)
        if result is None:
            result = src
        if out.is_plural:
            out.msgstr[field_index] = result
            for i in range(len(out.msgstr)):
                if not out.msgstr[i]:
                    out.msgstr[i] = out.msgstr[field_index]
        else:
            out.msgstr[0] = result

        with lock:
            done += 1
            if done % 100 == 0 or done == len(todo):
                translator.save_cache()
                print(f'  进度：{done}/{len(todo)}', flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(worker, todo))

    if args.write:
        # 未被翻译（limit 截断）的条目回落到已有译文，避免写入空串
        for out in out_entries:
            if out.msgid == 'lang':
                continue
            if not out.msgstr[0] and out.msgid in existing:
                saved = existing[out.msgid]
                if saved and saved[0]:
                    out.msgstr[0] = saved[0]

        header_text = build_header(lang_code, pot_header_fields, plural_forms,
                                   pot_creation_date)
        dump_po(po_path, header_text, out_entries)
        print(f'  已写入：{po_path}（{len(out_entries)} 条）', flush=True)

    events = translator.drain_fallback_events()
    reports[lang_code] = {
        'file': lang['file'],
        'target': target,
        'nplurals': nplurals,
        'total_fields': len(todo),
        'fallbacks': events,
    }

    translator.save_cache(force=True)
    return done


def main():
    parser = argparse.ArgumentParser(description='Typecho 语言包 TMT 翻译工具')
    parser.add_argument('--lang', nargs='*', default=None,
                        help='仅处理指定语言（文件名主干，如 en_US ja_JP）')
    parser.add_argument('--keep-existing', action='store_true',
                        help='保留已有译文，仅补齐缺失词条')
    parser.add_argument('--limit', type=int, default=0,
                        help='每个语言最多翻译的字段数量（调试用）')
    parser.add_argument('--no-write', action='store_true',
                        help='不写文件，仅测试接口连通性')
    parser.add_argument('--qps', type=float, default=4.0,
                        help='每秒请求数，默认 4（TMT 上限 5）')
    parser.add_argument('--workers', type=int, default=4,
                        help='并发线程数，默认 4')
    args = parser.parse_args()
    args.write = not args.no_write

    if not os.path.isfile(POT_FILE):
        print(f'未找到模板文件：{POT_FILE}')
        return 1

    pot_entries, pot_header_fields = parse_po(POT_FILE)
    pot_entries = [e for e in pot_entries
                   if not e.is_header and not e.msgid.startswith('#~')]
    pot_creation_date = get_header_value(pot_header_fields, 'POT-Creation-Date')
    print(f'模板文件：{POT_FILE}')
    print(f'词条数量：{len(pot_entries)}（其中复数 {sum(1 for e in pot_entries if e.is_plural)} 条）')

    languages = LANGUAGES
    if args.lang:
        wanted = set(args.lang)
        languages = [l for l in LANGUAGES
                     if os.path.splitext(l['file'])[0] in wanted]
        if not languages:
            print(f'没有匹配的语言：{args.lang}')
            return 1

    translator = TMTTranslator(qps=args.qps)

    reports = {}
    total = 0
    for i, lang in enumerate(languages, 1):
        total += process_language(lang, pot_entries, pot_header_fields,
                                  pot_creation_date, translator, args,
                                  i, len(languages), reports)

    print()
    print('=== 完成 ===')
    print(f'  接口调用：{translator.stats["api"]} 次')
    print(f'  缓存命中：{translator.stats["cache"]} 次')
    print(f'  占位符自动修复：{translator.stats["repaired"]} 条')
    print(f'  占位符回退：{translator.stats["fallback"]} 条')
    print(f'  合计处理：{total} 个字段')
    if translator.unsupported_targets:
        print(f'  不受支持的目标语言：{", ".join(sorted(translator.unsupported_targets))}')

    _write_report(reports)
    return 0


def _write_report(reports):
    """把本次翻译的回退/异常条目写入 tools/_tmt_report.json。"""
    summary = {
        'generated_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
        'pot': os.path.relpath(POT_FILE, BASE_DIR),
        'languages': {},
    }
    for code, rep in reports.items():
        fallbacks = rep['fallbacks']
        by_reason = Counter(e['reason'] for e in fallbacks)
        summary['languages'][code] = {
            'file': rep['file'],
            'target': rep['target'],
            'total_fields': rep['total_fields'],
            'fallback_total': len(fallbacks),
            'fallback_by_reason': dict(by_reason),
            'fallbacks': fallbacks,
        }
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    total_fb = sum(len(r['fallbacks']) for r in reports.values())
    print(f'  翻译报告：{os.path.relpath(REPORT_FILE, BASE_DIR)}'
          f'（共 {total_fb} 条需关注）')


if __name__ == '__main__':
    sys.exit(main())
