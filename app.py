from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import time
import uuid
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST
import logging
from pythonjsonlogger import jsonlogger
import asyncio

app = FastAPI()

# Prometheus counter
http_requests_total = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])

# Startup time
startup_time = time.time()

# In-memory logs for /logs/tail
logs = []

class InMemoryLogHandler(logging.Handler):
    def emit(self, record):
        log_entry = {
            "level": record.levelname,
            "ts": record.created,
            "path": getattr(record, 'path', 'unknown'),
            "request_id": getattr(record, 'request_id', 'unknown'),
            "message": record.getMessage()
        }
        logs.append(log_entry)
        if len(logs) > 1000:  # keep last 1000
            logs.pop(0)

# Structured JSON logging
logger = logging.getLogger("fastapi")
logger.setLevel(logging.INFO)
logHandler = InMemoryLogHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)
logger.propagate = False

# Also add to root for uvicorn if needed
root_logger = logging.getLogger()
root_logger.addHandler(logHandler)

# Middleware for logging and metrics
@app.middleware("http")
async def log_and_metrics(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Log request
    logger.info("Request started", extra={
        "path": request.url.path,
        "request_id": request_id,
        "method": request.method
    })
    
    # Increment counter
    endpoint = request.url.path
    http_requests_total.labels(request.method, endpoint).inc()
    
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info("Request completed", extra={
        "path": request.url.path,
        "request_id": request_id,
        "status_code": response.status_code,
        "duration": process_time
    })
    
    return response

@app.get("/work")
async def work(n: int = 1):
    # Simulate work
    await asyncio.sleep(0.01 * n)  # small delay
    return {"email": "your.email@example.com", "done": n}

@app.get("/metrics")
async def metrics():
    return JSONResponse(
        content=generate_latest().decode('utf-8'),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/healthz")
async def healthz():
    uptime = time.time() - startup_time
    return {"status": "ok", "uptime_s": uptime}

@app.get("/logs/tail")
async def logs_tail(limit: int = 10):
    # Return last N logs (most recent first)
    recent_logs = sorted(logs[-limit:], key=lambda x: x.get('ts', 0), reverse=True)
    return recent_logs

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)