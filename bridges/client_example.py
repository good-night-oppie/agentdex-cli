"""Minimal Hermes-side client. Sends one chat to each bridge.

Usage:
  python claude_bridge.py &   # 49801
  python codex_bridge.py &    # 49802
  python gemini_bridge.py &   # 49803
  python client_example.py
"""
import asyncio
import json
import sys


async def call(host: str, port: int, method: str, params: dict, rid: int = 1) -> dict:
    reader, writer = await asyncio.open_connection(host, port)
    writer.write((json.dumps({"id": rid, "method": method, "params": params}) + "\n").encode())
    await writer.drain()
    line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(line)


async def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "say hi"
    for name, port in [("claude", 49801), ("codex", 49802), ("gemini", 49803)]:
        try:
            r = await call("127.0.0.1", port, "chat", {"prompt": prompt})
            print(f"[{name}] {r}")
        except Exception as e:
            print(f"[{name}] ERR {e}")


if __name__ == "__main__":
    asyncio.run(main())
