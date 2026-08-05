import asyncio

from app.db.session import get_db, engine

async def use_get_db_once():
    agen = get_db()
    try:
        session = await agen.__anext__()
        try:
            bind = None
            try:
                bind = session.get_bind()
            except Exception:
                bind = None
            print(f"[SCRIPT] got session_id={id(session)} bind_id={id(bind) if bind is not None else None} engine_id={id(engine)} loop_id={id(asyncio.get_running_loop())}")
        finally:
            await agen.aclose()
    except StopAsyncIteration:
        pass

if __name__ == '__main__':
    # run on two separate event loops
    for i in range(2):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        print(f"--- loop {i} start id={id(loop)} ---")
        loop.run_until_complete(use_get_db_once())
        print(f"--- loop {i} end id={id(loop)} ---")
        loop.close()
