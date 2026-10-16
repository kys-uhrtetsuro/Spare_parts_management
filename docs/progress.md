# 実装進捗 / ブランチ対応

## 開発対象
- リポジトリ: Spare_parts_management
- 配布基準: Release（旧mainに代わる基準ブランチ）
- 実装: feature/initial-implementation

## 機能別確認表
| 項目 | 実装 | 自動テスト | Windows実機 |
| --- | --- | --- | --- |
| システムマスタ | 実装 | Django CI成功 | 未確認 |
| 部品マスタ・品番/型式引継ぎ | 実装 | Django CI成功 | 未確認 |
| 入出庫・履歴訂正 | 実装 | Django CI成功 | 未確認 |
| マイナス在庫の禁止 | 実装 | Django CI成功 | 未確認 |
| 下限アラート一括設定 | 実装 | Django CI成功 | 未確認 |
| 在庫一覧・Excel出力 | 実装 | Django CI成功 | 未確認 |
| React / pywebview GUI | 実装 | Reactビルド・Playwright成功 | 未確認 |
| Nuitka Windows standalone | src集約＋Cランチャー実装 | Windowsビルド検証待ち | 未確認 |
| DBバックアップ | 実装 | 実機未確認 | 未確認 |

## CI検証結果
- Python 3.12: Migration整合性・Django在庫/API自動テスト成功
- React: TypeScript/Viteビルド成功
- Django配信: ビルド済みReact index検証成功
- Playwright: マスタ作成→補充→下限設定→ExcelダウンロードのE2E成功
- Windows onefile: ビルド成功、SQLiteはEXE横のdata/inventory.sqlite3、GUI実機確認は未完了

## 追加要件（今回対応）
- 履歴登録・訂正から企業名を廃止。既存DBは0002マイグレーションで列を削除
- 部品の直接入力時に一意の品番／品番＋型式で完全一致すれば選択を確定
- 候補補完に加え、検索可能な「一覧から選択」モーダルを追加
- システム画面の余分な住所説明とローカル運用バッジを撤去
- Windowsビルド成功後のZIPはreleases/にコミット（CIを再帰起動しない）
- 配布用ZIPのCI結果・実行端末での動作確認は別管理

## 追加機能・修正（次の実装コミット）
- 機器マスタ（名称・通称）、機器にぶら下がる任意の部位マスタを新設
- 部品分類マスタと、部品マスタへの機器・部位・分類割当
- 旧品番や旧型式を上書きせず、後継部品を別IDで作成してリンクする
- 旧版で既に変更した部品の元番号を入出庫スナップショットから復元するマイグレーション
- 入出庫登録成功後にモーダルを閉じる。登録後の一覧再読込エラーを区別する
- 部品検索候補は最大4件に絞り、全件検索はスクロール可能な一覧モーダルへ
- Python/Djangoとブラウザの追加回帰テストに反映

## 新旧型式と逆引きの検証
- 品番のみ、型式のみ、両方同時の更新は後継レコードとして登録
- 旧マスタを残し、旧品番・旧型式の履歴と在庫を別々に保持
- 部品一覧・現在庫一覧から機器、部位、分類で絞り込み可
- 機器・部位・分類マスタから関連部品一覧へ遷移可
- 下限値とExcel出力は従来どおりシステム×部品単位
- Linux Djangoテスト・Reactビルド・Playwrightは先行コミットで成功
- 最新版Windows standalone配布ZIPのGit自動登録はビルド結果待ち

## アプリアイコン
- 歯車・予備品ボックスの原本画像 `assets/spare_parts.webp` をGitへ追加
- `scripts/prepare_icon.py` が原本からReact用PNG・複数サイズICOを生成
- Reactサイドバー・favicon・Windows EXEリソースで共通使用
- Windowsビルド成功後、生成したPNG/ICOと配布用ZIPをGitに登録（ビルド結果確認待ち）
- 最新EXEでのWindows実機アイコン反映は検証待ち

## Excelシステム移植
- 現在庫Excelの非表示シートにシステム・機器・部位・分類・部品・新旧対応・下限・在庫を保持
- Excel取込前にプレビューし、名称衝突と二重取込を検知
- 編集可能な内容は「現在庫」の在庫数量・下限値
- 在庫は新規システムの期首補充履歴として追加（元履歴はコピーしない）
- 単一システムなら取込先のシステム名を変更できる
- SQLiteバックアップは従来どおりファイルコピーで復元
- Windows 11 64bit推奨、Windows 10 64bit対応対象（実機未検証）
- 取り込み回帰テスト・Django・Playwright CI成功。最新Windows成果物は確認待ち

## 配布前の最終調整
- [実装] メニューを【在庫管理】・【システム管理】の２グループへ再編、アコーディオン開閉
- [実装] 在庫管理を初期展開・システム管理を初期折り畳み、画面切替後も状態維持
- [実装] システムごとに機器マスタを管理、部位もその機器に従属
- [実装] 部品は共通、機器／部位への割当はシステムと部品の組み合わせで管理
- [実装] 部品分類は共通マスタとして維持、Excel移植もシステム別機器割当を復元
- [実装] 在庫サマリーは最終入出庫日時降順、それ以外のID並びは昇順
- [検証済み] 0005 マイグレーション、Django、Playwrightの回帰テスト成功。Windows成果物は確認待ち
- [保留] mainへのマージはCI成功・Windows実機確認後

## 後継品フィルタとコピー機能（配布前追加）
- [実装] 後継登録済みの部品は部品マスタ一覧から初期除外。「後継登録済みを除外」を解除すると旧品を表示できる
- [実装] 後継登録済みの部品は編集・後継登録をロック（Django APIも拒否）
- [実装] 入庫は現行品のみ（旧品への補充をAPIでも拒否）、出庫は対象システムで在庫1以上の部品のみ（旧品の残存在庫も出庫可能）。負在庫は禁止。履歴訂正も維持
- [実装] 部品選択モーダルで機器・部位・分類と文字列の複合検索
- [実装] 部品コピーは新規レコードとして登録。品番・型式・分類・機器割当を複写、在庫や新旧リンクを引き継がない
- [実装] 機器コピーは同一／別システムへ名称・通称・全部位を複写。部品割当・在庫は複写しない
- [検証済み] 旧品出庫・補充拒否・在庫1以上の候補限定・出庫数量上限・入庫出庫の分離をDjangoおよびブラウザE2Eで確認（CI 38681818459 / 38681824038）
- [検証待ち] Windowsビルドと配布ZIPのGit登録、Windows実機起動
- [保留] mainマージはCI成功とWindows実機確認後

## タスクバーアイコン修正
- [修正] pywebview 6.2 標準の `start(icon=...)` を利用し、Windows WinForms生成時にICOを設定
- [修正] 起動後の `WM_SETICON` とウィンドウタイトルによる曖昧なハンドル探索を削除
- [修正] 起動前に固定AppUserModelIDを設定し、タスクバーグループのアプリ識別子を統一
- [検証] GUI生成引数とICO欠落検出をPython単体テスト、Windows EXEのアイコンリソースをビルド後にチェック
- [保留] 最新のWindows配布ZIPの成功確認とユーザー端末でのタスクバー表示を確認
- [参考] 旧版をピン留め済みならタスクバーから解除して更新版を再登録する場合あり

## 後継品の下限アラート整理
- [実装] 下限設定の新規追加は現行品のみ。後継登録済み旧品の既存設定は、在庫が残る間だけ維持・設定値変更不可
- [実装] 後継品に在庫が入れば同一システムの下限値を移植。既存後継設定があればその値を優先し、二重監視を解除
- [実装] 後継品の入庫前に旧品を使い切ったら旧品の監視設定を解除
- [実装] 品番・型式が複数世代あっても末端まで追跡。履歴訂正・一括保存・Excel移植でも状態を正規化
- [実装] 過去の設定もマイグレーション0006で整合性を修復
- [検証済み] Djangoテスト・Reactビルド・Playwright操作テスト成功（CI 38683110833 / 38683115818）
- [検証待ち] Windows Nuitkaビルド・配布ZIPのGit登録・Windows実機での動作確認

## ブランチ整理と配布準備（2026-10-15）
- [完了] 旧mainからReleaseを作成し、PR #1をマージ（Release統合コミット a42817b7）
- [完了] 以前のWindows Nuitka実行をキャンセルし、Releaseの最新コミットだけを対象にビルド
- [完了] CIはReleaseへの統合コミットで成功（GitHub Actions 38684622907）
- [実行中] Windows Nuitkaの最新ビルド（90分の上限、古いReleaseビルドは自動取消）
- [配布待ち] 成功時にreleases/SparePartsManagement-standalone.zip、PNG/ICOをReleaseへ自動コミット
- [未対応・GitHub設定操作] リポジトリのdefault_branchは現在もmain。GitHubのSettings → General → Default branchでReleaseへ切替が必要。その後mainを削除すれば完全移行（この操作は接続中のGitHubツールでは非対応）
- [未確認] ユーザーWindows PCでのWebView2起動・タスクバーアイコンの実機確認

## Nuitkaコンパイルキャッシュ（次回ビルド用）
- [マージ済み] `feature/nuitka-cache` で `NUITKA_CACHE_DIR` を固定し、GitHub Actionsのrestore/saveでCコンパイル結果（ccache/clcache）を継続利用
- [マージ済み] キャッシュキーはWindows/x64・Python 3.12・`requirements.txt` のハッシュで分離。各実行は固有キーで保存し、次回は互換キーから復元
- [マージ済み] ビルド成功直後にキャッシュを保存し、配布ZIP登録の成否とは分離
- [マージ済み] workflow本体と進捗文書のみの更新はWindowsビルドを再起動しない。手動実行は維持
- [統合済み] キャッシュ対応PR #2をReleaseへマージ（f0072ab8）。キャッシュは次回以降のWindowsビルドで保存・復元
- [検証待ち] Release統合後のビルド初回でキャッシュ保存、2回目以降でキャッシュ復元とヒット率を確認。高速化の程度はC生成コードの差分次第

## 1部品への複数機器・部位割当
- [実装] 中間モデル SystemPartPlacement の一意制約を「システム×部品×機器×部位」に変更
- [実装] 同じ機器の部位違い、別機器、部位なしを複数行で登録・編集可能。完全重複は拒否
- [実装] APIで `placements` 配列を検証し、旧形式の単一equipment_id/section_id指定も後方互換で受理
- [実装] 部品の後継登録では全機器割当を引継ぎ、通常編集は選択中システムだけ更新
- [実装] 部品マスタの一覧・逆引き・フィルター、および複数行を持つ編集モーダルを対応
- [実装] Excel出力は複数の割当レコードを非表示シートに保持。V3で書き出し、V2/V3の取り込みをサポート
- [検証済み] Djangoマイグレーション／回帰テスト・TypeScriptビルド・Playwright E2E成功（CI #38687272448 / #38687293404）
- [統合済み] PR #3をReleaseへマージ（af35659c）。CIとWindows配布ビルドはReleaseの最新コミットで確認

## Windows Onefileへの配布切替
- [実装] Nuitka既定ビルドを`--mode=onefile`に変更。出力は`build/SparePartsManagement.exe`
- [実装] Python・React・pywebview・ICOはEXE内部に含め、起動時の一時展開先から読み込む
- [実装] SQLiteの保存先は`sys.argv[0]`（元EXEのパス）を基準とし`data/inventory.sqlite3`へ固定。無ければ自動作成し、既存DBは更新しない
- [検証] 一時展開フォルダと永続DBフォルダのパスが別であること、既存DBが消えないことを単体テスト追加
- [検証] Onefile EXEのWindowsアイコンリソースをビルド後に確認する
- [実装] Actions成果物は単体EXE、Gitへ格納可能ならGitコミット。大きい場合はGitHub Releases資産として配布
- [更新] 配布を二方式併用に変更し、Onefile EXEとStandalone ZIPを共存させる
- [検証待ち] Windows実機Onefile起動、初回DB作成、EXE差替後のDB保持

## 起動不具合の最小診断修正（2026-10-15）
- [修正] マイグレーションをWaitress/pywebviewのimportより先に実行
- [修正] `data/startup.log` に起動段階と日時、例外発生時の完全なトレースバックを記録
- [修正] 例外時・通常終了時にインスタンスロックとサーバーをfinallyで解放
- [テスト] SQLiteマイグレーション段階で意図的に例外を発生させ、ログ記録と処理順を自動検証
- [実機検証待ち] ユーザーPCで無反応となるEXEのログから停止段階を特定（旧EXEはログ機能未搭載）
- [配布] 新版EXEのビルド成功・Windows実機起動は未確認

## Onefile外部データの一本化
- [実装] Djangoの秘密鍵を`inventory.sqlite3`内の`spareparts_configuration`テーブルに保存。データ保持に必要なファイルはSQLiteのみ
- [実装] 旧`.django-secret`があれば秘密鍵をSQLiteへ移植し、保存完了後に旧ファイルを整理
- [維持] `data/startup.log`（診断ログ）と`.instance.lock`（起動ロック）は補助ファイルとして自動生成。既存のDB・データは変更しない
- [検証待ち] 統合後のWindows Onefile実機動作、既存DB・秘密鍵の維持

## Windows二方式配布とDjango日本語リソース修正（2026-10-15）
- [修正] GitHub ActionsでOnefile EXEとStandaloneフォルダを同一ソースから連続ビルド、共通のPython/npm導入・Nuitkaコンパイルキャッシュを使用
- [修正] `releases/SparePartsManagement.exe` と `releases/SparePartsManagement-standalone.zip` を両方保存。GitHubの単一ファイル制限超過時は両方をGitHub Releases資産として保存
- [修正] 以前確認されたDjango初期化エラー「No translation files found for default language ja」に対処し、Nuitkaへ日本語翻訳リソースを明示同梱
- [検証] Standalone成果物内に`django/conf/locale/ja/LC_MESSAGES/django.mo`が存在することをビルド時に検証
- [維持] SQLite外部保存先 `data/inventory.sqlite3`、`data/startup.log`、既存マイグレーションと秘密鍵の移行仕様は変更しない
- [確認待ち] 両方式のWindowsビルド成功、利用者端末での起動・GUI表示・セキュリティ製品の検知状況

## Releaseマージ条件
1. GitHub ActionsのPython・React CI成功
2. Windowsのstandalone EXEが起動し、WebView2描画/入出庫/Excel保存が正常
3. SQLiteを残してEXE入替後も同じ履歴が読める
4. CI結果と本進捗表を更新

Nexusとは独立したプロジェクトとして管理する。

## 配布ブランチ・CI整理（2026-10-15）
- Windows NuitkaビルドはReleaseだけで自動実行する。開発ブランチではソーステストのみ実行。
- concurrencyで新しいWindowsビルドを優先し、過去の実行はactions:writeで停止要求。
- 一時的に走っていた旧開発ブランチのビルドもCIから一括キャンセル。
- リリース成果物はRelease/release配下ZIPに登録。配布用画像PNG/ICOもコミット。
- ドキュメント更新のみは既存EXEのビルド結果を無効化しない。コード更新時は古い成果物を登録しない。
- Release統合とWindows EXE実機起動は別途確認。

- EXEアイコン: gear / spare parts box（256〜16px、EXEに埋込み）


- 配布成果物ビルド元: 995db500979faf1ab55fbf263c9819f66aae5ddd
- Onefile成果物: onefile-995db500979f / 42323456 bytes（Git制限超過時はGitHub Releases）



## Standalone配布のsrc集約（2026-10-15）
- [実装] Nuitka standalone本体と依存ファイルをZIPのsrcフォルダへ集約（PyInstallerは不採用）
- [実装] 配布ルートにC製SparePartsManagement.exeを追加。src内のNuitka本体を子プロセスとして起動、両EXEにアイコンを埋込む
- [実装] SPARES_APP_ROOTで永続データを外側のdata/inventory.sqlite3に固定。既存SQLite・ログ・ロック・バックアップを維持
- [実装] CIの配布をstandalone ZIP一本に整理し、旧onefile EXEの新規配布を停止。Nuitkaコンパイルキャッシュは維持
- [検証] Python単体テストでsrcとdataのパス分離および既存SQLite非上書きを確認
- [検証待ち] GitHub ActionsでMSVCランチャーのビルド、アイコン、Django日本語リソース、ZIP配置
- [実機確認待ち] pywebview起動、入出庫、SQLite既存データ、終了時のロックとセキュリティ製品の検知状況
- [ブランチ] feature/standalone-src-launcher（ReleaseへPR反映）

- Standalone配布ビルド元: 9d55e481f82cfdb6507429916266576a567081a9
- Standalone配布ZIP: 64260119 bytes（Git制限超過時はGitHub Releases）


## Windows Cコンパイル進捗の表示（2026-10-15）
- [実装] Windows GitHub ActionsでNuitka standaloneビルドの実行中に生成Cファイル数とOBJファイル数を15秒おきに監視し、コンパイル工程内の進捗率（概算）をログ表示
- [維持] Nuitkaのコンパイル設定、キャッシュキー、配布成果物、Python 3.12とrequirements.txtは変更しない
- [維持] Windowsビルド完了時の既存ZIP（約64.3MB）は再生成しない。フロー変更のみではWindowsビルドを自動起動しない設定を維持
- [検証待ち] 次回WindowsビルドでOBJ数/生成Cファイル数の表示を確認。リンク・ZIP作成処理は表示対象外
- [確認] 修正開始時点で実行中のWindowsビルドなし。直近のRelease Windowsビルド #38714119795 は成功済み

## Excel出力のWindowsダウンロード修正（2026-10-16）
- [原因] pywebview 6.2の標準設定でALLOW_DOWNLOADSがFalse。DjangoのExcel生成とブラウザE2Eは成功するが、デスクトップWebViewのダウンロードが禁止されていた
- [修正] show_desktopでcreate_windowより前にALLOW_DOWNLOADSをTrueへ設定し、EdgeChromium標準の保存先指定ダイアログを有効化
- [維持] /api/exportのxlsx内容・システム/機器/部位/分類フィルタ・Excel取込・Nuitka・既存dataディレクトリは変更しない
- [テスト] ウィンドウ生成前にダウンロードが許可されていることをモック単体テストで確認
- [検証待ち] CIのWindowsアイコン/起動テスト・Django/React E2Eおよび新版EXEのWindows実機で「名前を付けて保存」を確認
- [ブランチ] bugfix/pywebview-excel-download → Release
