import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from capsolver_api import solver


class PoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        solver.BROWSER_QUEUE = asyncio.Queue(maxsize=1)
        solver.BROWSER_QUEUE.put_nowait(None)
        solver._active = 0
        self.session = object()

    async def test_repeated_errors_do_not_consume_slots(self):
        with patch.object(solver, '_new_session', AsyncMock(side_effect=RuntimeError('startup failed'))):
            for _ in range(6):
                with self.assertRaises(RuntimeError):
                    await solver._fetch_once('url', 'key')
                self.assertEqual(solver.BROWSER_QUEUE.qsize(), 1)
                self.assertEqual(solver._active, 0)

    async def test_solve_failure_rebuilds_then_succeeds(self):
        from types import SimpleNamespace
        session = SimpleNamespace(page=SimpleNamespace(url='url'))
        with patch.object(solver, '_new_session', AsyncMock(return_value=session)) as create, \
             patch.object(solver, '_close_session', AsyncMock()) as close, \
             patch.object(solver, 'solve_turnstile', AsyncMock(side_effect=[RuntimeError('challenge'), 'token'])):
            with self.assertRaises(RuntimeError):
                await solver._fetch_once('url', 'key')
            self.assertEqual(await solver._fetch_once('url', 'key'), 'token')
            self.assertEqual(create.await_count, 2)
            close.assert_awaited_once_with(session)
            self.assertEqual(solver.BROWSER_QUEUE.qsize(), 1)

    async def test_timeout_and_cancellation_restore_slot(self):
        from types import SimpleNamespace
        session = SimpleNamespace(page=SimpleNamespace(url='url'))
        async def hang(*args, **kwargs):
            await asyncio.Event().wait()
        with patch.object(solver, '_new_session', AsyncMock(return_value=session)), \
             patch.object(solver, '_close_session', AsyncMock()), \
             patch.object(solver, 'solve_turnstile', hang), \
             patch.object(solver, 'SOLVE_TIMEOUT', 0.02):
            with self.assertRaises(TimeoutError):
                await solver._fetch_once('url', 'key')
            self.assertEqual(solver.BROWSER_QUEUE.qsize(), 1)
            task = asyncio.create_task(solver._fetch_once('url', 'key'))
            await asyncio.sleep(0.005)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(solver.BROWSER_QUEUE.qsize(), 1)
            self.assertEqual(solver._active, 0)

    async def test_queue_wait_is_bounded(self):
        solver.BROWSER_QUEUE.get_nowait()
        with patch.object(solver, 'QUEUE_TIMEOUT', 0.01):
            with self.assertRaises(TimeoutError):
                await solver._fetch_once('url', 'key')

    async def test_request_retries_are_bounded(self):
        with patch.object(solver, '_fetch_once', AsyncMock(side_effect=RuntimeError('HTTP 520'))) as fetch, \
             patch.object(solver.asyncio, 'sleep', AsyncMock()):
            with self.assertRaises(RuntimeError):
                await solver.fetch_turnstile_token('url', 'key')
            self.assertEqual(fetch.await_count, 3)


if __name__ == '__main__':
    unittest.main()
