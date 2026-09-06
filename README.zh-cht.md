# Typecho 語言包

*其他語言版本：[English](README.md), [简体中文](README.zh-cn.md), [日本語](README.ja-jp.md)*

**Typecho 1.3.0** 的多言語言語包。譯文由簡體中文來源詞條（`original/messages.pot`）經機器翻譯自動產生，並隨 Typecho 原始碼更新同步。

## 安裝

1. 複製或下載本倉庫，並複製 `src/langs/` 目錄。
2. 將其中所有 `*.mo` 上傳到 `<你的 Typecho>/usr/langs/`（若不存在請先建立）。
3. 在 `管理後台 > 設置 > 基本設置` 中選擇所需語言。

## 目錄結構

```
original/messages.pot   翻譯模板：從 Typecho 1.3.0 原始碼抽取的簡體中文詞條
original/projects/      各語言的 .po 原始檔案（機器翻譯產生，與模板一一對應）
original/achieves/      官方倉庫遺留的歷史語言包（2018 年人工翻譯，未同步，僅供參考）
src/langs/              編譯完成的 .mo 檔案（安裝時使用）
tools/                  掃描模板與批次翻譯腳本（詳見 tools/README.md）
```

## 更新翻譯

請先在虛擬環境中工作（腳本本身是純 Python，但依賴不應汙染系統直譯器）：

```bash
python -m venv .venv                 # 只需建立一次
.venv\Scripts\activate               # Windows（PowerShell）
# source .venv/bin/activate          # macOS / Linux
pip install tencentcloud-sdk-python-common opencc-python-reimplemented
```

然後執行：

```
python tools/_i18n_analyze.py               # 掃描 Typecho 原始碼 → 重新產生 messages.pot
python tools/_tmt_translate.py              # 機器翻譯全部語言 → 重新產生 projects/*.po
msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo   # 編譯變更的語言檔案
```

譯文由 AI 機器產生，歡迎透過 Pull Request 修訂 `original/projects/` 下的譯文。

> **手工潤飾任意 `.po` 後，請執行 `python tools/_build_tmt_cache.py`。**
> `_tmt_translate.py` 的譯文取自 `tools/runtime/_tmt_cache.json`，手工修改卻未寫回快取的詞條，
> 會在下次翻譯時被機翻結果**靜默覆蓋**。`_build_tmt_cache.py` 會用目前 `original/projects/*.po`
> 整體重建快取，潤飾才能保留，後續執行也能全離線命中。完整順序：改 `.po` → `_build_tmt_cache.py` → `msgfmt` → `_po_check.py`。

另請參閱：http://docs.typecho.org/translate/start
