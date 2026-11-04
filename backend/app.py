"""PCの指定フォルダを一覧・画像・サムネイルとして配信する。"""

import hashlib
import json
import os
import socket
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from natsort import natsorted
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "data"
DIST = PROJECT / "dist"
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}
SETTINGS_LOCK = threading.Lock()
CACHE_LOCKS = [threading.Lock() for _ in range(32)]
app = FastAPI(title="Local Gallery", docs_url=None, redoc_url=None)


class FolderSetting(BaseModel):
    folder: str


def read_settings() -> dict:
    """保存した閲覧フォルダを読み込み、未設定の場合は初期設定を返す。"""
    settings_file = DATA / "settings.json"
    if not settings_file.exists():
        return {"folder": ""}
    try:
        return json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(500, f"設定ファイルを読み込めません: {error}") from error


def resolve_image_path(relative: str, *, directory: bool = False) -> Path:
    """閲覧ルート内の実在するパスを解決し、フォルダや画像の種類を検証する。"""
    folder = read_settings().get("folder")
    if not folder:
        raise HTTPException(409, "PCで閲覧フォルダを設定してください。")
    root = Path(folder).resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(403, "閲覧フォルダの外には移動できません。")
    if directory:
        if not target.is_dir():
            raise HTTPException(404, "フォルダが見つかりません。")
    elif not target.is_file() or target.suffix.lower() not in EXTENSIONS:
        raise HTTPException(404, "画像が見つかりません。")
    return target


@lru_cache(maxsize=20000)
def image_dimensions(filename: str, modified: int, size: int) -> tuple[int, int]:
    """更新日時・サイズをキーに画像寸法をキャッシュし、EXIFの回転を反映する。"""
    with Image.open(filename) as image:
        width, height = image.size
        if image.getexif().get(274) in {5, 6, 7, 8}:
            width, height = height, width
        return width, height


@app.get("/api/health")
def health() -> dict:
    """起動済みサーバーの識別と、起動スクリプトからの疎通確認に応答する。"""
    return {"application": "local-gallery", "status": "ok", "version": "1.0.0"}


@app.get("/api/settings")
def get_settings(request: Request) -> dict:
    """閲覧フォルダと接続用URLを返し、PC自身から設定できるかを通知する。"""
    local = request.client is not None and request.client.host in {"127.0.0.1", "::1"}
    port = request.url.port or 80
    addresses = sorted({
        item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        if not item[4][0].startswith("127.")
    })
    return {
        "folder": read_settings().get("folder", ""),
        "can_configure": local,
        "urls": [f"http://{address}:{port}" for address in addresses],
        "formats": sorted(extension[1:].upper() for extension in EXTENSIONS),
    }


@app.put("/api/settings")
def save_settings(setting: FolderSetting, request: Request) -> dict:
    """PC自身から指定されたフォルダを検証し、UTF-8で設定ファイルを保存する。"""
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "閲覧フォルダの変更はPCのlocalhost画面で行ってください。")
    folder = Path(setting.folder.strip()).expanduser()
    if not setting.folder.strip() or not folder.is_absolute() or not folder.is_dir():
        raise HTTPException(400, "存在するフォルダの絶対パスを指定してください。")
    try:
        with os.scandir(folder) as entries:
            next(entries, None)
        DATA.mkdir(exist_ok=True)
        with SETTINGS_LOCK:
            temporary = DATA / "settings.tmp"
            temporary.write_text(json.dumps({"folder": str(folder.resolve())}, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(DATA / "settings.json")
    except OSError as error:
        raise HTTPException(400, f"フォルダの参照または設定の保存に失敗しました: {error}") from error
    return {"folder": str(folder.resolve())}


@app.get("/api/browse")
def browse(path: str = "") -> dict:
    """現在のフォルダ直下を自然順で列挙し、画像情報と読めなかったファイルを返す。"""
    directory = resolve_image_path(path, directory=True)
    root = Path(read_settings()["folder"]).resolve()
    folders, images, skipped = [], [], []
    try:
        for entry in natsorted(directory.iterdir(), key=lambda item: item.name):
            try:
                if not entry.resolve().is_relative_to(root):
                    continue
                relative = entry.relative_to(root).as_posix()
                if entry.is_dir():
                    folders.append({"name": entry.name, "path": relative})
                elif entry.suffix.lower() in EXTENSIONS and entry.is_file():
                    stat = entry.stat()
                    width, height = image_dimensions(str(entry), stat.st_mtime_ns, stat.st_size)
                    images.append({
                        "name": entry.name, "path": relative, "width": width, "height": height,
                        "size": stat.st_size, "modified": stat.st_mtime_ns,
                        "version": f"{stat.st_mtime_ns}-{stat.st_size}",
                    })
            except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                skipped.append(entry.name)
    except OSError as error:
        raise HTTPException(403, f"フォルダを読み込めません: {error}") from error
    return {"path": "" if directory == root else directory.relative_to(root).as_posix(),
            "name": directory.name, "folders": folders, "images": images, "skipped": skipped}


@app.get("/api/image")
def original_image(path: str) -> FileResponse:
    """指定画像を原寸で配信し、日本語ファイル名でもブラウザ内で表示する。"""
    target = resolve_image_path(path)
    return FileResponse(target, content_disposition_type="inline", filename=target.name)


@app.get("/api/thumbnail")
def thumbnail(path: str) -> FileResponse:
    """回転を補正した一覧用WebPを生成し、更新内容ごとのディスクキャッシュから配信する。"""
    target = resolve_image_path(path)
    stat = target.stat()
    digest = hashlib.sha256(f"{target}:{stat.st_mtime_ns}:{stat.st_size}:480-v1".encode()).hexdigest()
    cache = DATA / "thumbnails" / f"{digest}.webp"
    try:
        with CACHE_LOCKS[int(digest[:2], 16) % len(CACHE_LOCKS)]:
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                with Image.open(target) as image:
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((480, 480))
                    if image.mode not in {"RGB", "RGBA"}:
                        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
                    with tempfile.NamedTemporaryFile(dir=cache.parent, suffix=".webp", delete=False) as temporary:
                        temporary_path = Path(temporary.name)
                    try:
                        image.save(temporary_path, "WEBP", quality=78)
                        temporary_path.replace(cache)
                    finally:
                        temporary_path.unlink(missing_ok=True)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, f"サムネイルを生成できません: {target.name}") from error
    return FileResponse(cache, media_type="image/webp", headers={"Cache-Control": "public, max-age=86400"})


if DIST.is_dir():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
