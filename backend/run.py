"""Server entry point (dev and cloud).

On Windows this owns event-loop creation — psycopg async needs a Selector
loop, and the uvicorn CLI defaults to Proactor. On cloud hosts (Render etc.)
it binds 0.0.0.0 on the platform-provided $PORT."""

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


async def main() -> None:
    port = int(os.environ.get("PORT", "8000"))
    # cloud platforms inject PORT and need a public bind; local dev stays loopback
    host = os.environ.get("HOST", "0.0.0.0" if "PORT" in os.environ else "127.0.0.1")
    config = uvicorn.Config("app.main:app", host=host, port=port)
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(main())
