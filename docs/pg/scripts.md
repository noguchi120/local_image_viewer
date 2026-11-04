# scripts フォルダ：関数一覧

## manage.ps1

| 関数名 | 処理 |
|---|---|
| Invoke-Checked | 外部コマンドを実行し、終了コードが失敗なら起動処理を中止する。 |
| Install-Backend | 専用Python環境を作成し、サーバーの依存ライブラリをインストールする。 |
| Build-Frontend | 必要なら画面ライブラリを取得し、型チェックと配信用ビルドを実行する。 |

本体処理でsetup・start・develop・buildを切り替え、開発用Viteの起動と終了も管理します。
