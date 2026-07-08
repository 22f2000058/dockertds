from fastapi import FastAPI, HTTPException, Header, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from redis.exceptions import ConnectionError
import os
from typing import Dict, Any, List
from collections import defaultdict
import time
import structlog
from datetime import datetime
from prometheus_client import Counter, generate_latest

app = FastAPI(title="TDS Full Instrumented API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus
http_requests_total = Counter('http_requests_total', 'Total HTTP requests', ['method', 'path'])

# Logger
logger = structlog.get_logger()
recent_logs: List[Dict] = []
MAX_LOGS = 100
START_TIME = time.time()

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=5)

ASSIGNED_API_KEY = "ak_grdgugqgtj0qzqpm7l8eg2tt"

# Logging + Metrics Middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    log_entry = {
        "level": "info",
        "ts": datetime.utcnow().isoformat() + "Z",
        "path": str(request.url.path),
        "method": request.method,
        "status_code": response.status_code,
        "duration_ms": round(duration * 1000, 2),
        "request_id": str(int(start_time * 1000))
    }
    recent_logs.append(log_entry)
    if len(recent_logs) > MAX_LOGS:
        recent_logs.pop(0)
    
    logger.info("request", **log_entry)
    http_requests_total.labels(method=request.method, path=request.url.path).inc()
    return response

# ====================== NEW INSTRUMENTED ENDPOINTS ======================
@app.get("/work")
async def do_work(n: int = Query(1, gt=0, le=100)):
    return {"email": "22f2000058@ds.study.iitm.ac.in", "done": n}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics - explicit content type"""
    from fastapi.responses import Response
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )

@app.get("/healthz")
async def healthz():
    uptime = time.time() - START_TIME
    return {"status": "ok", "uptime_s": round(uptime, 2)}

@app.get("/logs/tail")
async def logs_tail(limit: int = Query(10, gt=0, le=100)):
    return recent_logs[-limit:]

# ====================== PREVIOUS ENDPOINTS ======================
@app.post("/analytics")
async def analytics(
    request: Request,
    events_data: Dict[str, List[Dict]],
    x_api_key: str = Header(None, alias="X-API-Key")
) -> Dict[str, Any]:
    if not x_api_key or x_api_key != ASSIGNED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    events = events_data.get("events", [])
    if not events:
        return {"email": "22f2000058@ds.study.iitm.ac.in", "total_events": 0, "unique_users": 0, "revenue": 0.0, "top_user": ""}
    
    total_events = len(events)
    users = set()
    revenue = 0.0
    user_revenue = defaultdict(float)
    
    for event in events:
        user = event.get("user")
        amount = float(event.get("amount", 0))
        if user:
            users.add(user)
        if amount > 0:
            revenue += amount
            if user:
                user_revenue[user] += amount
    
    top_user = max(user_revenue, key=user_revenue.get) if user_revenue else ""
    
    return {
        "email": "22f2000058@ds.study.iitm.ac.in",
        "total_events": total_events,
        "unique_users": len(users),
        "revenue": round(revenue, 2),
        "top_user": top_user
    }

@app.post("/hit/{key}")
async def hit(key: str) -> Dict[str, Any]:
    try:
        count = redis_client.incr(key)
        return {"key": key, "count": count}
    except Exception:
        raise HTTPException(status_code=503, detail="Redis error")

@app.get("/count/{key}")
async def get_count(key: str) -> Dict[str, Any]:
    try:
        value = redis_client.get(key)
        count = int(value) if value is not None else 0
        return {"key": key, "count": count}
    except Exception:
        raise HTTPException(status_code=503, detail="Redis error")

@app.get("/")
async def root():
    return {"message": "TDS Instrumented Service Running"}
