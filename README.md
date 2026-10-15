# 予備品管理システム

React + Django + SQLite + pywebview + Nuitka によるWindows用ローカル在庫管理。

## 機能

- システムマスタ（同一SQLiteに複数システム、親拠点や住所のDB管理は不要）
- 品番・型式・品名の複合マスタとオートコンプリート、未登録品の明示登録
- 補充/使用の履歴蓄積で現在庫を集計、マイナス在庫は禁止。登録者名を保持し、企業名の入力は不要
- 履歴訂正は取消逆仕訳＋新規履歴の追記（元履歴は変更せず保持）
- 品番/型式/両方の変更は後継品を新規レコードとして作成し旧品と連結する。旧品番の在庫・履歴は旧品番のまま維持し、在庫は自動移動しない
- 機器マスタ（正式名・通称）、機器の任意の複数部位、部品分類マスタを独立して管理。部品に機器・部位・分類を任意で割当
- Django Adminの選択画面を参考にした下限設定2列UI、設定値1以上、複数件一括保存
- 現在庫1以上もしくは下限設定ありをExcelで出力（設定済み0個も出力）
- DBバックアップ作成

## 必要環境

- 開発: Python 3.12、Node.js 24、npm
- 利用者: Windows 10/11、Microsoft Edge WebView2 Runtime。Python、Node.js、DBサーバーは不要
- SQLiteのファイルはEXEと別に保存。配布先のフォルダに書込権限が必要

## 開発時の実行

Windows PowerShell:

~~~powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
cd frontend
npm install
cd ..
python scripts/prepare_icon.py
cd frontend
npm run build
cd ..
python backend/manage.py migrate
python launcher.py
~~~

フロント開発: 別ターミナルで \`python backend/manage.py runserver 127.0.0.1:8000\`、
\`cd frontend && npm run dev\`。ViteはAPIをローカルDjangoへプロキシする。

Djangoの自動テスト:

~~~powershell
python backend/manage.py test inventory
python backend/manage.py makemigrations --check --dry-run
~~~

## アイコン生成

歯車と予備品ボックスのアイコンを、GUI・ブラウザfavicon・EXEで共通使用する。
原本は `assets/spare_parts_icon.webp.b64`。初期実行またはビルド前に生成する。

~~~powershell
python scripts/prepare_icon.py
~~~

生成物は `frontend/src/assets/spare_parts.png` と `assets/spare_parts.ico`。
後者は16/24/32/48/64/128/256pxを含み、NuitkaがEXEのアイコンリソースに埋め込む。
Windowsビルド成功時に生成物もGitへコミットする。

## Windows EXE作成

~~~powershell
./scripts/build_windows.ps1
~~~

Windows向けNuitka standaloneビルドを作成。単体EXEの検証は
\`./scripts/build_windows.ps1 -Onefile\` で実施（初回はstandalone推奨）。
GitHub Actions は開発ブランチ更新時に Windows Nuitkaビルドし、成功した配布ZIPを releases/SparePartsManagement-standalone.zip としてGitにコミットする（約数十MB）。
ブラウザではなく独立ウィンドウで起動し、Djangoは127.0.0.1限定のWaitressで動作する。

Nuitka と pywebview の既知互換性のため、pywebviewは6.2を採用している。

部品は手入力（既存品番が一意に完全一致する場合）・少数件の候補補完・スクロール可能な一覧モーダルで選択可能。未登録品は明示操作で新規登録する。

## 配布・バックアップ

standalone配布時は \`build/launcher.dist/\` の中身を丸ごとコピーする。
Windows上で \`SparePartsManagement.exe\` を実行すると自動でマイグレーションし、
EXEと同じディレクトリの \`data/inventory.sqlite3\` を作成する。

同じ場所の \`data\` フォルダは更新時にも残す。DBはGit・Nuitkaへ同梱しない。
画面の「DBバックアップを作成」で \`data/backups/\` に日付付きコピーを作成。
復元する場合はアプリを完全終了し、バックアップを \`data/inventory.sqlite3\` へコピーする。
SQLite DBをネットワーク共有ドライブに置かないこと。
単一データフォルダで複数のEXEを同時起動しないこと。

## 開発方針・進捗

\`docs/progress.md\` にGitブランチと機能別検証状況を記載。
仕様と進捗を一致させてからmainへマージする。

既存データの品番上書きはマイグレーション0003で過去のスナップショットに基づき復元する。更新前にバックアップを取ること。

## Excelによるシステム別フォーク（取り込み・書き出し）

1. 現在庫一覧で対象システムを選ぶ（「すべて」なら複数システムを出力）。
2. 「Excel出力」で可視シート「現在庫」と非表示のマスタ情報シートを一緒に保存する。
3. コピー先のアプリで「Excel取込」→xlsx選択→プレビュー→確定。
4. 同名システムがある場合、単一システムのExcelなら別の移植先名称を指定できる。

「現在庫」シートの**現在庫（0以上）と下限値（空欄または1以上）**のみ編集可能。
行の削除・品番や品名の改変・非表示シートの削除は取り込みエラーとなる。
非表示シートには使用された部品、品番・型式の新旧対応、機器・部位・分類、
システム、在庫・下限のスナップショットを含める。履歴に登場して在庫0となった
部品も非表示シート側に残す。

**移植後の在庫は期首補充として記録**し、元の入出庫イベントそのものは移植しない。
元システムのデータも変更しない。同じファイルの再取り込みは禁止。
別の日時に再出力したExcelは別ファイルと判定されるため、移植先の名称を
重複させて安易に複数回取り込まないこと。マスタの品番・型式等が既存DBと矛盾する
場合は、トランザクション全体を取り消す。

DB全体をそのまま復元したい場合は、アプリを終了して`data/inventory.sqlite3`を
ファイルコピーで置き換える。これはExcel移植と異なり、履歴も丸ごと引き継ぐ。

## Windows対応範囲

- 配布用のGitHub Actions Windowsビルドは**64bit用**。Windows 11 64bitを推奨。
- Windows 10 64bitも対象（WebView2 Runtimeが必要、EXE実機での確認を継続）。
- Windows 10 32bitやWindows 8.1以前は非対応。
- Windows 10は2025年10月に通常サポート終了。利用PCのセキュリティ更新を確認すること。
