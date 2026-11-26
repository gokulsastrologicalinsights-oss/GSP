"""Dedicated media-only FastAPI application for temporary Instagram Reels delivery."""
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

import temp_media_service

media_app = FastAPI(
    title="GSP Media Delivery",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_CHUNK_SIZE = 1024 * 1024  # 1 MB streaming chunks


def _iter_file_range(path: str, start: int, length: int):
    with open(path, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@media_app.api_route("/api/media/temp/{token}", methods=["GET", "HEAD"])
def serve_temp_media(token: str, request: Request):
    """Serve an authorized temporary video file with Range and HEAD support."""
    media_path = temp_media_service.validate_temp_media_token(token)
    if not media_path:
        raise HTTPException(status_code=403, detail="Invalid, expired, or revoked media token")

    file_size = os.path.getsize(media_path)
    base_headers = {
        "Accept-Ranges": "bytes",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "Content-Disposition": f'inline; filename="{os.path.basename(media_path)}"',
    }

    if request.method == "HEAD":
        base_headers["Content-Length"] = str(file_size)
        return Response(status_code=200, media_type="video/mp4", headers=base_headers)

    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        spec = range_header.replace("bytes=", "", 1).split(",")[0].strip()
        start_str, _, end_str = spec.partition("-")
        try:
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            raise HTTPException(status_code=416, detail="Invalid Range header")
        if start < 0 or end >= file_size or start > end:
            raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")
        length = end - start + 1
        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
        }
        return StreamingResponse(
            _iter_file_range(media_path, start, length),
            status_code=206,
            media_type="video/mp4",
            headers=headers,
        )

    base_headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        _iter_file_range(media_path, 0, file_size),
        status_code=200,
        media_type="video/mp4",
        headers=base_headers,
    )
