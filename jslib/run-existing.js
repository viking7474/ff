import { launchCamoufox } from './src/launcher.js';
import path from 'path';

// Set the path to your existing camoufox.exe here
// Note: If you're on Linux/Mac, just point to the 'camoufox' executable
const executablePath = process.env.CAMOUFOX_PATH || path.resolve('./camoufox.exe');

console.log(`Launching Camoufox using existing binary at: ${executablePath}`);

(async () => {
    try {
        const browser = await launchCamoufox(executablePath, {
            headless: false, // Set to true if you don't want the UI
            proxyIP: '8.8.8.8' // Example proxy IP for GeoIP spoofing
        });

        const page = await browser.newPage();
        console.log("Navigating to test site...");

        // Go to a site to test fingerprinting (e.g., BrowserScan or CreepJS)
        await page.goto('https://browserleaks.com/canvas');

        console.log("Browser is open. Press Ctrl+C to exit.");

        // Keep the browser open until the process is killed
        await new Promise(() => {});

    } catch (error) {
        console.error("Failed to launch Camoufox:", error.message);
        console.log("Tip: Make sure you provide the correct path to the executable. You can set the CAMOUFOX_PATH environment variable.");
    }
})();
