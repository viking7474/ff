import WebSocket, { WebSocketServer } from "ws";
import { v4 as uuidv4 } from "uuid";

export class ExtensionBridge {
  private port: number;
  private server: WebSocketServer | null = null;
  private ws: WebSocket | null = null;
  private pending: Map<string, { resolve: (val: any) => void; reject: (err: any) => void }> = new Map();
  private connectedResolvers: Array<() => void> = [];

  constructor(port: number) {
    this.port = port;
  }

  async start(): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        this.server = new WebSocketServer({ host: "127.0.0.1", port: this.port }, () => {
          resolve();
        });
        this.server.on("connection", (ws) => this.handler(ws));
        this.server.on("error", (err) => reject(err));
      } catch (e) {
        reject(e);
      }
    });
  }

  private handler(ws: WebSocket) {
    this.ws = ws;
    while (this.connectedResolvers.length > 0) {
      const r = this.connectedResolvers.shift();
      if (r) r();
    }

    ws.on("message", (raw) => {
      try {
        const data = JSON.parse(raw.toString());
        if (data.type === "hello") return;
        const msgId = data.id;
        if (msgId && this.pending.has(msgId)) {
          this.pending.get(msgId)!.resolve(data);
        }
      } catch (e) {}
    });

    ws.on("close", () => {
      for (const [_, p] of this.pending.entries()) {
        p.reject(new Error("Extension bridge disconnected"));
      }
      this.pending.clear();
      if (this.ws === ws) {
        this.ws = null;
      }
    });
  }

  async sendCommand(cmd: string, params: any, timeoutSec: number = 10.0): Promise<any> {
    if (!this.ws) {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("Extension not connected")), 5000);
        this.connectedResolvers.push(() => {
          clearTimeout(timer);
          resolve();
        });
      });
    }

    const msgId = uuidv4().substring(0, 8);
    let timeoutHandle: any;

    const prom = new Promise((resolve, reject) => {
      this.pending.set(msgId, { resolve, reject });
      timeoutHandle = setTimeout(() => {
        this.pending.delete(msgId);
        reject(new Error(`Extension command ${cmd} timed out after ${timeoutSec}s`));
      }, timeoutSec * 1000);
    });

    this.ws!.send(JSON.stringify({ id: msgId, cmd, params }));
    try {
      const result: any = await prom;
      if (result.error) throw new Error(`Extension error: ${result.error}`);
      return result.result;
    } finally {
      clearTimeout(timeoutHandle);
      this.pending.delete(msgId);
    }
  }

  async stop(): Promise<void> {
    if (this.ws) {
      try { this.ws.close(); } catch (e) {}
      this.ws = null;
    }
    for (const [_, p] of this.pending.entries()) {
      p.reject(new Error("Extension bridge stopped"));
    }
    this.pending.clear();
    if (this.server) {
      this.server.close();
      this.server = null;
    }
  }

  get isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
