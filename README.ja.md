*Read this in other languages: [English](README.md), [日本語](README.ja.md), [简体中文](README.zh-cn.md).*

## Typechoへのインストール

1. 利用したい言語の`.po`ファイルがここに存在することを確認する

2. 必要な`.po`ファイルをダウンロードし、 `.mo`ファイルに変換する。方法は以下の通り:
  + [poedit](https://github.com/vslavik/poedit/releases)を使う
  + `gettext`コマンドを使う: `msgfmt <LANG>.po -o <LANG>.mo`
  + なにか他のgettextソフトを使う

3. Typecho内の`/usr/langs`にアップロードする。もしフォルダが存在しなかったら、アップロードする前に作ってください。

4. Typechoの`控制台`に行き、設定を変更する。`http://your-blog-url.com/admin/options-general.php`で見れるはずです。
