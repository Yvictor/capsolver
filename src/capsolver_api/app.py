import os

import capsolver
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from .utils import get_turnstile_token
from .solver import fetch_turnstile_token, init_browser_pool, close_browser_pool

app = FastAPI()
app.add_event_handler("startup", init_browser_pool)
app.add_event_handler("shutdown", close_browser_pool)

capsolver.api_key = os.getenv("CAPSOLVER_API_KEY")
TOKENS_QUEUE = []

@app.get("/")
def read_root():
    return {"message": "Hello World"}


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
    except Exception as e:
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
        reload=bool(os.getenv("API_RELOAD", True)),
        # workers=os.getenv("API_WORKERS", 4),
    )
