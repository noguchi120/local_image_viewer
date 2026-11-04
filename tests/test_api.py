"""画像配信・フォルダ制限・キャッシュを一時フォルダで検証する。"""

import hashlib
import io
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

import backend.app as gallery


class GalleryApiTests(unittest.TestCase):
    def setUp(self):
        """テスト専用の日本語フォルダと画像を用意し、実利用の設定から隔離する。"""
        artifacts = gallery.PROJECT / ".test-artifacts"
        artifacts.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=artifacts)
        self.base = Path(self.temporary.name)
        self.root = self.base / "写真フォルダ"
        self.root.mkdir()
        (self.root / "アルバム").mkdir()
        Image.new("RGB", (120, 80), "green").save(self.root / "画像2.jpg")
        Image.new("RGBA", (100, 100), (0, 128, 255, 100)).save(self.root / "画像10.png")
        Image.new("RGB", (60, 90), "orange").save(self.root / "アルバム" / "一枚.webp")
        (self.root / "破損.jpg").write_bytes(b"not an image")
        (self.root / "メモ.txt").write_text("画像ではありません", encoding="utf-8")
        self.data_patch = patch.object(gallery, "DATA", self.base / "data")
        self.data_patch.start()
        self.client = TestClient(gallery.app, client=("127.0.0.1", 50000))
        response = self.client.put("/api/settings", json={"folder": str(self.root)})
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        """クライアントとキャッシュを解放し、一時データと設定の差し替えを片付ける。"""
        self.client.close()
        gallery.image_dimensions.cache_clear()
        self.data_patch.stop()
        self.temporary.cleanup()

    def test_browse_natural_order_and_corrupt_image(self):
        """自然順、日本語の名前、非画像の除外、破損画像の報告を検証する。"""
        response = self.client.get("/api/browse")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["path"], "")
        self.assertEqual([item["name"] for item in body["images"]], ["画像2.jpg", "画像10.png"])
        self.assertEqual(body["folders"], [{"name": "アルバム", "path": "アルバム"}])
        self.assertEqual(body["skipped"], ["破損.jpg"])

    def test_subfolder_and_unicode_original(self):
        """日本語サブフォルダを開き、元画像を変更せずそのまま取得できることを検証する。"""
        body = self.client.get("/api/browse", params={"path": "アルバム"}).json()
        self.assertEqual(body["path"], "アルバム")
        response = self.client.get("/api/image", params={"path": body["images"][0]["path"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, (self.root / "アルバム" / "一枚.webp").read_bytes())
        self.assertIn("inline", response.headers["content-disposition"])

    def test_traversal_and_non_images_are_rejected(self):
        """閲覧ルート外や非画像へのアクセスを、URLの各入口で拒否することを検証する。"""
        for endpoint in ("browse", "image", "thumbnail"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(f"/api/{endpoint}", params={"path": "../outside.jpg"})
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/api/image", params={"path": "メモ.txt"}).status_code, 404)
        self.assertEqual(self.client.get("/api/browse", params={"path": "missing"}).status_code, 404)

    def test_remote_cannot_change_folder(self):
        """スマホ相当の接続からは一覧を開けるが、フォルダ設定は変更できないことを検証する。"""
        with TestClient(gallery.app, client=("192.168.1.25", 50000)) as remote:
            self.assertFalse(remote.get("/api/settings").json()["can_configure"])
            self.assertEqual(remote.get("/api/browse").status_code, 200)
            self.assertEqual(remote.put("/api/settings", json={"folder": str(self.base)}).status_code, 403)
        self.assertEqual(gallery.read_settings()["folder"], str(self.root.resolve()))

    def test_invalid_folder_keeps_setting_and_utf8_no_bom(self):
        """無効なパスを保存せず、既存設定がUTF-8 BOMなしで保持されることを検証する。"""
        for folder in ("", "relative/path", str(self.base / "missing")):
            self.assertEqual(self.client.put("/api/settings", json={"folder": folder}).status_code, 400)
        content = (gallery.DATA / "settings.json").read_bytes()
        self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
        self.assertIn("写真フォルダ", content.decode("utf-8"))
        self.assertEqual(gallery.read_settings()["folder"], str(self.root.resolve()))

    def test_exif_rotation_and_thumbnail_preserve_source(self):
        """EXIF回転を寸法とサムネイルに反映し、元画像を変更しないことを検証する。"""
        filename = self.root / "回転.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (80, 40), "blue").save(filename, exif=exif)
        before = hashlib.sha256(filename.read_bytes()).digest()
        body = self.client.get("/api/browse").json()
        image = next(item for item in body["images"] if item["name"] == "回転.jpg")
        self.assertEqual((image["width"], image["height"]), (40, 80))
        response = self.client.get("/api/thumbnail", params={"path": "回転.jpg"})
        self.assertEqual(response.status_code, 200)
        with Image.open(io.BytesIO(response.content)) as thumb:
            self.assertEqual(thumb.size, (40, 80))
        self.assertEqual(hashlib.sha256(filename.read_bytes()).digest(), before)

    def test_thumbnail_cache_refreshes_after_change(self):
        """同じ画像はキャッシュを再利用し、変更後は新しい寸法・サムネイルを返すことを検証する。"""
        filename = self.root / "画像2.jpg"
        first = self.client.get("/api/thumbnail", params={"path": "画像2.jpg"})
        caches = list((gallery.DATA / "thumbnails").glob("*.webp"))
        self.assertEqual(len(caches), 1)
        cache_time = caches[0].stat().st_mtime_ns
        self.assertEqual(self.client.get("/api/thumbnail", params={"path": "画像2.jpg"}).content, first.content)
        self.assertEqual(caches[0].stat().st_mtime_ns, cache_time)
        old_stat = filename.stat()
        Image.new("RGB", (60, 140), "red").save(filename)
        os.utime(filename, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000_000))
        second = self.client.get("/api/thumbnail", params={"path": "画像2.jpg"})
        self.assertNotEqual(first.content, second.content)
        self.assertEqual(len(list((gallery.DATA / "thumbnails").glob("*.webp"))), 2)
        body = self.client.get("/api/browse").json()
        image = next(item for item in body["images"] if item["name"] == "画像2.jpg")
        self.assertEqual((image["width"], image["height"]), (60, 140))

    def test_parallel_thumbnail_generation_and_transparency(self):
        """同一サムネイルの同時生成を検証し、透明PNGが正しいWebPになることを確認する。"""
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(self.client.get, "/api/thumbnail", params={"path": "画像10.png"}) for _ in range(6)]
            responses = [future.result() for future in futures]
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertEqual(len({response.content for response in responses}), 1)
        self.assertEqual(len(list((gallery.DATA / "thumbnails").glob("*.webp"))), 1)
        with Image.open(io.BytesIO(responses[0].content)) as image:
            self.assertEqual(image.mode, "RGBA")

    def test_unconfigured_and_broken_thumbnail(self):
        """破損画像とフォルダ未設定の失敗を、クライアントが判別できる状態で返すことを確認する。"""
        self.assertEqual(self.client.get("/api/thumbnail", params={"path": "破損.jpg"}).status_code, 422)
        (gallery.DATA / "settings.json").unlink()
        self.assertEqual(self.client.get("/api/browse").status_code, 409)
        self.assertEqual(self.client.get("/api/settings").json()["folder"], "")

    def test_static_app_and_health(self):
        """ビルドした画面と起動識別用のヘルスチェックが同じサーバーから配信されることを確認する。"""
        response = self.client.get("/api/health")
        self.assertEqual(response.json()["application"], "local-gallery")
        if gallery.DIST.is_dir():
            response = self.client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Local Gallery", response.text)


if __name__ == "__main__":
    unittest.main()
