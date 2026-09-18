"""One-off: check which Poe bots accept API access with this key."""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import fastapi_poe as fp

from app.config import settings

CANDIDATES = [
    "GPT-5-mini",
    "Claude-Sonnet-5",
    "GPT-5.6-Sol",
    # fallbacks to try if the above fail
    "Claude-Sonnet-4.5",
    "Claude-Sonnet-4",
    "GPT-5.1",
    "Gemini-2.5-Flash",
]


async def probe(bot: str) -> str:
    try:
        chunks = []
        async for p in fp.get_bot_response(
            messages=[fp.ProtocolMessage(role="user", content="Reply with exactly: OK")],
            bot_name=bot,
            api_key=settings.poe_api_key,
        ):
            chunks.append(p.text)
        return f"WORKS  ({''.join(chunks)[:30].strip()})"
    except Exception as e:
        return f"FAILS  ({str(e)[:90]})"


async def main():
    for bot in CANDIDATES:
        print(f"{bot:22} -> {await probe(bot)}")


asyncio.run(main())
