# Typecho 语言包

*其他语言版本：[English](README.md), [繁體中文](README.zh-cht.md), [日本語](README.ja-jp.md)*

**Typecho 1.3.0** 的多语言语言包。译文由简体中文源词条（`original/messages.pot`）经机器翻译自动生成，并随 Typecho 源码更新同步。

## 安装

1. 克隆或下载本仓库，并复制 `src/langs/` 目录。
2. 将其中所有 `*.mo` 上传到 `<你的 Typecho>/usr/langs/`（若不存在请先创建）。
3. 在 `管理后台 > 设置 > 基本设置` 中选择所需语言。

## 目录结构

```
original/messages.pot   翻译模板：从 Typecho 1.3.0 源码提取的简体中文词条
original/projects/      各语言的 .po 源文件（机器翻译生成，与模板一一对应）
original/achieves/      官方仓库遗留的历史语言包（2018 年人工翻译，未同步，仅作参考）
src/langs/              编译完成的 .mo 文件（安装时使用）
tools/                  扫描模板与批量翻译脚本（详见 tools/README.md）
```

## 更新翻译

请先在虚拟环境中工作（脚本本身是纯 Python，但依赖不应污染系统解释器）：

```bash
python -m venv .venv                 # 只需创建一次
.venv\Scripts\activate               # Windows（PowerShell）
# source .venv/bin/activate          # macOS / Linux
pip install tencentcloud-sdk-python-common opencc-python-reimplemented
```

然后执行：

```
python tools/_i18n_analyze.py               # 扫描 Typecho 源码 → 重新生成 messages.pot
python tools/_tmt_translate.py              # 机器翻译全部语言 → 重新生成 projects/*.po
msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo   # 编译变更的语言文件
```

译文由 AI 机器生成，欢迎通过 Pull Request 修订 `original/projects/` 下的译文。

> **手工润色任意 `.po` 后，请运行 `python tools/_build_tmt_cache.py`。**
> `_tmt_translate.py` 的译文取自 `tools/runtime/_tmt_cache.json`，手工修改却未写回缓存的词条，
> 会在下次翻译时被机翻结果**静默覆盖**。`_build_tmt_cache.py` 会用当前 `original/projects/*.po`
> 整体重建缓存，润色才能保留，后续运行也能全离线命中。完整顺序：改 `.po` → `_build_tmt_cache.py` → `msgfmt` → `_po_check.py`。

另请参阅：http://docs.typecho.org/translate/start
