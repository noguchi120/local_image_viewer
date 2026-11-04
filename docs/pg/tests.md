# tests フォルダ：関数一覧

## test_api.py / GalleryApiTests

| 関数名 | 処理 |
|---|---|
| setUp | 日本語フォルダとテスト画像を作り、実利用のデータ領域から隔離する。 |
| tearDown | クライアント、寸法キャッシュ、一時フォルダ、差し替えた設定を片付ける。 |
| test_browse_natural_order_and_corrupt_image | 自然順、日本語、非画像除外、破損画像報告を検証する。 |
| test_subfolder_and_unicode_original | 日本語サブフォルダと元画像配信を検証する。 |
| test_traversal_and_non_images_are_rejected | ルート外参照と非画像の配信を拒否することを検証する。 |
| test_remote_cannot_change_folder | LAN端末の閲覧と、PCに限定したフォルダ設定を検証する。 |
| test_invalid_folder_keeps_setting_and_utf8_no_bom | 無効設定の拒否と、UTF-8 BOMなしの設定保持を検証する。 |
| test_exif_rotation_and_thumbnail_preserve_source | EXIF回転補正と元画像の不変を検証する。 |
| test_thumbnail_cache_refreshes_after_change | キャッシュ再利用と元画像更新後の再生成を検証する。 |
| test_parallel_thumbnail_generation_and_transparency | サムネイル同時生成と透明画像の保持を検証する。 |
| test_unconfigured_and_broken_thumbnail | 未設定・破損画像のエラー応答を検証する。 |
| test_static_app_and_health | 画面配信とサーバー起動確認を検証する。 |
