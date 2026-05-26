import json
import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

logger = logging.getLogger("jarvis.tma_server")

STATIC_DIR = Path(__file__).parent.parent / "static"
LEDGER_PATH = Path(__file__).parent.parent / "financial_ledger.json"


class CommandRequest(BaseModel):
    command: str
    args: dict = {}


class TaskRequest(BaseModel):
    prompt: str
    metadata: dict = {}


def create_app(brain, pool=None, notifier=None) -> FastAPI:
    app = FastAPI(title="Jarvis-Omega TMA API", version="1.0.0")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def root():
        dashboard = STATIC_DIR / "dashboard.html"
        if dashboard.exists():
            return FileResponse(str(dashboard))
        return JSONResponse({"status": "Jarvis-Omega TMA running"})

    @app.get("/api/metrics")
    async def get_metrics():
        try:
            metrics = await brain.get_metrics()
            if pool is not None:
                metrics["queue_size"] = pool.queue_size
            return JSONResponse(metrics)
        except Exception as e:
            logger.error(f"[TMA] Error fetching metrics: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch metrics")

    @app.get("/api/ledger")
    async def get_ledger(limit: int = 10):
        try:
            if not LEDGER_PATH.exists():
                return JSONResponse({"total_profit_usd": 0.0, "transactions": []})
            data = json.loads(LEDGER_PATH.read_text())
            txns = data.get("transactions", [])
            return JSONResponse(
                {
                    "total_profit_usd": data.get("total_profit_usd", 0.0),
                    "transactions": txns[-(min(limit, 50)):],
                }
            )
        except Exception as e:
            logger.error(f"[TMA] Error reading ledger: {e}")
            raise HTTPException(status_code=500, detail="Failed to read ledger")

    @app.post("/api/task")
    async def add_task(req: TaskRequest):
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="prompt must not be empty")
        if pool is None:
            raise HTTPException(status_code=503, detail="WorkerPool is not available")
        try:
            await pool.add_task(req.prompt.strip(), req.metadata)
            logger.info(f"[TMA] Task enqueued via API: {req.prompt[:60]!r}")
            return {"status": "queued", "queue_size": pool.queue_size}
        except Exception as e:
            logger.error(f"[TMA] Failed to enqueue task: {e}")
            raise HTTPException(status_code=500, detail="Failed to enqueue task")

    @app.post("/api/command")
    async def run_command(req: CommandRequest):
        cmd = req.command.lower().strip()
        logger.info(f"[TMA] Received command: {cmd}")

        if cmd == "pause":
            if pool:
                await pool.pause()
            else:
                await brain.pause_workers()
            return {"status": "ok", "message": "Workers paused"}
        elif cmd == "resume":
            if pool:
                await pool.resume()
            else:
                await brain.resume_workers()
            return {"status": "ok", "message": "Workers resumed"}
        elif cmd == "status":
            metrics = await brain.get_metrics()
            if pool is not None:
                metrics["queue_size"] = pool.queue_size
            return {"status": "ok", "metrics": metrics}
        else:
            raise HTTPException(status_code=400, detail=f"Unknown command: {cmd}")

    @app.get("/api/alerts")
    async def get_alerts():
        if notifier is None:
            return JSONResponse({"alerts": []})
        try:
            return JSONResponse({"alerts": notifier.get_history_dicts()})
        except Exception as e:
            logger.error(f"[TMA] Error fetching alerts: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch alerts")

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


async def start_server(brain, pool=None, notifier=None):
    host = os.getenv("TMA_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("TMA_SERVER_PORT", "8000"))

    app = create_app(brain, pool=pool, notifier=notifier)
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info(f"[TMA] Starting FastAPI server on {host}:{port}")
    await server.serve()
