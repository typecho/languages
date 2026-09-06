## tools/

Maintenance scripts for regenerating the language pack.

### Set up the environment

Always work inside a virtual environment rooted at `.venv/` in the repository, so the
script dependencies never leak into your system interpreter:

```bash
python -m venv .venv                 # create it once

.venv\Scripts\activate               # Windows (PowerShell)
source .venv/bin/activate            # macOS / Linux

pip install tencentcloud-sdk-python-common opencc-python-reimplemented
```

| Dependency | Needed by |
| --- | --- |
| `tencentcloud-sdk-python-common` | `_tmt_translate.py` (calls the TMT `TextTranslate` API) |
| `opencc-python-reimplemented` | `_po_check.py` (Simplified → Traditional check for `zh_TW` / `ja_JP`) |
| `msgfmt` (GNU gettext, not a Python package) | compiling `src/langs/*.mo` |

`.venv/` is git-ignored — never commit it.

### Scripts

Maintenance scripts for regenerating the language pack:

| Script | Purpose | Usage |
| --- | --- | --- |
| `_i18n_analyze.py` | Scans Typecho's PHP source for i18n strings and regenerates `original/messages.pot`. Run it whenever Typecho is updated. | `python tools/_i18n_analyze.py` |
| `_tmt_translate.py` | Batch machine-translation via Tencent Cloud TMT: reads `original/messages.pot` and rewrites the `.po` files under `original/projects/`. | `python tools/_tmt_translate.py [--lang en_US ja_JP] [--keep-existing] [--limit N --no-write]` |
| `_po_check.py` | Validates `.po` files for translation completeness, placeholder integrity, POT alignment, Chinese residual, plural-form consistency, HTML structure and verbatim copies. By default only checks `original/projects/` (the maintained packs); pass `--dir achieves` to also check the reference-only historical packs. | `python tools/_po_check.py [--dir projects] [--no-json]` |
| `_build_tmt_cache.py` | One-off helper: seeds `tools/runtime/_tmt_cache.json` from the translations already present in `original/projects/*.po`, so a later `_tmt_translate.py` run can work fully offline. | `python tools/_build_tmt_cache.py` |

Notes:

- **After polishing any `.po` file by hand, run `python tools/_build_tmt_cache.py`.**
  `_tmt_translate.py` serves translations from `tools/runtime/_tmt_cache.json`; a hand-edited
  string that is missing from (or stale in) the cache is **overwritten by the machine output**
  on the next run. `_build_tmt_cache.py` re-seeds the whole cache from the current
  `original/projects/*.po`, so your edits survive — and every later run can then work offline.
  Full order: edit `.po` → `_build_tmt_cache.py` → `msgfmt` → `_po_check.py`.
- `_tmt_translate.py` reads the Tencent Cloud credentials from `TENCENTCLOUD_SECRET_ID` / `TENCENTCLOUD_SECRET_KEY` (falling back to defaults embedded in the script).
- The translation cache is self-healing: on start-up `_tmt_translate.py` drops cached entries that would no longer pass validation (fallback-to-Chinese, missing placeholders, emptied HTML tags) so those strings get re-translated instead of being served from stale cache.
- Strings containing HTML elements (`<a>…</a>`, `<strong>…</strong>`, …) are translated segment-wise so the engine cannot empty the text inside a tag.
- After translation, compile the changed files into `src/langs/` with `msgfmt`.
- The leading `_` marks all scripts as internal tooling.
- All JSON run artifacts are written under `tools/runtime/`:
  - `_tmt_report.json` / `_tmt_cache.json` from `_tmt_translate.py`
  - `po_check_report.json` from `_po_check.py`
- `_tmt_report.json` lists every entry that fell back to the source string (API failure or placeholders the engine dropped), with the raw machine output for recovery.
- Maintenance workflow and how to fix fallback entries: see `tools/SKILL.md`.
