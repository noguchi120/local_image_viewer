# src フォルダ：関数一覧

## App.vue

| 関数名 | 処理 |
|---|---|
| visibleImages（computed） | 名前検索と並び替えを適用し、一覧とビューアーの画像順を揃える。 |
| visibleFolders（computed） | 名前検索をフォルダ一覧へ適用する。 |
| breadcrumbs（computed） | 現在の相対パスからパンくずを作る。 |
| rootName（computed） | 設定したフォルダの末尾名を画面表示用に取り出す。 |
| request | APIを呼び出し、失敗を画面表示用の例外へ変換する。 |
| loadFolder | 古い取得を中止し、フォルダ一覧・画像URL・履歴・表示状態を更新する。 |
| initialize | 設定を読み込み、設定済みの閲覧フォルダを開く。 |
| saveFolder | PCからフォルダ設定を保存し、新しいルートへ切り替える。 |
| openGallery | 表示中の画像群をPhotoSwipeへ渡し、拡大・スワイプ表示を開始する。 |
| openGallery 内 onInit | PhotoSwipeのキャプション表示を初期化する。 |
| openGallery 内 updateCaption | スワイプで変わった画像のファイル名をキャプションに表示する。 |
| generateQr | 選択したLAN接続URLのQRコードをPC内で生成する。 |
| openConnect | 接続ダイアログを開き、QRコードの生成とフォーカス移動を行う。 |
| copyUrl | 接続先URLをコピーし、コピーできない環境では選択状態にする。 |
| onPopState | ブラウザ履歴に合わせてフォルダを再表示する。 |
| onKeyDown | ダイアログのEscape操作とフォーカス循環を処理する。 |
| ダイアログ状態のwatchコールバック | 入力先へのフォーカス移動と、閉じたときのフォーカス・スクロール復元を行う。 |
| onMounted コールバック | 初期取得と履歴・キー操作のイベント登録を行う。 |
| onUnmounted コールバック | 取得・ビューアー・イベント登録を解除する。 |

main.ts はVueのマウント処理のみで、独自関数はありません。
