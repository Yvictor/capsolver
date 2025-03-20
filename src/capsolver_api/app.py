import os

import capsolver
import requests
import uvicorn
from fastapi import FastAPI

app = FastAPI()
capsolver.api_key = os.getenv("CAPSOLVER_API_KEY")

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


def main():
    uvicorn.run(
        "capsolver_api.app:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", 9987)),
        reload=bool(os.getenv("API_RELOAD", True)),
        # workers=os.getenv("API_WORKERS", 4),
    )
