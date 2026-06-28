from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import time

app = FastAPI()

# --- CORS SETUP ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ASSIGNED VALUES ---
TOTAL_ORDERS = 41
RATE_LIMIT = 18
RATE_WINDOW = 10  # seconds

# --- IN-MEMORY DATABASE ---
# Pagination ke liye 1 se 41 tak orders ki list
orders_db = [{"id": i, "item": f"Product_{i}"} for i in range(1, TOTAL_ORDERS + 1)]

idempotency_cache = {}
rate_limit_store = {}
next_new_order_id = TOTAL_ORDERS + 1

# --- 1. RATE LIMITING MIDDLEWARE ---
@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    # Sirf API endpoints par rate limit lagayenge
    if request.url.path.startswith("/orders"):
        client_id = request.headers.get("x-client-id", "default_client")
        now = time.time()
        
        # Purane (10s se pehle ke) requests hatao
        timestamps = rate_limit_store.get(client_id, [])
        timestamps = [ts for ts in timestamps if now - ts < RATE_WINDOW]
        
        if len(timestamps) >= RATE_LIMIT:
            # R limit cross ho gayi, 429 error do aur Retry-After header lagao
            retry_after = int((timestamps[0] + RATE_WINDOW) - now)
            if retry_after < 1:
                retry_after = 1
                
            return Response(
                content='{"error": "Too Many Requests"}',
                status_code=429,
                headers={"Retry-After": str(retry_after)}
            )
        
        # Request valid hai, iska time save karo
        timestamps.append(now)
        rate_limit_store[client_id] = timestamps

    # Aage badho
    response = await call_next(request)
    return response


# --- 2. IDEMPOTENT ORDER CREATION ---
@app.post("/orders", status_code=201)
async def create_order(request: Request, response: Response):
    global next_new_order_id
    idem_key = request.headers.get("idempotency-key")
    
    # Agar key pehle se cache mein hai, toh wahi purana response do
    if idem_key and idem_key in idempotency_cache:
        return idempotency_cache[idem_key]
    
    # Naya order banao
    new_order = {"id": next_new_order_id, "status": "Order Created Successfully"}
    next_new_order_id += 1
    
    # Naye order ko cache mein save karo agar key di gayi hai
    if idem_key:
        idempotency_cache[idem_key] = new_order
        
    return new_order


# --- 3. CURSOR PAGINATION ---
@app.get("/orders")
async def get_orders(limit: int = 10, cursor: str = None):
    # Cursor ko index ki tarah use karenge
    start_index = 0
    if cursor and cursor.isdigit():
        start_index = int(cursor)
        
    end_index = start_index + limit
    
    # Slice the database list
    items = orders_db[start_index:end_index]
    
    # Agar abhi aur items bache hain list mein, toh naya cursor do
    next_cursor = str(end_index) if end_index < len(orders_db) else None
    
    return {
        "items": items,
        "next_cursor": next_cursor
    }
