"""Interactive HTTP server for the Moss RAG chatbot, evaluation dashboard, and selective test runner."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from moss import QueryOptions

from src.build_dashboard import DASHBOARD_DIR, write_dashboard
from src.common import load_config, make_inference_client, make_moss_client
from src.test_runner import run_selected_tests


class MossBackendRuntime:
    """Owns a dedicated asyncio loop thread so MossClient and MossInference stay bound cleanly."""

    def __init__(self) -> None:
        self.cfg = load_config()
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._loaded_indexes: set[str] = set()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10)
        self.moss_client = self.run(self._init_moss_client())

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self.loop)
        self._ready.set()
        self.loop.run_forever()

    def run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=300)

    async def _init_moss_client(self) -> Any:
        return make_moss_client(self.cfg)

    async def chat(
        self,
        message: str,
        history: list[dict[str, str]],
        index_name: str,
        use_rag: bool,
        use_cache: bool,
    ) -> dict[str, Any]:
        sources: list[dict[str, Any]] = []
        retrieval_ms = 0.0

        if use_rag and index_name:
            if index_name not in self._loaded_indexes:
                await self.moss_client.load_index(index_name)
                self._loaded_indexes.add(index_name)
            r0 = time.perf_counter()
            qres = await self.moss_client.query(index_name, message, QueryOptions(top_k=4))
            retrieval_ms = round((time.perf_counter() - r0) * 1000.0, 2)
            sources = [
                {"id": d.id, "score": float(d.score), "text": d.text}
                for d in qres.docs
            ]

        input_items: list[dict[str, str]] = [
            {"role": m["role"], "content": m["content"]}
            for m in history[-8:]
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]
        input_items.append({"role": "user", "content": message})

        instructions = (
            "You are a helpful Kestrel Systems assistant. Answer clearly in plain language using "
            "the retrieved Moss index facts. If the answer is not in the retrieved documents, say "
            "clearly that you do not have that information."
            if use_rag
            else "You are a helpful assistant. Answer concisely in plain language."
        )

        t0 = time.perf_counter()
        async with make_inference_client(self.cfg, timeout=60.0) as inf:
            resp = await inf.responses.create(
                model="moss",
                instructions=instructions,
                input=input_items,
                indexes=[index_name] if use_rag else None,
                retrieve=use_rag,
                cache=use_cache,
            )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        return {
            "reply": resp.output_text,
            "model": resp.model,
            "latency_ms": latency_ms,
            "retrieval_ms": retrieval_ms,
            "sources": sources,
            "usage": {
                "input_tokens": resp.usage.input_tokens if resp.usage else None,
                "output_tokens": resp.usage.output_tokens if resp.usage else None,
                "total_tokens": resp.usage.total_tokens if resp.usage else None,
                "cached_tokens": (
                    resp.usage.input_tokens_details.cached_tokens
                    if resp.usage and resp.usage.input_tokens_details
                    else 0
                ),
            },
        }


RUNTIME: MossBackendRuntime | None = None
RERUN_LOCK = threading.Lock()


class DashboardHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html_path = DASHBOARD_DIR / "index.html"
            if not html_path.exists():
                write_dashboard()
            data = html_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/api/dashboard":
            self._send_json(HTTPStatus.OK, write_dashboard())
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self) -> None:
        assert RUNTIME is not None
        if self.path == "/api/chat":
            try:
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Message cannot be empty"})
                    return
                res = RUNTIME.run(
                    RUNTIME.chat(
                        message=message,
                        history=body.get("history") or [],
                        index_name=body.get("index_name") or "Company factuals",
                        use_rag=bool(body.get("use_rag", True)),
                        use_cache=bool(body.get("use_cache", False)),
                    )
                )
                self._send_json(HTTPStatus.OK, res)
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        if self.path == "/api/rerun":
            try:
                body = self._read_json()
                test_ids = body.get("test_ids") or []
                if not isinstance(test_ids, list) or not test_ids:
                    self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Provide non-empty test_ids list"})
                    return
                with RERUN_LOCK:
                    outcomes = RUNTIME.run(run_selected_tests([str(x) for x in test_ids]))
                    dashboard = write_dashboard()
                case_map = {c["id"]: c for c in dashboard["cases"]}
                enriched = []
                for o in outcomes:
                    c = case_map.get(o["id"])
                    raw_out = None
                    if c:
                        d = c.get("details") or {}
                        if "grounded_summary" in d:
                            raw_out = d["grounded_summary"].get("output_text")
                        elif isinstance(d.get("result"), dict):
                            raw_out = d["result"].get("output") or d["result"].get("output_text")
                        elif d.get("output_text"):
                            raw_out = d.get("output_text")
                        elif d.get("error"):
                            raw_out = d.get("error")
                        elif d.get("message"):
                            raw_out = d.get("message")
                    enriched.append(
                        {
                            **o,
                            "title": c["title"] if c else o["id"],
                            "expected": c["expected"] if c else None,
                            "result": c["result"] if c else None,
                            "verdict": c["verdict"] if c else ("Did Not Meet" if not o["ok"] else "Partial"),
                            "met_expectation": (c["verdict"] == "Met") if c else False,
                            "cost_usd": c["cost_usd"] if c else 0.0,
                            "raw_output": raw_out,
                        }
                    )
                self._send_json(HTTPStatus.OK, {"outcomes": enriched, "dashboard": dashboard})
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})


def main() -> None:
    global RUNTIME
    write_dashboard()
    RUNTIME = MossBackendRuntime()
    server = ThreadingHTTPServer(("127.0.0.1", 8765), DashboardHandler)
    print("Moss Interactive Dashboard & RAG Chatbot running at http://127.0.0.1:8765/")
    server.serve_forever()


if __name__ == "__main__":
    main()
