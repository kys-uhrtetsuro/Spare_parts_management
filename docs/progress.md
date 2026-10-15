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
| Nuitka Windows standalone/onefile | ビルドスクリプト作成 | GitHub Actionsビルド実行中 | 未確認 |
| DBバックアップ | 実装 | 実機未確認 | 未確認 |

## CI検証結果
- Python 3.12: Migration整合性・Django在庫/API自動テスト成功
- React: TypeScript/Viteビルド成功
- Django配信: ビルド済みReact index検証成功
- Playwright: マスタ作成→補充→下限設定→ExcelダウンロードのE2E成功
- Windows standalone: 実行環境でのコンパイルとWebView2実機確認は未完了

## mainマージ条件
1. GitHub ActionsのPython・React CI成功
2. Windowsのstandalone EXEが起動し、WebView2描画/入出庫/Excel保存が正常
3. SQLiteを残してEXE入替後も同じ履歴が読める
4. CI結果と本進捗表を更新

Nexusとは独立したプロジェクトとして管理する。
