"""Serves the built frontend (Vite `dist/`) from the same process, outside `/api`.

Installed as the router's *default* handler, so it only sees requests that no API route matched:
a known `/api` path with the wrong method still answers 405 from the router, and an unknown
`/api/**` path still answers the backend's JSON 404 (never `index.html`).

Everything that reaches the filesystem is hostile input. A request path is served only if it
passes every check below; anything else is a plain 404:
- GET/HEAD only (other methods: 405);
- no NUL, backslash or ":"; no empty, `.` or `..` segment; no segment starting with "." (dotfiles);
- the file is a regular file, reached without crossing a symlink, and its resolved path stays
  inside the resolved root (`is_relative_to`).
A path without an extension that matches no file gets `index.html` (client-side routing); a path
with an extension that matches no file is a 404. Security headers come from
`SecurityHeadersMiddleware`, which wraps these responses too.
"""

from pathlib import Path

from fastapi import FastAPI
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.http_utils import is_api_path

INDEX = "index.html"
ALLOWED_METHODS = ("GET", "HEAD")
_FORBIDDEN_CHARS = frozenset("\x00\\:")

# Explicit table: `mimetypes` reads the Windows registry and may differ across hosts.
_MEDIA_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".txt": "text/plain",
    ".map": "application/json",
}
_DEFAULT_MEDIA_TYPE = "application/octet-stream"

CACHE_REVALIDATE = "no-cache"
CACHE_IMMUTABLE = "public, max-age=31536000, immutable"
_NOT_FOUND_HEADERS = {"Cache-Control": "no-store"}


def _clean_segments(path: str) -> list[str] | None:
    """Segments of a safe relative path, [] for the root, or None when the path is unacceptable."""
    if not path.startswith("/") or any(ch in _FORBIDDEN_CHARS for ch in path):
        return None
    segments = path[1:].split("/")
    if segments == [""]:
        return []
    if segments[-1] == "":  # trailing slash: a directory, never a file
        segments.pop()
    if any(not s or s.startswith(".") for s in segments):
        return None
    return segments


def _cache_control(segments: list[str]) -> str:
    if len(segments) > 1 and segments[0] == "assets":
        return CACHE_IMMUTABLE  # Vite puts a content hash in these names
    # index.html, sw.js, workbox-*.js, manifest.webmanifest and everything else: revalidate with
    # the ETag instead of guessing a lifetime (a stale service worker would pin an old app).
    return CACHE_REVALIDATE


class SpaApp:
    """ASGI app that serves `root` (a built SPA) for requests outside `/api`."""

    def __init__(self, root: Path, api_not_found: ASGIApp) -> None:
        self._root = root.resolve(strict=True)
        self._api_not_found = api_not_found

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_api_path(scope["path"]):
            await self._api_not_found(scope, receive, send)
            return
        if scope["method"] not in ALLOWED_METHODS:
            await PlainTextResponse(
                "Method Not Allowed",
                status_code=405,
                headers={"Allow": ", ".join(ALLOWED_METHODS), **_NOT_FOUND_HEADERS},
            )(scope, receive, send)
            return
        await self._serve(scope)(scope, receive, send)

    def _not_found(self) -> Response:
        return PlainTextResponse("Not Found", status_code=404, headers=_NOT_FOUND_HEADERS)

    def _serve(self, scope: Scope) -> Response:
        segments = _clean_segments(scope["path"])
        if segments is None:
            return self._not_found()
        file = self._existing_file(segments) if segments else None
        if file is None:
            if segments and "." in segments[-1]:
                return self._not_found()  # looks like a file (has an extension) but is missing
            index = self._existing_file([INDEX])
            if index is None:
                return self._not_found()
            return self._file(index, [INDEX])
        return self._file(file, segments)

    def _existing_file(self, segments: list[str]) -> Path | None:
        """The regular file at root/segments, or None. Never follows a symlink out of the root."""
        current = self._root
        try:
            for segment in segments:
                current = current / segment
                if current.is_symlink():
                    return None
            resolved = current.resolve(strict=True)
            if not resolved.is_relative_to(self._root) or not resolved.is_file():
                return None
        except (OSError, ValueError):
            return None
        return resolved

    def _file(self, file: Path, segments: list[str]) -> Response:
        media_type = _MEDIA_TYPES.get(file.suffix.lower(), _DEFAULT_MEDIA_TYPE)
        # The fallback serves index.html under a different URL: it must never be cached long.
        cache = _cache_control(segments if file.name != INDEX else [INDEX])
        return FileResponse(file, media_type=media_type, headers={"Cache-Control": cache})


def install_spa(app: FastAPI, dist_dir: Path) -> None:
    """Serve `dist_dir` for every path no API route matches (call once, after the routers)."""
    app.router.default = SpaApp(dist_dir, app.router.default)
