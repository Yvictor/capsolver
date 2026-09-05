import asyncio
import logging
import json
from dataclasses import dataclass

from camoufox.async_api import AsyncCamoufox
from playwright.async_api import Browser, Page

logger = logging.getLogger(__name__)
POOL_SIZE = 4
QUEUE_TIMEOUT = 30
SOLVE_TIMEOUT = 60
BROWSER_TIMEOUT = 45
BROWSER_QUEUE = asyncio.Queue(maxsize=POOL_SIZE)
_sessions = set()
_initializing = False
_active = 0


@dataclass(eq=False)
class BrowserSession:
    manager: object
    browser: Browser
    page: Page


async def _new_session():
    manager = AsyncCamoufox(headless=True, main_world_eval=True)
    try:
        async with asyncio.timeout(BROWSER_TIMEOUT):
            browser = await manager.__aenter__()
            page = await browser.new_page()
            await page.route("**/*", _route_page)
        session = BrowserSession(manager, browser, page)
        _sessions.add(session)
        return session
    except BaseException:
        try:
            await asyncio.wait_for(manager.__aexit__(None, None, None), 10)
        except Exception:
            logger.exception("Failed to clean up browser startup")
        raise


async def _close_session(session):
    _sessions.discard(session)
    try:
        await asyncio.wait_for(session.manager.__aexit__(None, None, None), 10)
    except Exception:
        logger.exception("Failed to close browser")


async def _route_page(route):
    request = route.request
    # The site's navigation/table scripts can stall HTML parsing; the solver
    # only needs the actual widget container and the official Turnstile assets.
    if request.frame == request.frame.page.main_frame:
        if request.resource_type in {"font", "image", "stylesheet"} or (
            request.resource_type == "script"
            and "challenges.cloudflare.com/" not in request.url
        ):
            await route.abort()
            return
    await route.continue_()


async def solve_turnstile(url: str, website_key: str, page: Page,
                         reload_page: bool = False):
    if reload_page:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if response is not None and response.status >= 400:
            raise RuntimeError(f"Target page returned HTTP {response.status}")
        try:
            await page.locator("#myWidget").wait_for(state="attached", timeout=10000)
        except Exception:
            logger.error("Widget missing: url=%s title=%s body=%s", page.url,
                         await page.title(), (await page.locator("body").inner_text())[:300])
            raise
    # Keep a real script element; evaluating api.js breaks script-tag detection.
    if not await page.evaluate("mw:() => Boolean(window.turnstile)"):
        if not await page.locator('script[src*="challenges.cloudflare.com/turnstile/"]').count():
            await page.add_script_tag(
                url="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit"
            )
    async with asyncio.timeout(20):
        while not await page.evaluate(
            "mw:() => Boolean(window.turnstile && typeof window.turnstile.render === 'function')"
        ):
            await asyncio.sleep(0.1)
    # Camoufox's main-world evaluator also does not forward Playwright's arg.
    await page.evaluate("mw:() => { const sitekey = " + json.dumps(website_key) + ";" + """
        window.brokerSolverResult = null;
            try {
                const container = document.querySelector('#myWidget');
                if (!container) throw new Error('TPEX widget container not found');
                if (window.brokerSolverWidget !== undefined) {
                    turnstile.remove(window.brokerSolverWidget);
                } else {
                    turnstile.remove(container);
                }
                container.replaceChildren();
                window.brokerSolverWidget = turnstile.render(container, {
                    sitekey,
                    callback: token => { window.brokerSolverResult = {token}; },
                    'error-callback': code => { window.brokerSolverResult = {error: 'Turnstile error: ' + code}; },
                    'expired-callback': () => { window.brokerSolverResult = {error: 'Turnstile expired'}; },
                    'timeout-callback': () => { window.brokerSolverResult = {error: 'Turnstile timed out'}; },
                    theme: 'light'
                });
            } catch (error) { window.brokerSolverResult = {error: String(error)}; }
        return true;
    }""")
    # Camoufox main-world evaluation does not unwrap a returned Promise.
    async with asyncio.timeout(SOLVE_TIMEOUT):
        while True:
            result = await page.evaluate("mw:() => window.brokerSolverResult")
            if result:
                if result.get("error"):
                    raise RuntimeError(result["error"])
                return result.get("token")
            await asyncio.sleep(0.2)


async def fetch_turnstile_token(url: str, website_key: str) -> str:
    async with asyncio.timeout(210):
        for attempt in range(3):
            try:
                return await _fetch_once(url, website_key)
            except Exception:
                logger.exception("Solver attempt %s failed", attempt + 1)
                if attempt == 2:
                    raise
                await asyncio.sleep(attempt + 1)


async def _fetch_once(url: str, website_key: str) -> str:
    global _active
    session = await asyncio.wait_for(BROWSER_QUEUE.get(), QUEUE_TIMEOUT)
    _active += 1
    healthy = False
    try:
        if session is None:
            session = await _new_session()
        token = await asyncio.wait_for(
            solve_turnstile(url, website_key, session.page,
                           reload_page=session.page.url != url),
            SOLVE_TIMEOUT,
        )
        if not token:
            raise RuntimeError("Solver returned an empty token")
        healthy = True
        return token
    finally:
        try:
            if session is not None and not healthy:
                await _close_session(session)
                session = None
        finally:
            # Preserve the slot on every failure, including browser startup.
            BROWSER_QUEUE.put_nowait(session if healthy else None)
            BROWSER_QUEUE.task_done()
            _active -= 1


async def init_browser_pool(num_browsers: int = POOL_SIZE):
    global _initializing
    _initializing = True
    try:
        for _ in range(num_browsers):
            session = None
            try:
                session = await _new_session()
            except Exception:
                logger.exception("Browser pool initialization failed")
            BROWSER_QUEUE.put_nowait(session)
    finally:
        _initializing = False


def browser_pool_status():
    live = sum(s.browser.is_connected() and not s.page.is_closed() for s in _sessions)
    return {"ready": not _initializing and live > 0,
            "initializing": _initializing, "browsers": live,
            "available_slots": BROWSER_QUEUE.qsize(), "active": _active}


async def close_browser_pool():
    for session in list(_sessions):
        await _close_session(session)
    while not BROWSER_QUEUE.empty():
        BROWSER_QUEUE.get_nowait()
        BROWSER_QUEUE.task_done()
