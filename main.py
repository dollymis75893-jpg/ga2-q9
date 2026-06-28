from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 41
RATE_LIMIT = 18
RATE_WINDOW = 10

orders_db = [{"id": i, "item": f"Product_{i}"} for i in range(1, TOTAL_ORDERS + 1)]
idempotency_cache = {}
rate_limit_store = {}
next_new_order_id = TOTAL_ORDERS + 1

@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    # FIX: Browser ki CORS preflight (OPTIONS) requests ko allow karo
    if request.method == "OPTIONS":
        return await call_next(request)
        
    if request.url.path.startswith("/orders"):
        client_id = request.headers.get("x-client-id", "default_client")
        now = time.time()
        
        timestamps = rate_limit_store.get(client_id, [])
        timestamps = [ts for ts in timestamps if now - ts < RATE_WINDOW]
        
        if len(timestamps) >= RATE_LIMIT:
            retry_after = int((timestamps[0] + RATE_WINDOW) - now)
            if retry_after < 1:
                retry_after = 1
                
            # FIX: Rate limit error ke sath CORS header bhejna zaroori hai
            return Response(
                content='{"error": "Too Many Requests"}',
                status_code=429,
                headers={
                    "Retry-After": str(retry_after),
                    "Access-Control-Allow-Origin": "*"
                }
            )
        
        timestamps.append(now)
        rate_limit_store[client_id] = timestamps

    return await call_next(request)

@app.post("/orders", status_code=201)
async def create_order(request: Request, response: Response):
    global next_new_order_id
    idem_key = request.headers.get("idempotency-key")
    
    if idem_key and idem_key in idempotency_cache:
        return idempotency_cache[idem_key]
    
    new_order = {"id": next_new_order_id, "status": "Order Created Successfully"}
    next_new_order_id += 1
    
    if idem_key:
        idempotency_cache[idem_key] = new_order
        
    return new_order

@app.get("/orders")
async def get_orders(limit: int = 10, cursor: str = None):
    start_index = 0
    if cursor and cursor.isdigit():
        start_index = int(cursor)
        
    end_index = start_index + limit
    items = orders_db[start_index:end_index]
    next_cursor = str(end_index) if end_index < len(orders_db) else None
    
    return {
        "items": items,
        "next_cursor": next_cursor
    }
