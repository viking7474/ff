import { test } from "node:test";
import * as assert from "node:assert";
import * as path from "node:path";
import * as fs from "node:fs";
import { RDPBrowser } from "../src/rdp/browser.js";

const WINFOX_PATH = process.env.WINFOX_PATH || "";
const RDP_PORT = parseInt(process.env.RDP_PORT || "7000", 10);
const WS_PORT = parseInt(process.env.WS_PORT || "9700", 10);

test("Context Smoke Test", async () => {
    if (!WINFOX_PATH) {
        console.warn("WINFOX_PATH not set, skipping smoke test");
        return;
    }
    if (!fs.existsSync(WINFOX_PATH)) {
        throw new Error(`WINFOX_PATH not found: ${WINFOX_PATH}`);
    }

    const browser = new RDPBrowser({
        executablePath: WINFOX_PATH,
        headless: false,
        rdpPort: RDP_PORT,
        wsPort: WS_PORT
    });

    try {
        await browser.start();

        const ctx1 = await browser.newContext();
        const ctx2 = await browser.newContext();
        console.log("contexts count:", browser.contexts().length);

        const page1 = await ctx1.newPage();
        await page1.goto("https://example.com");
        await page1.waitForLoadState("load");
        await page1.setLocalStorage({ "ctx_key": "ctx1" });

        const page2 = await ctx2.newPage();
        await page2.goto("https://example.com");
        await page2.waitForLoadState("load");
        const storage2 = await page2.getLocalStorage();
        console.log("ctx2 localStorage before load:", storage2);
        if (storage2["ctx_key"] === "ctx1") {
            throw new Error("Context isolation failed before state load");
        }

        const state1 = await ctx1.saveState();
        console.log("ctx1 state origins:", (state1.origins || []).length);
        await ctx2.loadState(state1, { clearExisting: true });

        const page2b = await ctx2.newPage();
        await page2b.goto("https://example.com");
        await page2b.waitForLoadState("load");
        const storage2b = await page2b.getLocalStorage();
        console.log("ctx2 localStorage after load:", storage2b);
        if (storage2b["ctx_key"] !== "ctx1") {
            throw new Error("Context state load failed");
        }

        console.log("ctx1 pages:", ctx1.pages().length);
        console.log("ctx2 pages:", ctx2.pages().length);

        await ctx2.close();
        console.log("contexts after closing ctx2:", browser.contexts().length);
        if (browser.contexts().length !== 1) {
            throw new Error("Context close/unregister failed");
        }

        await ctx1.close();
        console.log("contexts after closing ctx1:", browser.contexts().length);
        if (browser.contexts().length !== 0) {
            throw new Error("All contexts should be closed");
        }

        console.log("PASS context smoke test");
    } finally {
        await browser.close();
    }
});
