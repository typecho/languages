## tools/

Maintenance scripts for regenerating the language pack:

| Script | Purpose | Usage |
| --- | --- | --- |
| `_i18n_analyze.py` | Scans Typecho's PHP source for i18n strings and regenerates `original/messages.pot`. Run it whenever Typecho is updated. | `python tools/_i18n_analyze.py` |
| `_tmt_translate.py` | Batch machine-translation via Tencent Cloud TMT: reads `original/messages.pot` and rewrites the `.po` files under `original/projects/`. | `python tools/_tmt_translate.py [--lang en_US ja_JP] [--keep-existing] [--limit N --no-write]` |

Notes:

- `_tmt_translate.py` reads the Tencent Cloud credentials from `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` (falling back to defaults embedded in the script).
- After translation, compile the changed files into `src/langs/` with `msgfmt`.
- The leading `_` marks both scripts as internal tooling.
