import { generateCamoufoxConfig } from './launcher.js';

console.log("Testing fingerprint generation...");
const config = generateCamoufoxConfig({ proxyIP: '8.8.8.8' });
console.log(JSON.stringify(config, null, 2));
