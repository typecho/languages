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

```
python tools/_i18n_analyze.py             # scan Typecho source → regenerate messages.pot
python tools/_tmt_translate.py            # machine-translate all languages → regenerate projects/*.po
msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo   # compile the changed language file
```

Translations are AI machine-generated; pull requests that improve them under `original/projects/` are welcome.

See also: http://docs.typecho.org/translate/start
