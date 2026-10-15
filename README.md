# 予備品管理システム

Windows向けローカル在庫管理アプリ。React + Django + SQLite + pywebview + Nuitka。

## 主な機能

- システム別の補充・使用履歴から現在庫を計算（マイナス在庫は禁止）
- 品番・型式・品名の検索補完、未登録品の明示的なマスタ登録
- 品番だけ・型式だけ・両方の更新（同一部品IDを継承、変更履歴も記録）
- 履歴は削除・上書きせず、逆仕訳と訂正履歴を追加
- 下限アラートの2列選択・一括保存（下限は1以上、未設定は監視対象外）
- 現在庫が1以上、または下限監視対象の部品をExcel出力（監視対象の0個を含む）

## 開発環境

Python 3.12、Node.js 24、Windows 10/11 (WebView2 Runtime)。

~~~powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
python backend/manage.py migrate
python launcher.py
~~~

Windows以外でバックエンドのテストを実行する場合:

~~~bash
python -m pip install -r requirements.txt
python backend/manage.py test inventory
~~~

開発フロントエンド: \`cd frontend && npm run dev\` （ViteのプロキシがローカルDjangoへ接続）。Djangoは別ターミナルで \`python backend/manage.py runserver 127.0.0.1:8000\`。

## 配布

\`scripts/build_windows.ps1\` は依存関係をインストールしてフロントをビルドし、Nuitka standalone のEXEを生成する。CIの Windows build は手動実行。standaloneで動作確認した後、\`-Onefile\` で1ファイルEXE化できる。WebView2 Runtimeは配布先PCに必要。

EXEの隣に \`data/inventory.sqlite3\` を作成する。**データフォルダはGit管理・EXEへの同梱対象外**。EXE更新時もこれを残す。アプリのフォルダは書き込み可能な場所へ配置する。DBバックアップは画面から \`data/backups/\` に生成可能。

## 設計・運用

- 親拠点/住所はDBに持たない。1配置ディレクトリにつき1DB、DB内に複数のシステムマスタを持つ。
- 品番と型式の組を全体でユニークにする。同じ部品を複数システムで管理できる。
- APIはDjangoが提供。画面は同一オリジンのReact静的ビルドを配信。ログイン不要、127.0.0.1限定、CSRF検証あり。
- 書込みは単一プロセス内で直列化し、SQLiteトランザクションを使用。複数EXEを同一データフォルダで同時起動しない。
- SQLite DBをネットワーク共有フォルダに配置する運用は非推奨。
- マスタ更新の前後の名称はバージョン履歴へ記録。入出庫時点の品番・型式も履歴へスナップショットする。
- データ移行・バックアップ復元はファイル操作で行う。復元時は**アプリ終了後**にSQLiteファイルを安全なバックアップと入れ替える。
- CIはLinuxでAPI/React検証、Windowsで手動起動のstandaloneビルドを検証する。

開発状況は \`docs/progress.md\` を参照。
