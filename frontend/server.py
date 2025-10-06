from __future__ import annotations

import os
from typing import Dict

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles


BACKEND_BASE = os.environ.get("BACKEND_BASE_URL", "http://127.0.0.1:3601").rstrip("/")

app = FastAPI(title="RSS-AI Frontend Server")


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(path: str, request: Request):
    target = f"{BACKEND_BASE}/api/{path}"
    body = await request.body()
    headers: Dict[str, str] = dict(request.headers)
    headers.pop("host", None)
    # Avoid hop-by-hop headers
    for k in ["content-length", "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"]:
        headers.pop(k, None)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            request.method,
            target,
            params=request.query_params,
            headers=headers,
            content=body,
        )
    # Filter response headers
    resp_headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in {"content-encoding", "transfer-encoding", "connection"}
    }
    return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)


# 静态资源（最后挂载，避免覆盖 /api 前缀）
static_dir = os.path.dirname(__file__)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "3602"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)

