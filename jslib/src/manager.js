import os from 'os';
import path from 'path';
import fs from 'fs';
import axios from 'axios';
import { extract } from 'tar-fs';
import unzipper from 'unzipper';
import { pipeline } from 'stream/promises';
import zlib from 'zlib';

const REPO_OWNER = 'daijro';
const REPO_NAME = 'camoufox';
const CACHE_DIR = path.join(os.homedir(), '.cache', 'camoufox-js');

/**
 * Gets the current OS and architecture strings mapping to release asset names.
 */
function getSystemInfo() {
    const platform = os.platform();
    const arch = os.arch();

    let sysOs = 'linux';
    if (platform === 'win32') sysOs = 'windows';
    else if (platform === 'darwin') sysOs = 'macos';

    let sysArch = 'x86_64';
    if (arch === 'arm64' || arch === 'aarch64') sysArch = 'arm64';
    else if (arch === 'ia32') sysArch = 'i686';

    return { sysOs, sysArch };
}

/**
 * Fetches the latest release from the official repository.
 */
export async function getLatestRelease() {
    const url = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/releases/latest`;
    try {
        const response = await axios.get(url);
        return response.data;
    } catch (err) {
        throw new Error(`Failed to fetch latest release: ${err.message}`);
    }
}

/**
 * Downloads and extracts the Camoufox binary for the current system.
 */
export async function fetchCamoufox() {
    const { sysOs, sysArch } = getSystemInfo();
    const release = await getLatestRelease();

    // Find the correct asset
    const assetPrefix = `camoufox-${sysOs}-${sysArch}`;
    const asset = release.assets.find(a => a.name.startsWith(assetPrefix));

    if (!asset) {
        throw new Error(`No compatible release found for ${sysOs}-${sysArch}`);
    }

    const versionDir = path.join(CACHE_DIR, release.tag_name);
    const executablePath = path.join(versionDir, sysOs === 'windows' ? 'camoufox.exe' : 'camoufox');

    if (fs.existsSync(executablePath)) {
        console.log(`Camoufox ${release.tag_name} is already installed.`);
        return executablePath;
    }

    if (!fs.existsSync(versionDir)) {
        fs.mkdirSync(versionDir, { recursive: true });
    }

    console.log(`Downloading Camoufox ${release.tag_name} for ${sysOs}-${sysArch}...`);
    const response = await axios({
        url: asset.browser_download_url,
        method: 'GET',
        responseType: 'stream'
    });

    if (asset.name.endsWith('.zip')) {
        await response.data.pipe(unzipper.Extract({ path: versionDir })).promise();
    } else if (asset.name.endsWith('.tar.gz') || asset.name.endsWith('.tgz')) {
        await pipeline(response.data, zlib.createGunzip(), extract(versionDir));
    } else if (asset.name.endsWith('.tar.bz2')) {
        // Simple fallback, though typically node doesn't natively support bz2 stream easily without a library
        console.warn("bzip2 extraction not natively implemented in this skeleton. Needs external tool or library.");
    } else {
        throw new Error(`Unknown archive format: ${asset.name}`);
    }

    // Ensure executable permissions
    if (sysOs !== 'windows' && fs.existsSync(executablePath)) {
        fs.chmodSync(executablePath, '755');
    }

    return executablePath;
}

export function getCamoufoxPath() {
    // A simplified method that just gets the latest cached version if available.
    if (!fs.existsSync(CACHE_DIR)) return null;
    const dirs = fs.readdirSync(CACHE_DIR).filter(d => fs.statSync(path.join(CACHE_DIR, d)).isDirectory());
    if (dirs.length === 0) return null;

    // Simple sort to get latest (alphanumeric sort on version tag)
    dirs.sort((a, b) => b.localeCompare(a));
    const { sysOs } = getSystemInfo();
    const execPath = path.join(CACHE_DIR, dirs[0], sysOs === 'windows' ? 'camoufox.exe' : 'camoufox');

    return fs.existsSync(execPath) ? execPath : null;
}
