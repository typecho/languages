# Typecho Language Pack

*Read this in other languages: [简体中文](README.zh-cn.md), [繁體中文](README.zh-cht.md), [日本語](README.ja-jp.md)*

Multi-language language pack for **Typecho 1.3.0**. All translations are machine-generated from the Simplified-Chinese templates in `original/messages.pot` and kept in sync by the scripts under `tools/`.

## Install

1. Clone or download this repo, then copy the `src/langs/` folder.
2. Upload all `*.mo` files to `<your Typecho>/usr/langs/` (create the folder if missing).
3. In `Admin > Settings > General`, pick the language you need.

## Repository layout

```
original/messages.pot   Translation template: Simplified-Chinese strings extracted from Typecho 1.3.0 source
original/projects/      Per-language .po files (machine-generated, one-to-one with the template)
original/achieves/      Historical language packs from the upstream repo (hand-translated in 2018, not synced, reference only)
src/langs/              Compiled .mo files (what you install)
tools/                  Template-scan and batch-translation scripts (see tools/README.md)
```

## Update translations

Set up a virtual environment first (the scripts are plain Python, but the dependencies must not leak into your system interpreter):

```bash
python -m venv .venv                 # create once
.venv\Scripts\activate               # Windows (PowerShell)
# source .venv/bin/activate          # macOS / Linux
pip install tencentcloud-sdk-python-common opencc-python-reimplemented
```

Then:

```bash
python tools/_i18n_analyze.py             # scan Typecho source → regenerate messages.pot
python tools/_tmt_translate.py            # machine-translate all languages → regenerate projects/*.po
msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo   # compile the changed language file
```

Translations are AI machine-generated; pull requests that improve them under `original/projects/` are welcome.

> **After polishing any `.po` by hand, run `python tools/_build_tmt_cache.py`.**
> `_tmt_translate.py` serves translations from `tools/runtime/_tmt_cache.json`; a hand-polished
> string that is not in the cache will be **overwritten by the machine output** on the next run.
> `_build_tmt_cache.py` re-seeds the whole cache from the current `original/projects/*.po`, so your
> edits survive and later runs can work fully offline. Full order: edit `.po` → `_build_tmt_cache.py` → `msgfmt` → `_po_check.py`.

See also: http://docs.typecho.org/translate/start
