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
    6. 运行后输出 tools/runtime/_tmt_report.json，记录回退/异常的译文，便于后续补译。

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
# 所有运行产物（json）统一收纳在 tools/runtime/ 内
RUNTIME_DIR = os.path.join(BASE_DIR, 'tools', 'runtime')
CACHE_FILE = os.path.join(RUNTIME_DIR, '_tmt_cache.json')
REPORT_FILE = os.path.join(RUNTIME_DIR, '_tmt_report.json')

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
    {'file': 'zh_TW.po',  'target': 'zh-TW', 'name': '繁體中文'},
    {'file': 'tr_TR.po',  'target': 'tr',    'name': 'Türkçe'},
    {'file': 'ru_RU.po',  'target': 'ru',    'name': 'Русский'},
    {'file': 'pt_BR.po',  'target': 'pt',    'name': 'Português (Brasil)'},
    {'file': 'ja_JP.po',  'target': 'ja',    'name': '日本語'},
    {'file': 'ko_KR.po',  'target': 'ko',    'name': '한국어'},
    {'file': 'fr_FR.po',  'target': 'fr',    'name': 'Français'},
    {'file': 'es_ES.po',  'target': 'es',    'name': 'Español'},
    {'file': 'de_DE.po',  'target': 'de',    'name': 'Deutsch'},
    {'file': 'en_US.po',  'target': 'en',    'name': 'English'},
]

# 语言代码（文件名去扩展名）-> Plural-Forms，仅在原文件缺失时使用
DEFAULT_PLURAL_FORMS = {
    'ru_RU': 'nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2);',
    'fr_FR': 'nplurals=2; plural=(n > 1);',
    'ja_JP': 'nplurals=1; plural=0;',
    'ko_KR': 'nplurals=1; plural=0;',
    'pt_BR': 'nplurals=2; plural=(n > 1);',
    'zh_TW': 'nplurals=1; plural=0;',
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
                # 不要预先按 nplurals=2 铺两个槽位：nplurals=1 的语言
                # （zh_TW / ja_JP / ko_KR 等）在 .po 里只有 msgstr[0] 一行，
                # 预填会让「译文本已完整」的条目被误判为「缺 msgstr[1]」。
                # 真实槽位数由下面出现过的 msgstr[i] 决定。
                current.msgstr = ['']
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


def _strip_to_real_text(text):
    """去掉占位符、HTML 标签与实体，仅保留“真实”文本，
    用于判断一个 HTML 标签内部是否还残存可读内容。"""
    t = text
    for pattern in PLACEHOLDER_PATTERNS:
        t = re.sub(pattern, '', t)
    return t.strip()


_HTML_TAG_RE = re.compile(r'<(/?)([A-Za-z][A-Za-z0-9]*)[^>]*>')

def html_elements(text):
    """提取文本中所有成对的 HTML 元素，返回 [(tag, inner_text), ...]（按出现顺序）。"""
    stack = []          # [(tag, inner_start)]
    elements = []
    for m in _HTML_TAG_RE.finditer(text):
        is_close = m.group(1) == '/'
        tag = m.group(2).lower()
        if is_close:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == tag:
                    start = stack[i][1]
                    elements.append((tag, text[start:m.start()]))
                    del stack[i]
                    break
        else:
            stack.append((tag, m.end()))
    return elements


def check_html_integrity(source, translated):
    """检测译文是否破坏了原文的 HTML 结构（如 ``<a>…</a>`` 标签内文本被清空）。

    返回问题描述列表；为空表示正常。仅当原文某标签内含有“真实”文本、
    而译文对应标签内该文本丢失（变空）时才报警，避免误报本就为空的标签。
    """
    if not translated:
        return []
    src_by_tag = {}
    dst_by_tag = {}
    for tag, inner in html_elements(source):
        src_by_tag.setdefault(tag, []).append(inner)
    for tag, inner in html_elements(translated):
        dst_by_tag.setdefault(tag, []).append(inner)
    problems = []
    for tag in (set(src_by_tag) | set(dst_by_tag)):
        s_list = src_by_tag.get(tag, [])
        d_list = dst_by_tag.get(tag, [])
        for i in range(max(len(s_list), len(d_list))):
            s_inner = s_list[i] if i < len(s_list) else ''
            d_inner = d_list[i] if i < len(d_list) else ''
            if _strip_to_real_text(s_inner) and not _strip_to_real_text(d_inner):
                problems.append(f'<{tag}> 标签内的文本在译文中丢失或为空')
    return problems


def repair_placeholder_spacing(text):
    """修复机器翻译在占位符中插入的空格 / 改写的大小写。

    机器翻译常把 ``%s`` / ``%d`` / ``{slug}`` 拆成
    ``% s`` / ``% d`` / ``{sl ug}``，或把 ``%s`` 写成 ``%S``、
    ``{cid}`` 写成 ``{Cid}``。这里只把**断开的占位符**拼回、
    把被改写的大小写还原，不会改动译文里正常的词间空格。
    """
    # %s / %d / %1$s 之间被插入的空格
    text = re.sub(r'%(\s+)([sdSD])', r'%\2', text)
    text = re.sub(r'%(\d+)\s*\$\s*([sdSD])', r'%\1$\2', text)
    # 机器翻译偶尔会把 %s / %d 大写化为 %S / %D（printf 里二者不等价）
    text = re.sub(r'%(?:(\d+)\$)?([SD])',
                  lambda m: '%' + (m.group(1) + '$' if m.group(1) else '')
                            + m.group(2).lower(),
                  text)
    # {name} / {slug} 等花括号内被插入的空格
    text = re.sub(r'(\{)([^}]*?)(\})',
                  lambda m: m.group(1) + m.group(2).replace(' ', '') + m.group(3),
                  text)
    return text


_BRACE_PLACEHOLDER_RE = re.compile(r'\{([^{}]*)\}')


def restore_placeholder_case(source, translated):
    """把译文里被改写大小写的 ``{Name}`` 占位符还原为原文的 ``{name}``。

    机器翻译常把 ``{cid}`` 写成 ``{Cid}`` / ``{CID}``，而占位符名是
    区分大小写的键名，必须逐字还原，否则会被判为「占位符缺失」而回退原文。
    """
    if '{' not in source or '{' not in translated:
        return translated
    wanted = {}
    for name in _BRACE_PLACEHOLDER_RE.findall(source):
        wanted.setdefault(name.lower(), name)
    if not wanted:
        return translated
    return _BRACE_PLACEHOLDER_RE.sub(
        lambda m: '{' + wanted.get(m.group(1).lower(), m.group(1)) + '}',
        translated)


# ============================================================
# HTML 重型字符串的分段翻译
#
# 机器翻译遇到 ``分类 <a href="%s">%s</a> 已经被增加`` 这类「正文 + 标签」
# 混排的字符串时，常常把标签挪到句首并清空标签内的文字
# （如 ``<a href="%s"></a>分类``），导致链接文字丢失、页面出现空链接。
# 这里改为「先切分、再翻译、最后按原顺序拼回」，保证标签结构不丢。
# ============================================================

_MARKUP_TAG_RE = re.compile(r'<(/?)([A-Za-z][A-Za-z0-9]*)[^>]*>')

# 简体中文（CJK 统一表意文字），用于判断机翻是否真的改动了句子
CJK_RE = re.compile(r'[\u4e00-\u9fff]')


def split_markup(text):
    """把字符串切分为文本片段与（最外层）HTML 元素。

    返回列表，每个元素形如：
        ('text', content)                       —— 标签之间的纯文本
        ('elem', open_tag, inner, close_tag)    —— 一个完整的 HTML 元素
    嵌套元素由最外层片段整体带走，交给递归处理。
    """
    spans, stack = [], []
    for m in _MARKUP_TAG_RE.finditer(text):
        if m.group(1) == '/':
            tag = m.group(2).lower()
            for k in range(len(stack) - 1, -1, -1):
                if stack[k][0] == tag:
                    spans.append((stack[k][1], m.end(), stack[k][2], m.start()))
                    del stack[k]
                    break
        elif not m.group(0).endswith('/>'):     # 跳过 <br /> 等自闭合标签
            stack.append((m.group(2).lower(), m.start(), m.end()))
    spans.sort()

    segments, pos = [], 0
    for start, end, inner_start, inner_end in spans:
        if start < pos:                          # 嵌套元素，已随外层带走
            continue
        if start > pos:
            segments.append(('text', text[pos:start]))
        segments.append(('elem', text[start:inner_start],
                         text[inner_start:inner_end], text[inner_end:end]))
        pos = end
    if pos < len(text):
        segments.append(('text', text[pos:]))
    return segments


def has_markup(text):
    """字符串是否含有成对的 HTML 元素。"""
    return any(seg[0] == 'elem' for seg in split_markup(text))


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

        self.stats = Counter()
        self.unsupported_targets = set()
        self.print_lock = threading.Lock()
        # 回退/修复事件，用于生成翻译报告（见 _tmt_report.json）
        self.fallback_events = []
        self.report_lock = threading.Lock()

        self.cache = {}
        self.cache_dirty = 0
        self.cache_lock = threading.Lock()
        self._load_cache()

    # ---------- 缓存 ----------

    def _load_cache(self):
        if os.path.isfile(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
            except (ValueError, OSError):
                self.cache = {}
        self._purge_stale_cache()

    def _purge_stale_cache(self):
        """清理缓存里已经不合格的历史译文，让它们在本轮重新翻译。

        两类历史遗留都会被剔除：
          1. 「译文 == 简体中文原文」—— 早期占位符校验过严（TMT 返回的
             ``%S`` / ``{CID}`` 被判为缺失），正常译文被回退成原文后又被
             写进缓存，导致后续重跑一直命中错误的中文（zh-TW 属正常，跳过）；
          2. 占位符缺失、或 HTML 标签内文字被机翻清空的译文
             （如 ``<a href="%s"></a>分类``）。
        """
        removed = 0
        for key in list(self.cache):
            target, _, source = key.partition('\x00')
            value = self.cache[key]
            if not isinstance(value, str) or not source:
                del self.cache[key]
                removed += 1
                continue
            if target != 'zh-TW' and value == source:
                del self.cache[key]
                removed += 1
                continue
            if not is_safe_translation(source, value) \
                    or check_html_integrity(source, value):
                del self.cache[key]
                removed += 1
        if removed:
            self.cache_dirty += 1
            self.log(f'  已清理 {removed} 条不合格的历史缓存译文，本轮将重新翻译')

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

    @staticmethod
    def _is_valid(source, translated):
        """译文是否同时满足占位符完整与 HTML 结构完整。"""
        return bool(translated) \
            and is_safe_translation(source, translated) \
            and not check_html_integrity(source, translated)

    def translate(self, text, target):
        """翻译单条文本（对外入口：缓存 + HTML 结构保护）。

        含 HTML 元素的字符串优先走 :meth:`_translate_markup`，避免机翻
        清空标签内文字；其余走 :meth:`_translate_plain`。
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
        if has_markup(text):
            result = self._translate_markup(text, target)
            if result is not None:
                self.stats['markup'] += 1

        if result is None:
            result = self._translate_plain(text, target)

        if result is None:
            # 接口失败 / 目标语言不受支持：回退原文，且不写缓存
            return text

        if result == text and target != 'zh-TW' and CJK_RE.search(text):
            # 机翻原样吐回中文：多半是踩到了接口对某些句式的怪癖，再试一次
            retried = self._retry_untranslated(text, target)
            if retried:
                result = retried
                self.stats['retried'] += 1

        if result == text and target != 'zh-TW':
            # 回退原文的结果不进缓存，避免一次偶发失败被永久固化
            return result

        with self.cache_lock:
            self.cache[key] = result
            self.cache_dirty += 1
        return result

    def _retry_untranslated(self, text, target):
        """机翻原样吐回中文时，去掉尾部的半角标点再翻译一次。

        TMT 对部分「以半角句点结尾的中文长句」会直接原样返回，去掉尾部
        标点后通常就能正常出译文，最后再把标点补回去。
        """
        m = re.search(r'[.!?,;:]+\s*$', text)
        if not m:
            return None
        core, tail = text[:m.start()], m.group(0)
        if not core.strip() or not CJK_RE.search(core):
            return None
        got = self.translate(core, target)
        if not got or got == core:
            return None
        return got + tail

    def _translate_markup(self, text, target):
        """翻译含 HTML 元素的字符串，保证标签结构与占位符不被机翻破坏。

        策略一：把元素整体替换为 ``{E0}`` 掩码后整句翻译，再把翻译好的元素
                回填到掩码位置 —— 语序最自然，但机翻可能吞掉掩码；
        策略二：掩码未能保留时，退回「逐片段翻译 + 按原顺序拼回」，
                语序略生硬但结构一定正确。
        两种策略都需通过占位符与 HTML 结构校验；都失败则返回 None，
        由调用方回落到普通整句翻译。
        """
        segments = split_markup(text)
        elements = [s for s in segments if s[0] == 'elem']
        if not elements:
            return None

        # ---------- 策略一：掩码整句翻译 ----------
        skeleton, elem_index = [], 0
        for seg in segments:
            if seg[0] == 'text':
                skeleton.append(seg[1])
            else:
                skeleton.append('{E%d}' % elem_index)
                elem_index += 1
        skeleton_text = ''.join(skeleton)

        masked_out = self._translate_plain(skeleton_text, target, record=False)
        masks_kept = (masked_out is not None
                      and all('{E%d}' % i in masked_out for i in range(elem_index))
                      # 掩码虽在但整句仍是中文 = 机翻失败回退，不能采用
                      and not (masked_out == skeleton_text
                               and CJK_RE.search(skeleton_text)))
        if masks_kept:
            rendered = masked_out
            for i, seg in enumerate(elements):
                rendered = rendered.replace('{E%d}' % i,
                                            self._render_element(seg, target))
            if self._is_valid(text, rendered):
                return rendered

        # ---------- 策略二：逐片段翻译后按原顺序拼回 ----------
        parts = [self._render_element(seg, target) if seg[0] == 'elem'
                 else self._translate_fragment(seg[1], target)
                 for seg in segments]
        joined = ''.join(parts)
        return joined if self._is_valid(text, joined) else None

    def _render_element(self, seg, target):
        """渲染一个 HTML 元素：标签原样保留，内部文本单独翻译。"""
        _, open_tag, inner, close_tag = seg
        return open_tag + self._translate_fragment(inner, target) + close_tag

    def _translate_fragment(self, text, target):
        """翻译片段（标签之间的文本，或标签内部的文本），保留首尾空白。"""
        # 纯空白、或去掉占位符/标签后已无实义文本（如 "%s"）的片段无需翻译
        if not text.strip() or not _strip_to_real_text(text):
            return text
        lead = text[:len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        core = text.strip()

        if has_markup(core):
            got = self._translate_markup(core, target)
        else:
            got = self._translate_plain(core, target, record=False)
            if got is not None:
                got = restore_placeholder_case(core, got)
        if not got:
            got = core
        return lead + got + trail

    def _translate_plain(self, text, target, record=True):
        """调用 TMT 翻译单条纯文本（不含 HTML 元素）。

        ``record=False`` 用于分段翻译的内部片段，其成败由外层整体校验
        负责，避免把中间结果误记进回退报告。
        返回译文；接口不可用或占位符被破坏时回退原文（record 时记入报告）。
        """
        if target in self.unsupported_targets:
            if record:
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
                    if record:
                        self._record_fallback(target, text, '', 'unsupported')
                    return None
                if attempt >= self.max_retries:
                    self.log(f'  [warn] 翻译失败（{code}），已回退原文：{text[:40]}')
                    if record:
                        self._record_fallback(target, text, '', 'api_error')
                    return None
                time.sleep(0.6 * attempt)
            except Exception as err:  # 网络异常等
                if attempt >= self.max_retries:
                    self.log(f'  [warn] 请求异常，已回退原文：{text[:40]}（{err}）')
                    if record:
                        self._record_fallback(target, text, '', 'api_error')
                    return None
                time.sleep(0.6 * attempt)

        if result is None:
            if record:
                self._record_fallback(target, text, '', 'api_error')
            return None

        result = result.strip()

        # 机器翻译偶尔会把占位符拆开（"% s" / "% d" / "{sl ug}"）或改写
        # 大小写（"%S" / "{Cid}"）。先把它们还原，再做完整性校验。
        repaired = restore_placeholder_case(text, repair_placeholder_spacing(result))
        if repaired != result:
            self.log(f'  [hint] 检测到占位符被改写，已自动修复'
                     f'（如 "% s" → "%s"、"%S" → "%s"、"{{Cid}}" → "{{cid}}"）：{text[:30]}')
            result = repaired
            self.stats['repaired'] += 1

        if not is_safe_translation(text, result):
            if record:
                self.log(f'  [warn] 占位符仍不完整，已回退原文：{text[:40]}')
                self._record_fallback(target, text, result, 'placeholder_broken')
            result = text
            self.stats['fallback'] += 1

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
        # nplurals==1 的语言（zh_TW / ja_JP / ko_KR 等）在 .po 中每个复数词条
        # 只有 msgstr[0] 一个槽位（msgid_plural 原样保留但不单独占格）。
        # 只翻译 msgid 主形即可，勿把 msgid_plural 也排入任务，
        # 否则 worker 会写越界的 msgstr[1]（IndexError）。
        if entry.is_plural and nplurals > 1:
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

    # 确保运行产物目录存在（所有 json 都写入 tools/runtime/）
    os.makedirs(RUNTIME_DIR, exist_ok=True)

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
    print(f'  HTML 分段翻译：{translator.stats["markup"]} 条')
    print(f'  原样返回重试成功：{translator.stats["retried"]} 条')
    print(f'  合计处理：{total} 个字段')
    if translator.unsupported_targets:
        print(f'  不受支持的目标语言：{", ".join(sorted(translator.unsupported_targets))}')

    _write_report(reports)
    return 0


def _write_report(reports):
    """把本次翻译的回退/异常条目写入 tools/runtime/_tmt_report.json。"""
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
