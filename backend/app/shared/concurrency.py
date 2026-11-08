"""스레드 작업이 끝난 뒤 취소를 전파해 늦은 저장 경합을 막습니다."""

import asyncio


async def run_in_thread(fn, *args, on_cancel=None):
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
            if on_cancel is not None:
                on_cancel()
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result
