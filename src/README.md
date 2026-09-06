## src/

Compiled language files (`*.mo`) — these are what you actually install.

1. Copy the `langs/` folder.
2. Upload its `*.mo` files to `<your Typecho>/usr/langs/` (create the folder if missing).
3. The language selector under `Admin > Settings > General` will list them automatically.

`langs/` contains 10 languages:

- `de_DE` — Deutsch (German)
- `en_US` — English
- `es_ES` — Español (Spanish)
- `fr_FR` — Français (French)
- `ja_JP` — 日本語 (Japanese)
- `ko_KR` — 한국어 (Korean)
- `pt_BR` — Português (Brasil)
- `ru_RU` — Русский (Russian)
- `tr_TR` — Türkçe (Turkish)
- `zh_TW` — 繁體中文 (Traditional Chinese)

```
msgfmt ../original/projects/xx_XX.po -o langs/xx_XX.mo
```

Validate the `.po` sources before compiling — see `tools/_po_check.py` (report: `tools/runtime/po_check_report.json`).
