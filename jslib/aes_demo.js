import crypto from 'crypto';

// The JSON data you want to inject
const data = {
    "browser.profileName": "hoadeptrai",
    "showcursor": false,
    "battery:charging": false,
    "battery:level": 0.55
};

const jsonStr = JSON.stringify(data);

// Matches the hardcoded key/IV in MaskConfig.hpp
const key = Buffer.from('CamoufoxSecretKeyForAES256Cipher');
const iv = Buffer.from('0123456789ABCDEF');

// Encrypt AES-256-CBC
const cipher = crypto.createCipheriv('aes-256-cbc', key, iv);
let encrypted = cipher.update(jsonStr, 'utf8', 'hex');
encrypted += cipher.final('hex');

console.log("Encrypted Hex String to pass to CAMOU_CONFIG:");
console.log(encrypted);

// Example of how you would launch:
/*
import { spawn } from 'child_process';
const env = Object.assign({}, process.env, {
    CAMOU_CONFIG: encrypted
});
const browserProcess = spawn('C:\\path\\to\\camoufox.exe', ['-remote-debugging-port', '9222'], { env });
*/
