## original/

Source and project files used to build the language pack:

| Path | Contents |
| --- | --- |
| `messages.pot` | Translation template — every Simplified-Chinese string of Typecho 1.3.0, extracted from its source code. |
| `projects/` | Language `.po` files, machine-translated from `messages.pot`. Therefore, we can only guarantee basic multilingual support; we look forward to your involvement in refining the translations, or you may even take the lead on the translation work yourself. |
| `achieves/` | Historical language packs kept from the upstream repo (hand-translated in 2018). They are not synced with the current template and are kept for reference. |

Typecho loads pre-compiled `.mo` files, so this directory is not meant for direct upload — use the compiled files in `src/langs/` instead.

The `.po` files can be validated for completeness and placeholder integrity with `tools/_po_check.py`, which writes its report to `tools/runtime/po_check_report.json`.
