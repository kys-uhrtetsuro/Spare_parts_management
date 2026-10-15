# 実装進捗 / ブランチ対応

## 開発対象
- リポジトリ: Spare_parts_management
- 基準: main（初期化）
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
| Nuitka Windows standalone/onefile | ビルドスクリプト作成 | 旧版standaloneは成功。機器・分類・品番引継ぎ修正版はWindowsビルド検証中 | 未確認 |
| DBバックアップ | 実装 | 実機未確認 | 未確認 |

## CI検証結果
- Python 3.12: Migration整合性・Django在庫/API自動テスト成功
- React: TypeScript/Viteビルド成功
- Django配信: ビルド済みReact index検証成功
- Playwright: マスタ作成→補充→下限設定→ExcelダウンロードのE2E成功
- Windows standalone: 旧版のコンパイルは成功。今回変更後のEXE生成とWebView2実機確認は未完了

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
- 生成した歯車・予備品ボックスの図柄をアイコン原本として追加
- `scripts/prepare_icon.py` が原本からReact用PNG・複数サイズICOを生成
- Reactサイドバー・favicon・Windows EXEリソースで共通使用
- Windowsビルド成功後、生成したPNG/ICOと配布用ZIPをGitに登録
- 最新EXEでのWindows実機アイコン反映は検証待ち

## mainマージ条件
1. GitHub ActionsのPython・React CI成功
2. Windowsのstandalone EXEが起動し、WebView2描画/入出庫/Excel保存が正常
3. SQLiteを残してEXE入替後も同じ履歴が読める
4. CI結果と本進捗表を更新

Nexusとは独立したプロジェクトとして管理する。
