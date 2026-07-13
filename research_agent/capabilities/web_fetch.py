from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Any


class WebFetchService:
    """Fetch a URL. Saves PDFs to disk, returns text content otherwise."""

    def fetch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        url = str(arguments.get("url", "")).strip()
        if not url.startswith("https://") and not url.startswith("http://"):
            raise ValueError("web_fetch requires a valid URL")

        timeout = int(arguments.get("timeout") or 30)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read(10 * 1024 * 1024 + 1)

        if len(content) > 10 * 1024 * 1024:
            raise ValueError("Response exceeds 10 MB limit")

        if content.startswith(b"%PDF"):
            output_dir = Path(arguments.get("output_dir") or ".")
            output_dir.mkdir(parents=True, exist_ok=True)
            name = hashlib.sha256(url.encode()).hexdigest()[:12] + ".pdf"
            path = output_dir / name
            path.write_bytes(content)
            return {
                "message": f"Fetched PDF ({len(content)} bytes): {path}",
                "artifacts": {"fetched_pdf": str(path)},
                "data": {"url": url, "type": "pdf", "path": str(path), "bytes": len(content)},
            }

        text = content.decode("utf-8", errors="replace")
        return {
            "message": text[:5000] + ("..." if len(text) > 5000 else ""),
            "artifacts": {},
            "data": {"url": url, "type": "text", "length": len(text)},
        }
