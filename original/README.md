## original/

Source and project files used to build the language pack:

| Path | Contents |
| --- | --- |
| `messages.pot` | Translation template — every Simplified-Chinese string of Typecho 1.3.0, extracted from its source code. |
| `projects/` | Per-language `.po` files, machine-translated from `messages.pot` and aligned with it one-to-one. |
| `achieves/` | Historical language packs kept from the upstream repo (hand-translated in 2018). They are not synced with the current template and are kept for human reference only. |

Typecho loads pre-compiled `.mo` files, so this directory is not meant for direct upload — use the compiled files in `src/langs/` instead.
