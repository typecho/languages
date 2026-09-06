# Typecho 语言包维护工作流（SKILL）

供维护者 / AI 协作时遵循的标准流程。所有脚本在 `tools/` 下，文件名以 `_` 开头表示内部工具。

## 仓库结构

```
original/messages.pot   翻译模板：从 Typecho 1.3.0 源码抽取的简体中文词条（唯一来源）
original/projects/      TMT 机器翻译生成的各语言 .po（与模板一一对应）
original/achieves/      上游遗留的 2018 人工翻译历史包（仅参考，未同步）
src/langs/              编译后的 .mo（安装使用）
tools/                  _i18n_analyze.py（扫模板）、_tmt_translate.py（翻译）、_po_check.py（校验）、runtime/（运行产物 json）
```

翻译链路：`messages.pot` →（TMT）→ `original/projects/*.po` →（`msgfmt`）→ `src/langs/*.mo`

## 环境搭建（务必使用虚拟环境）

所有脚本都跑在仓库根目录的 `.venv/` 虚拟环境里，避免依赖污染系统 Python：

```bash
python -m venv .venv                 # 只需创建一次

.venv\Scripts\activate               # Windows（PowerShell）
source .venv/bin/activate            # macOS / Linux

pip install tencentcloud-sdk-python-common opencc-python-reimplemented
```

| 依赖 | 用途 |
| --- | --- |
| `tencentcloud-sdk-python-common` | `_tmt_translate.py` 调用 TMT `TextTranslate` 接口 |
| `opencc-python-reimplemented` | `_po_check.py` 对 `zh_TW` / `ja_JP` 做简→繁判定 |
| `msgfmt`（GNU gettext，非 Python 包） | 编译 `src/langs/*.mo` |

`.venv/` 已在 `.gitignore` 中，不要提交。

## 前置条件

- 腾讯云机器翻译（TMT）凭证：`TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`（未设置时回退脚本内默认值）。
- 已在 `.venv/` 中安装 `tencentcloud-sdk-python-common` 与 `opencc-python-reimplemented`（见上）。
- 编译 `.mo` 需要 `msgfmt`（gettext）。

## 标准工作流

0. **激活虚拟环境**（每个新终端都要做一次）：
   ```bash
   .venv\Scripts\activate       # Windows（PowerShell）
   source .venv/bin/activate    # macOS / Linux
   ```
1. **更新模板**（Typecho 升级或词条变化时）：
   ```bash
   python tools/_i18n_analyze.py
   ```
2. **翻译**（覆写全部语言，或仅指定语言）：
   ```bash
   python tools/_tmt_translate.py                 # 全部
   python tools/_tmt_translate.py --lang ko_KR    # 单语言
   python tools/_tmt_translate.py --keep-existing # 仅补齐缺失，保留已有译文
   python tools/_tmt_translate.py --lang en_US --limit 20 --no-write  # 只测连通性
   ```
3. **编译**变更的语言：
   ```bash
   msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo
   ```
4. **校验**（翻译完整度 + 占位符完整性 + POT 对齐 + 中文残留 + 复数表单 + HTML 结构 + 未译副本）：
   ```bash
   python tools/_po_check.py            # 默认仅检查 projects/，输出 tools/runtime/_po_check_report.json
   python tools/_po_check.py --dir achieves  # 额外检查历史参考包 achieves/
   python tools/_po_check.py --no-json  # 仅打印汇总，不写文件
   ```
   也可以直接用 `_tmt_translate.py` 里的 `parse_po` / `is_safe_translation` 写临时脚本检查。

## 人工润色后必须重建缓存

直接编辑 `original/projects/xx_XX.po` 润色译文后，**一定要**执行：

```bash
python tools/_build_tmt_cache.py                             # 把润色结果写回翻译缓存
msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo      # 重新编译
python tools/_po_check.py                                    # 重新校验
```

> **为什么**：`_tmt_translate.py` 的译文取自 `tools/runtime/_tmt_cache.json`，
> 而不是直接读 `.po`。手工改过但没有回写缓存的词条，会在下一次跑翻译时被
> 机翻结果**静默覆盖**，润色就白做了。
> `_build_tmt_cache.py` 会用当前 `original/projects/*.po` 整体重建缓存
> （自动跳过占位符缺失、HTML 标签被清空的坏译文），之后的翻译运行也能全离线命中。

## 已知问题与处理

| 现象 | 原因 | 脚本行为 | 报告 reason |
| --- | --- | --- | --- |
| `% s` / `% d` / `{sl ug}` | 机翻把占位符断开 | **已自动修复**（`repair_placeholder_spacing`），日志打 `[hint]` | — |
| `%S` / `%D` / `{CID}` / `{Cid}` | 机翻改写了占位符大小写，而占位符名区分大小写 | **已自动修复**（`repair_placeholder_spacing` + `restore_placeholder_case`），日志打 `[hint]` | — |
| `<a href="%s">%s</a>` 类 HTML 重型串被吞掉标签内文字（变成 `<a href="%s"></a>…`） | TMT 重写标签结构 | **已自动规避**：这类串改走分段翻译（`_translate_markup`），标签原样保留、内部文字单独翻译后拼回 | — |
| 整句被机翻原样吐回中文 | TMT 对个别句式（如以半角句点结尾的长句）失灵 | **已自动重试**：去掉尾部半角标点再翻一次，成功后补回标点 | — |
| 接口报错 / 超时 / 不支持的语言 | 网络或配额 | 回退为原文，日志 `[warn]` | `api_error` / `unsupported` |
| 占位符/HTML 结构仍不完整 | 上述修复都无效 | 回退为原文，日志 `[warn]` | `placeholder_broken` |

> 修复逻辑只会把**断开的占位符**拼回、把**被改写的大小写**还原，不会改动译文里的正常词间空格。

## 翻译缓存的自愈

`_tmt_cache.json` 在加载时会剔除三类不合格历史译文，让它们在本轮重新翻译，
避免「一次失败被永久固化」：

1. 译文 == 简体中文原文（即曾经的回退结果，`zh-TW` 除外，其简繁相同属正常）；
2. 占位符缺失（`is_safe_translation` 不通过）；
3. HTML 标签内文字被清空（`check_html_integrity` 报警）。

新产生的回退结果也不会再写入缓存。`_build_tmt_cache.py` 生成缓存时同样会跳过这三类。

## 繁体中文的特殊规则

`_po_check.py` 对繁体中文（`zh_TW` 等）**跳过「未译副本」检查**：简→繁只是字形
转换，大量词条（如「作者」「保存文件」「%d年」）转换后与原文逐字相同是正确结果，
不是漏译。其它语言（含日文）仍保留该项检查，日文靠 OpenCC 判定豁免纯汉字串。

## 运行产物：`tools/runtime/`

所有脚本生成的 json 统一收纳在 `tools/runtime/` 内：

| 文件 | 来源 | 内容 |
| --- | --- | --- |
| `_tmt_report.json` | `_tmt_translate.py` | 翻译回退/异常条目（占位符被破坏、接口报错等） |
| `_tmt_cache.json` | `_tmt_translate.py` | 翻译缓存，避免重复调用接口 |
| `_po_check_report.json` | `_po_check.py` | 各 .po 的翻译完整度、占位符、中文残留等校验结果 |

`_tmt_report.json` 记录所有回退/异常条目，便于事后补译：

```json
{
  "generated_at": "...",
  "pot": "original/messages.pot",
  "languages": {
    "ko_KR": {
      "file": "ko_KR.po",
      "target": "ko",
      "total_fields": 904,
      "fallback_total": 16,
      "fallback_by_reason": {"placeholder_broken": 16},
      "fallbacks": [
        {"target": "ko", "source": "分类 <a href=\"%s\">%s</a> 已经被增加",
         "raw_tmt": "<a href=\"%s\"></a>分类", "reason": "placeholder_broken"}
      ]
    }
  }
}
```

`source` = 原文（msgid），`raw_tmt` = TMT 实际返回（已尽量修复占位符空格），`reason` = 失败类别。

## 如何基于报告补译（无需重跑 API）

1. 读取 `tools/runtime/_tmt_report.json`，按 `reason` 分组。
2. `placeholder_broken`：取 `raw_tmt` 再跑一次 `repair_placeholder_spacing`
   （幂等）；若仍缺占位符（多为 HTML 标签被吞），需人工把原文里的占位符补回。
3. `api_error` / `unsupported`：无 `raw_tmt`，需重跑该语言或人工翻译。
4. 将补好的译文写回 `original/projects/xx_XX.po` 对应 `msgstr`，重新 `msgfmt` 编译。

也可直接写一次性脚本：解析报告 → 对每条 `source` 在 po 中定位 → 用修复后的 `raw_tmt`（或人工译文）回填 → `dump_po` 写回。

## 新增语言

1. 在 `_tmt_translate.py` 的 `LANGUAGES` 增加
   `{'file': 'xx_XX.po', 'target': '<TMT代码>', 'name': '本语种名称'}`。
2. 若该语言复数规则特殊，在 `DEFAULT_PLURAL_FORMS` 增加对应项
   （缺省 `nplurals=2; plural=(n != 1);`）。
3. 运行翻译 → `msgfmt` 编译 → 校验。

## 验证清单

- [ ] `python -m py_compile tools/_tmt_translate.py` 通过
- [ ] 全文件 `is_safe_translation` 占位符完整（不完整 = 0）
- [ ] POT 与 PO 词条数一致（无缺失 / 无多余）
- [ ] 无意外中文残留（`msgstr` 含简体中文应仅为确实未翻译的回退项）
- [ ] `python tools/_po_check.py` 运行无占位符/缺失/中文残留告警
- [ ] `tools/runtime/_tmt_report.json` 中的 `placeholder_broken` / `api_error` 已处理
