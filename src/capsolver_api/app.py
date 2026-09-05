import asyncio
import os
import logging

import capsolver
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from .utils import get_turnstile_token
from .solver import fetch_turnstile_token, init_browser_pool, close_browser_pool, browser_pool_status

app = FastAPI()
logger = logging.getLogger(__name__)
_pool_task = None


async def _startup_browser_pool():
    """Start browser pool in background so it doesn't block the server startup."""
    global _pool_task
    _pool_task = asyncio.create_task(init_browser_pool())


async def _shutdown_browser_pool():
    if _pool_task is not None:
        _pool_task.cancel()
        await asyncio.gather(_pool_task, return_exceptions=True)
    await close_browser_pool()

app.add_event_handler("startup", _startup_browser_pool)
app.add_event_handler("shutdown", _shutdown_browser_pool)

capsolver.api_key = os.getenv("CAPSOLVER_API_KEY")
TOKENS_QUEUE = []


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/health")
async def health_check():
    """Health check endpoint. Returns 200 if the service is alive and responsive."""
    pool = browser_pool_status()
    if not pool["ready"]:
        raise HTTPException(status_code=503, detail=pool)
    return {"status": "ok", "pool": pool}


@app.get("/ip")
async def ip_endpoint():
    response = requests.get("https://api.ipify.org?format=json")
    return response.json()["ip"]


@app.get("/recaptchav2/capsolver")
def recaptchav2_capsolver(url: str, website_key: str):
    solution = capsolver.solve(
        {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": url,
            "websiteKey": website_key,
        }
    )
    return {"token": solution["gRecaptchaResponse"]}


@app.get("/turnstile/capsolver")
def turnstile_capsolver(url: str, website_key: str):
    solution = capsolver.solve(
        {
            "type": "AntiTurnstileTaskProxyLess",
            "websiteURL": url,
            "websiteKey": website_key,
        }
    )
    return {"token": solution["token"]}

@app.get("/turnstile/solver")
async def turnstile_solver(url: str, website_key: str, action: str, cdata: str="", headless: bool = True, browser_type: str = "camoufox"):
    res = await get_turnstile_token(url, website_key, action, cdata, headless=headless, browser_type=browser_type)
    if res.status == "success":
        return {"token": res.turnstile_value}
    else:
        raise HTTPException(status_code=500, detail=res.reason)

@app.get("/turnstile/realpage/solver")
async def turnstile_realpage_solver(url: str, website_key: str):
    try:
        token = await fetch_turnstile_token(url, website_key)
        return {"token": token}
    except TimeoutError:
        logger.exception("Realpage solver timed out")
        raise HTTPException(status_code=504, detail="Browser wait or solve timed out")
    except Exception as e:
        logger.exception("Realpage solver failed")
        raise HTTPException(status_code=500, detail=f"Error: {e}")

@app.get("/turnstile/collect")
def turnstile_collect(token: str):
    TOKENS_QUEUE.append(token)
    return {"message": "Token collected"}


@app.get("/turnstile/get")
def turnstile_get():
    if len(TOKENS_QUEUE) == 0:
        return {"error": "No tokens in queue"}
    return {"token": TOKENS_QUEUE.pop(0)}


def main():
    uvicorn.run(
        "capsolver_api.app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 9987)),
        reload=os.getenv("API_RELOAD", "false").lower() in {"1", "true", "yes"},
        # workers=os.getenv("API_WORKERS", 4),
    )
