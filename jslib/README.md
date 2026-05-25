# Camoufox-js

`camoufox-js` is a Node.js/JavaScript wrapper for [Camoufox](https://github.com/daijro/camoufox). It replaces the original Python toolkit with a native JavaScript implementation, making it seamless to integrate into Playwright projects.

## Features
- **Binary Manager:** Automatically fetches and extracts the appropriate Camoufox binary for your OS and Architecture.
- **Fingerprint Generation:** Uses `fingerprint-generator` to create realistic browser profiles (User-Agent, screen dimensions, WebGL, fonts).
- **GeoIP Integration:** Automatically resolves proxy IPs to latitude, longitude, and timezone.
- **Environment Injection:** Directly maps the generated configuration to the `CAMOU_CONFIG` environment variable as expected by the Camoufox C++ patches.

## Usage Example

```javascript
import { fetchCamoufox, launchCamoufox } from 'camoufox-js';

(async () => {
    // 1. Download/Get path to the latest Camoufox binary
    const executablePath = await fetchCamoufox();

    // 2. Launch the browser with spoofed fingerprints
    const browser = await launchCamoufox(executablePath, {
        headless: false,
        proxyIP: '8.8.8.8' // Automatically sets timezone and geolocation
    });

    const page = await browser.newPage();
    await page.goto('https://bot.sannysoft.com');

    // ... do your scraping

    await browser.close();
})();
```

## How it works?

Camoufox includes C++ patches (like `MaskConfig.hpp`) that intercept internal browser calls (e.g., `window.innerWidth`, `navigator.userAgent`). It looks for the environment variable `CAMOU_CONFIG` containing a JSON payload with spoofed values.

`camoufox-js` acts as the bridge: generating real-world statistical fingerprints in NodeJS and passing them to Camoufox via this mechanism.

## Testing with an existing binary

If you already have a `camoufox.exe` (or `camoufox` on macOS/Linux) built and you want to test the wrapper without fetching from GitHub, you can use the `run-existing.js` script.

1. Ensure you have the dependencies installed:
   ```bash
   npm install
   ```

2. Run the script and specify the path to your executable using the `CAMOUFOX_PATH` environment variable:
   ```bash
   # On Windows (Command Prompt)
   set CAMOUFOX_PATH=C:\path\to\camoufox.exe
   node run-existing.js

   # On Windows (PowerShell)
   $env:CAMOUFOX_PATH="C:\path\to\camoufox.exe"; node run-existing.js

   # On Linux / macOS
   CAMOUFOX_PATH=/path/to/camoufox node run-existing.js
   ```

The script will generate a realistic fingerprint, calculate the GeoIP data (defaulting to testing IP `8.8.8.8`), inject the `CAMOU_CONFIG` environment variable, and open the browser.
