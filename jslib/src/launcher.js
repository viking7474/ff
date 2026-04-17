import { firefox } from 'playwright';
import { FingerprintGenerator } from 'fingerprint-generator';
import geoip from 'geoip-lite';

/**
 * Generates a realistic fingerprint using fingerprint-generator and formats it
 * to match the JSON structure expected by Camoufox's MaskConfig mechanism.
 */
export function generateCamoufoxConfig(options = {}) {
    // Generate a fingerprint based on options (defaulting to desktop devices)
    const generator = new FingerprintGenerator({
        devices: ['desktop'],
        browsers: [{ name: 'firefox', minVersion: 110 }],
        operatingSystems: ['windows', 'macos', 'linux']
    });

    const { fingerprint } = generator.getFingerprint();

    const config = {
        "window.innerWidth": fingerprint.screen.width,
        "window.innerHeight": fingerprint.screen.height,
        "screen.width": fingerprint.screen.width,
        "screen.height": fingerprint.screen.height,
        "screen.availWidth": fingerprint.screen.width,
        "screen.availHeight": fingerprint.screen.height,
        "screen.colorDepth": fingerprint.screen.colorDepth,
        "screen.pixelDepth": fingerprint.screen.pixelDepth,
        "navigator.userAgent": fingerprint.navigator.userAgent,
        "navigator.platform": fingerprint.navigator.platform,
        "navigator.appVersion": fingerprint.navigator.appVersion,
        "navigator.language": fingerprint.navigator.language,
        "navigator.hardwareConcurrency": fingerprint.navigator.hardwareConcurrency,
        "headers.User-Agent": fingerprint.navigator.userAgent,
        "headers.Accept-Language": fingerprint.navigator.language,
        "battery:charging": true,
        "battery:level": 1.0,
        "fonts": fingerprint.fonts || ["Arial", "Courier", "Times New Roman"],
        "debug": false
    };

    // GeoIP parsing
    if (options.proxyIP) {
        const geo = geoip.lookup(options.proxyIP);
        if (geo) {
            config["geolocation:latitude"] = geo.ll[0];
            config["geolocation:longitude"] = geo.ll[1];
            config["timezone"] = geo.timezone;
        }
    }

    return config;
}

/**
 * Launch Camoufox via Playwright with the injected fingerprint config.
 */
export async function launchCamoufox(camoufoxPath, options = {}) {
    const config = generateCamoufoxConfig(options);
    const configString = JSON.stringify(config);

    // In case the config is too large for a single environment variable,
    // Camoufox's MaskConfig supports CAMOU_CONFIG_1, CAMOU_CONFIG_2, etc.
    // For simplicity in this skeleton, we use the fallback CAMOU_CONFIG.

    const env = {
        ...process.env,
        CAMOU_CONFIG: configString,
    };

    // Add optional custom ENV vars
    if (options.env) {
        Object.assign(env, options.env);
    }

    const browser = await firefox.launch({
        executablePath: camoufoxPath,
        headless: options.headless !== undefined ? options.headless : true,
        env,
        args: options.args || []
    });

    return browser;
}
