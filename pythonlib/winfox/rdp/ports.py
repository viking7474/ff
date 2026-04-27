import asyncio
import time
from typing import Optional


def _check_port(host: str, port: int) -> bool:
    """Synchronous TCP port check (Windows-compatible)."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((host, port))
        sock.close()
        return True
    except (ConnectionRefusedError, OSError, socket.timeout):
        return False


def _port_bindable(host: str, port: int) -> bool:
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


async def _wait_for_port(host: str, port: int, timeout: float = 60.0) -> None:
    """Wait for a TCP port to accept connections. Uses sync socket in thread for Windows compatibility."""
    deadline = time.time() + timeout
    delay = 0.2
    while time.time() < deadline:
        is_open = await asyncio.to_thread(_check_port, host, port)
        if is_open:
            return
        await asyncio.sleep(delay)
        delay = min(delay * 1.5, 2.0)
    raise TimeoutError(f"Port {port} not ready within {timeout}s")


class _PortAllocator:
    """Process-local port allocator for RDPBrowser instances."""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._reserved: set[int] = set()

    async def reserve(self, port: int) -> int:
        async with self._lock:
            if port in self._reserved:
                raise RuntimeError(f"Port already reserved in allocator: {port}")
            bindable = await asyncio.to_thread(_port_bindable, "127.0.0.1", port)
            if not bindable:
                raise RuntimeError(f"Port is not available: {port}")
            self._reserved.add(port)
            return port

    async def find_and_reserve(self, start_port: int, limit: int = 500) -> int:
        async with self._lock:
            port = start_port
            while port < start_port + limit:
                if port in self._reserved:
                    port += 1
                    continue
                bindable = await asyncio.to_thread(_port_bindable, "127.0.0.1", port)
                if bindable:
                    self._reserved.add(port)
                    return port
                port += 1
            raise RuntimeError(f"Unable to find available port near {start_port}")

    async def release(self, port: Optional[int]) -> None:
        if port is None:
            return
        async with self._lock:
            self._reserved.discard(port)


_PORT_ALLOCATOR = _PortAllocator()
