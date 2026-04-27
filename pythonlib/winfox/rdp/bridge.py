import asyncio
import json
import logging
import uuid
from typing import Any, Dict


logger = logging.getLogger(__name__)


class _ExtensionBridge:
    def __init__(self, port: int):
        self._port = port
        self._server = None
        self._ws = None
        self._pending: Dict[str, asyncio.Future] = {}
        self._connected = asyncio.Event()

    async def start(self):
        try:
            import websockets

            self._server = await websockets.serve(
                self._handler, "127.0.0.1", self._port
            )
            logger.info(f"Extension bridge listening on ws://127.0.0.1:{self._port}")
        except ImportError:
            logger.warning("websockets not installed, extension input unavailable")

    async def _handler(self, ws):
        self._ws = ws
        self._connected.set()
        logger.info("Extension connected")
        try:
            async for raw in ws:
                data = json.loads(raw)
                if data.get("type") == "hello":
                    logger.info(f"Extension hello: {data.get('extensionId')}")
                    continue
                msg_id = data.get("id")
                if msg_id and msg_id in self._pending:
                    self._pending[msg_id].set_result(data)
        except Exception:
            pass
        finally:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError("Extension bridge disconnected"))
            self._pending.clear()
            self._ws = None
            self._connected.clear()

    async def send_command(self, cmd: str, params: dict, timeout: float = 10.0) -> Any:
        if not self._ws:
            if not self._connected.is_set():
                try:
                    await asyncio.wait_for(self._connected.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    raise ConnectionError("Extension not connected")

        msg_id = str(uuid.uuid4())[:8]
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut

        await self._ws.send(json.dumps({"id": msg_id, "cmd": cmd, "params": params}))

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

        if result.get("error"):
            raise RuntimeError(f"Extension error: {result['error']}")
        return result.get("result")

    async def stop(self):
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError("Extension bridge stopped"))
        self._pending.clear()
        self._connected.clear()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def is_connected(self) -> bool:
        return self._ws is not None
