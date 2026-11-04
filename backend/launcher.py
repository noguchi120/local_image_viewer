"""普段使いと開発で共用する、ブラウザ付きサーバー起動処理。"""

import argparse
import json
import socket
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn


def open_when_ready(url: str, page_url: str) -> None:
    """起動完了を待ってからブラウザを開き、起動失敗時には待機を終了する。"""
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=0.5) as response:
                if json.load(response).get("application") == "local-gallery":
                    webbrowser.open(page_url)
                    return
        except (OSError, ValueError):
            time.sleep(0.2)


def main() -> None:
    """起動オプションとポートを確認し、LAN向けサーバーとブラウザを起動する。"""
    parser = argparse.ArgumentParser(description="Local Gallery")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    url = f"http://localhost:{arguments.port}"
    page_url = "http://localhost:5173" if arguments.dev else url
    if not arguments.dev and not (Path(__file__).resolve().parents[1] / "dist" / "index.html").exists():
        raise SystemExit("Build is missing. Run setup.cmd or build.cmd first.")
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1) as response:
            if json.load(response).get("application") == "local-gallery":
                if arguments.dev:
                    raise SystemExit("Stop the running server before starting development mode.")
                print(f"Local Gallery is already running: {page_url}", flush=True)
                if not arguments.no_browser:
                    webbrowser.open(page_url)
                return
    except (OSError, ValueError):
        pass
    with socket.socket() as probe:
        try:
            probe.bind(("0.0.0.0", arguments.port))
        except OSError as error:
            raise SystemExit(f"Port {arguments.port} is in use. Close the other server.") from error
    print(f"\nLocal Gallery: {page_url}\nStop: Ctrl+C\n", flush=True)
    if not arguments.no_browser:
        threading.Thread(target=open_when_ready, args=(url, page_url), daemon=True).start()
    uvicorn.run("backend.app:app", host="0.0.0.0", port=arguments.port,
                reload=arguments.dev, reload_dirs=["backend"] if arguments.dev else None,
                proxy_headers=False)


if __name__ == "__main__":
    main()
