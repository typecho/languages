## src/

Compiled language files (`*.mo`) — these are what you actually install.

1. Copy the `langs/` folder.
2. Upload its `*.mo` files to `<your Typecho>/usr/langs/` (create the folder if missing).
3. The language selector under `Admin > Settings > General` will list them automatically.

`langs/` contains 8 languages: `en_US`, `es_ES`, `fr_FR`, `ja_JP`, `pt_BR`, `ru_RU`, `tr_TR`, `zh_TW`. Rebuild a file after editing its `.po`:

```
msgfmt ../original/projects/xx_XX.po -o langs/xx_XX.mo
```
