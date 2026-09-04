# Typecho 语言包维护工作流（SKILL）

供维护者 / AI 协作时遵循的标准流程。所有脚本在 `tools/` 下，文件名以 `_` 开头表示内部工具。

## 仓库结构

```
original/messages.pot   翻译模板：从 Typecho 1.3.0 源码抽取的简体中文词条（唯一来源）
original/projects/      TMT 机器翻译生成的各语言 .po（与模板一一对应）
original/achieves/      上游遗留的 2018 人工翻译历史包（仅参考，未同步）
src/langs/              编译后的 .mo（安装使用）
tools/                  _i18n_analyze.py（扫模板）、_tmt_translate.py（翻译）、_tmt_report.json（运行产物）
```

翻译链路：`messages.pot` →（TMT）→ `original/projects/*.po` →（`msgfmt`）→ `src/langs/*.mo`

## 前置条件

- 腾讯云机器翻译（TMT）凭证：`TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY`（未设置时回退脚本内默认值）。
- 本地安装 `tencentcloud-sdk-python` 与 `msgfmt`（gettext）。

## 标准工作流

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
4. **校验**（占位符完整性 + 中文残留 + POT 对齐）：用 `_tmt_translate.py` 里的
   `parse_po` / `is_safe_translation` 写临时脚本检查，或直接比对 `tools/_tmt_report.json`。

## 已知问题与处理

| 现象 | 原因 | 脚本行为 | 报告 reason |
| --- | --- | --- | --- |
| `% s` / `% d` / `{sl ug}` | 机翻把占位符断开 | **已自动修复**（`repair_placeholder_spacing`），日志打 `[hint]` | — |
| `<a href="%s">%s</a>` 类 HTML 重型串被吞掉占位符 | TMT 重写标签导致占位符缺失 | 回退为原文（简体中文），日志 `[warn]` | `placeholder_broken` |
| 接口报错 / 超时 / 不支持的语言 | 网络或配额 | 回退为原文，日志 `[warn]` | `api_error` / `unsupported` |

> 修复逻辑只会把**断开的占位符**拼回，不会改动译文里的正常词间空格。

## 运行产物：`tools/_tmt_report.json`

每次翻译都会覆盖写入该文件，记录所有回退/异常条目，便于事后补译：

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

1. 读取 `tools/_tmt_report.json`，按 `reason` 分组。
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
- [ ] `tools/_tmt_report.json` 中的 `placeholder_broken` / `api_error` 已处理
