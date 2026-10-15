# 実装進捗 / ブランチ対応

## 開発対象
- リポジトリ: Spare_parts_management
- 基準: main（初期化）
- 実装: feature/initial-implementation

## 機能別確認表
| 項目 | 実装 | 自動テスト | Windows実機 |
| --- | --- | --- | --- |
| システムマスタ | 実装 | CIで検証予定 | 未確認 |
| 部品マスタ・品番/型式引継ぎ | 実装 | CIで検証予定 | 未確認 |
| 入出庫・履歴訂正 | 実装 | CIで検証予定 | 未確認 |
| マイナス在庫の禁止 | 実装 | CIで検証予定 | 未確認 |
| 下限アラート一括設定 | 実装 | CIで検証予定 | 未確認 |
| 在庫一覧・Excel出力 | 実装 | CIで検証予定 | 未確認 |
| React / pywebview GUI | 実装 | ReactビルドはCIで検証予定 | 未確認 |
| Nuitka Windows standalone/onefile | ビルドスクリプト作成 | 手動GitHub Actions | 未確認 |
| DBバックアップ | 実装 | 実機未確認 | 未確認 |

## mainマージ条件
1. GitHub ActionsのPython・React CI成功
2. Windowsのstandalone EXEが起動し、WebView2描画/入出庫/Excel保存が正常
3. SQLiteを残してEXE入替後も同じ履歴が読める
4. CI結果と本進捗表を更新

Nexusとは独立したプロジェクトとして管理する。
