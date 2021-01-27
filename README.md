# Typechoへのインストール

1. 利用したい言語の`.po`ファイルがここに存在することを確認する

2.必要な`.po`ファイルをダウンロードし、 `.mo`ファイルに変換する。方法は以下の通り:
  + [poedit](https://github.com/vslavik/poedit/releases)を使う
  + `gettext`コマンドを使う: `msgfmt <LANG>.po -o <LANG>.mo`
  + なにか他のgettextソフトを使う

3. Typecho内の`/usr/langs`にアップロードする。もしフォルダが存在しなかったら、アップロードする前に作ってください。

4. Typechoの`控制台`に行き、設定を変更する。`http://your-blog-url.com/admin/options-general.php`で見れるはずです。

以下原文
***
# How to install language for your Typecho

1. Check if the `.po` file for your language already exists.

2. Download the `.po` file you need and convert it to machine-readable `.mo` file. You can do this with:
  + Using [poedit](https://github.com/vslavik/poedit/releases) software
  + Using `gettext` command: `msgfmt <LANG>.po -o <LANG>.mo`
  + Using any other gettext software

3. Upload it to path `/usr/langs` in your Typecho. If that folder doesn't exist, you can create it before upload it.

4. Go to control panel of Typecho to switch to your language. It often locates at `http://your-blog-url.com/admin/options-general.php`

# Multi-language Translation to Typecho

1. [Fork](https://github.com/typecho/languages/fork) this repo and clone to local.
2. Start your translation road by using [PoEdit](http://poedit.net/) or other gettext software. The `message.pot` file contains all recent translation strings, but it is in Chinese, so you might want to start with the English translation file `en_US.po` and update the missing messages from `messages.pot`.
3. Push update to your forked repo, and then pull a request to offical languages repo: named `typecho/languages`.

Also please see http://docs.typecho.org/translate/start

