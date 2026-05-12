import WebSocket from "ws";
import { EventEmitter } from "events";

export class RDPClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private connectedFlag = false;
  private pendingRequests: Map<string, (val: any) => void> = new Map();
  private eventListeners: Map<string, Array<(data: any) => void>> = new Map();
  private timeoutSec: number;

  constructor(timeoutSec: number = 10) {
    super();
    this.timeoutSec = timeoutSec;
  }

  public connect(host: string, port: number): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(`ws://${host}:${port}`);
      const timer = setTimeout(() => {
        reject(new Error("Timeout connecting to RDP"));
        this.disconnect();
      }, this.timeoutSec * 1000);

      this.ws.on("open", () => {
        clearTimeout(timer);
        this.connectedFlag = true;
        resolve();
      });

      this.ws.on("message", (data) => {
        try {
          const msg = JSON.parse(data.toString());
          // Extract reply tracking if any (some gecko packets use 'from' as request correlation if we wrap it, or we rely on 'type' matches, but usually we just broadcast)
          this.handleMessage(msg);
        } catch (e) {
          // ignore
        }
      });

      this.ws.on("error", (err) => {
        clearTimeout(timer);
        if (!this.connectedFlag) reject(err);
      });

      this.ws.on("close", () => {
        this.connectedFlag = false;
      });
    });
  }

  private handleMessage(msg: any) {
    const from = msg.from;
    const type = msg.type;
    if (from && this.eventListeners.has(from)) {
       const listeners = this.eventListeners.get(from)!;
       for (const l of listeners) {
         try { l(msg); } catch(e) {}
       }
    }
  }

  public send_receive(msg: any, timeoutMs?: number): Promise<any> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        return reject(new Error("WS not connected"));
      }

      const to = msg.to;
      const type = msg.type;

      const timer = setTimeout(() => {
        this.remove_event_listener(to, type, handler); // fallback logic
        resolve(null); // Timeout instead of throw to match python
      }, timeoutMs || this.timeoutSec * 1000);

      const handler = (data: any) => {
         // rudimentary matching
         if (data.from === to && (data.type === type || !type || data.error)) {
            clearTimeout(timer);
            this.remove_event_listener(to, "", handler);
            resolve(data);
         }
      };

      this.add_event_listener(to, "", handler);
      this.ws.send(JSON.stringify(msg));
    });
  }

  public add_event_listener(actorId: string, event: string, callback: (data: any) => void) {
      if (!this.eventListeners.has(actorId)) {
         this.eventListeners.set(actorId, []);
      }
      this.eventListeners.get(actorId)!.push(callback);
  }

  public remove_event_listener(actorId: string, event: string, callback: (data: any) => void) {
      if (this.eventListeners.has(actorId)) {
          const filtered = this.eventListeners.get(actorId)!.filter(cb => cb !== callback);
          this.eventListeners.set(actorId, filtered);
      }
  }

  public connected(): boolean {
    return this.connectedFlag;
  }

  public disconnect() {
    this.connectedFlag = false;
    if (this.ws) {
      try { this.ws.close(); } catch(e) {}
      this.ws = null;
    }
  }
}
