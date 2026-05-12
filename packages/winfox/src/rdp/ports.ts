import net from "net";

function _checkPort(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    sock.setTimeout(1000);
    sock.on('connect', () => {
      sock.destroy();
      resolve(true);
    });
    sock.on('timeout', () => {
      sock.destroy();
      resolve(false);
    });
    sock.on('error', () => {
      resolve(false);
    });
    sock.connect(port, host);
  });
}

function _portBindable(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.on('error', () => resolve(false));
    server.listen(port, host, () => {
      server.close(() => resolve(true));
    });
  });
}

export async function waitForPort(host: string, port: number, timeout: number = 60.0): Promise<void> {
  const deadline = Date.now() + timeout * 1000;
  let delay = 200;
  while (Date.now() < deadline) {
    const isOpen = await _checkPort(host, port);
    if (isOpen) return;
    await new Promise(r => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 2000);
  }
  throw new Error(`Port ${port} not ready within ${timeout}s`);
}

class PortAllocator {
  private reserved = new Set<number>();
  private queue: Array<() => void> = [];
  private locked = false;

  private async acquireLock() {
    if (!this.locked) {
      this.locked = true;
      return;
    }
    await new Promise<void>(resolve => this.queue.push(resolve));
  }

  private releaseLock() {
    if (this.queue.length > 0) {
      const next = this.queue.shift();
      if (next) next();
    } else {
      this.locked = false;
    }
  }

  async reserve(port: number): Promise<number> {
    await this.acquireLock();
    try {
      if (this.reserved.has(port)) throw new Error(`Port already reserved in allocator: ${port}`);
      const bindable = await _portBindable("127.0.0.1", port);
      if (!bindable) throw new Error(`Port is not available: ${port}`);
      this.reserved.add(port);
      return port;
    } finally {
      this.releaseLock();
    }
  }

  async findAndReserve(startPort: number, limit: number = 500): Promise<number> {
    await this.acquireLock();
    try {
      let port = startPort;
      while (port < startPort + limit) {
        if (this.reserved.has(port)) {
          port++;
          continue;
        }
        const bindable = await _portBindable("127.0.0.1", port);
        if (bindable) {
          this.reserved.add(port);
          return port;
        }
        port++;
      }
      throw new Error(`Unable to find available port near ${startPort}`);
    } finally {
      this.releaseLock();
    }
  }

  async release(port: number | undefined): Promise<void> {
    if (port === undefined) return;
    await this.acquireLock();
    try {
      this.reserved.delete(port);
    } finally {
      this.releaseLock();
    }
  }
}

export const PORT_ALLOCATOR = new PortAllocator();
