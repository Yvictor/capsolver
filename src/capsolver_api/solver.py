import asyncio

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, Page
import aiohttp

BROWSER_QUEUE = asyncio.Queue(maxsize=4)

async def get_turnstile_js():
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://challenges.cloudflare.com/turnstile/v0/api.js?onload=_turnstileCb"
        ) as response:
            turnstile_js = await response.text()
    return turnstile_js


async def solve_turnstile(
    url: str,
    website_key: str,
    page: Page,
    turnstile_js: str = "",
    reload_page: bool = False,
):
    if reload_page:
        await page.goto(url)
        if not turnstile_js:
            turnstile_js = await get_turnstile_js()
        await page.evaluate(turnstile_js)
    js_token = f"""function getTurnstileToken() {{
    return new Promise((resolve, reject) => {{
        try {{
            turnstile.render("#myWidget", {{
                sitekey: "{website_key}",
                
                // 成功時呼叫的回調
                callback: function(token) {{
                    console.log(`Challenge Success, resolving promise with token: {{token}}`);
                    resolve(token); // 使用 token 來 "完成" 這個 Promise
                }},

                // 失敗時呼叫的回調
                'error-callback': function() {{
                    console.error('Turnstile challenge failed.');
                    reject('Challenge failed'); // "拒絕" 這個 Promise
                }},

                // 過期時呼叫的回調
                'expired-callback': function() {{
                    console.warn('Turnstile challenge expired.');
                    reject('Challenge expired'); // "拒絕" 這個 Promise
                }},

                theme: "light"
            }});
        }} catch (error) {{
            reject(error); // 如果 turnstile.render 本身出錯，也拒絕 Promise
        }}  
    }});
}}
"""
    js_clean = 'document.querySelector("#myWidget").innerHTML = ""'
    await page.evaluate(js_clean)
    token = await page.evaluate(js_token)
    return token


async def fetch_turnstile_token(url: str, website_key: str) -> str:
    browser, page = await BROWSER_QUEUE.get()
    reload_page = page.url != url
    token = await solve_turnstile(url, website_key, page, reload_page=reload_page)
    await BROWSER_QUEUE.put((browser, page))
    return token


async def init_browser(headless: bool = True):
    # async with AsyncCamoufox(headless=headless) as browser:
    browser: Browser = await AsyncCamoufox(headless=headless).start() # type: ignore

    page = await browser.new_page()
    await BROWSER_QUEUE.put((browser, page))

async def init_browser_pool(num_browsers: int = 4):
    for _ in range(num_browsers):
        await init_browser()

async def close_browser_pool():
    while not BROWSER_QUEUE.empty():
        browser, page = await BROWSER_QUEUE.get()
        await page.close()
        await browser.close()
