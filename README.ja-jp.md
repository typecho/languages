# Typecho 言語パック

*他の言語で読む：[English](README.md), [简体中文](README.zh-cn.md), [繁體中文](README.zh-cht.md)*

**Typecho 1.3.0** 向けの多言語言語パック。原文は簡体字中国語のテンプレート `original/messages.pot` を基に機械翻訳で自動生成され、Typecho 本体の更新に合わせて同期されています。

## インストール

1. このリポジトリを取得し、`src/langs/` フォルダをコピーしてください。
2. `*.mo` ファイルをすべて `<Typecho のディレクトリ>/usr/langs/` にアップロードしてください（フォルダが無い場合は作成してください）。
3. `管理画面 > 設定 > 基本設定` で使用する言語を選択してください。

## ディレクトリ構成

```
original/messages.pot   翻訳テンプレート: Typecho 1.3.0 のソースから抽出した簡体字中国語の文字列
original/projects/      各言語の .po ソースファイル（機械翻訳で生成、テンプレートと一対一で対応）
original/achieves/      上流リポジトリから引き継いだ旧言語パック（2018 年・手動翻訳、未同期・参考用）
src/langs/              コンパイル済みの .mo ファイル（インストール用）
tools/                  テンプレート走査・一括翻訳スクリプト（tools/README.md 参照）
```

## 翻訳の更新

まず仮想環境を用意してください（スクリプト自体は純粋な Python ですが、依存関係がシステムの Python に漏れないようにするためです）：

```bash
python -m venv .venv                 # 一度だけ作成
.venv\Scripts\activate               # Windows (PowerShell)
# source .venv/bin/activate          # macOS / Linux
pip install tencentcloud-sdk-python-common opencc-python-reimplemented
```

その後：

```
python tools/_i18n_analyze.py             # Typecho のソースを走査 → messages.pot を再生成
python tools/_tmt_translate.py            # 全言語を機械翻訳 → projects/*.po を再生成
msgfmt original/projects/xx_XX.po -o src/langs/xx_XX.mo   # 変更した言語ファイルをコンパイル
```

翻訳は AI 機械生成です。`original/projects/` 配下の翻訳の改善 Pull Request を歓迎します。

> **`.po` を手作業で調整した後は `python tools/_build_tmt_cache.py` を実行してください。**
> `_tmt_translate.py` は `tools/runtime/_tmt_cache.json` から訳文を読み込むため、キャッシュにない手修正は
> 次回の実行時に機械翻訳の結果で**上書きされて消えます**。`_build_tmt_cache.py` は現在の `original/projects/*.po`
> からキャッシュ全体を再構築するので、手修正が保持され、以降の実行も完全オフラインで動きます。順序：`.po` を編集 → `_build_tmt_cache.py` → `msgfmt` → `_po_check.py`。

関連リンク: http://docs.typecho.org/translate/start
