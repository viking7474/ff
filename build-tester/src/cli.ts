import { build as esbuild } from "esbuild";
import { createServer } from "node:http";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

import {
  buildCertificateText,
  buildFullResult,
  countAllChecks,
  generateCertificate,
  launchWinfox,
  printCertificate,
  printProfileResult,
  resolveWinfoxExecutablePath,
  type TesterProfileResult,
  type TesterResults,
} from "../../packages/winfox/src/index.js";

type ParsedArgs = {
  executablePath?: string;
  headful: boolean;
  timeoutMs: number;
  saveJson?: string;
  saveCert?: string;
  secret: string;
  noCert: boolean;
  help: boolean;
};

function parseArgs(argv: string[]): ParsedArgs {
  const parsed: ParsedArgs = {
    headful: false,
    timeoutMs: 120000,
    secret: "winfox-build-tester",
    noCert: false,
    help: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];

    if (arg === "--help" || arg === "-h") {
      parsed.help = true;
      continue;
    }

    if (arg === "--headful") {
      parsed.headful = true;
      continue;
    }

    if (arg === "--executable-path") {
      parsed.executablePath = argv[i + 1];
      i += 1;
      continue;
    }

    if (arg === "--timeout-ms") {
      parsed.timeoutMs = Number(argv[i + 1] ?? parsed.timeoutMs);
      i += 1;
      continue;
    }

    if (arg === "--save-json") {
      parsed.saveJson = argv[i + 1];
      i += 1;
      continue;
    }

    if (arg === "--save-cert") {
      parsed.saveCert = argv[i + 1];
      i += 1;
      continue;
    }

    if (arg === "--secret") {
      parsed.secret = argv[i + 1] ?? parsed.secret;
      i += 1;
      continue;
    }

    if (arg === "--no-cert") {
      parsed.noCert = true;
      continue;
    }

    if (!arg.startsWith("--") && !parsed.executablePath) {
      parsed.executablePath = arg;
      continue;
    }

    throw new Error(`Unknown argument: ${arg}`);
  }

  return parsed;
}

async function ensureBundle(projectDir: string): Promise<string> {
  const outfile = resolve(projectDir, "scripts", "checks-bundle.js");
  const entry = resolve(projectDir, "src", "lib", "checks", "index.ts");

  await mkdir(resolve(projectDir, "scripts"), { recursive: true });
  await esbuild({
    entryPoints: [entry],
    bundle: true,
    platform: "browser",
    target: "es2017",
    format: "iife",
    globalName: "WinfoxChecks",
    outfile,
  });

  return outfile;
}

async function startServer(projectDir: string): Promise<{ port: number; close: () => Promise<void> }> {
  const templatePath = resolve(projectDir, "scripts", "test_page_template.html");
  const bundlePath = resolve(projectDir, "scripts", "checks-bundle.js");
  const [template, bundle] = await Promise.all([readFile(templatePath), readFile(bundlePath)]);

  const server = createServer((req, res) => {
    if (!req.url || req.url === "/test" || req.url === "/test/") {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      res.end(template);
      return;
    }

    if (req.url === "/checks-bundle.js") {
      res.writeHead(200, { "content-type": "application/javascript; charset=utf-8" });
      res.end(bundle);
      return;
    }

    res.writeHead(404);
    res.end();
  });

  await new Promise<void>((resolvePromise) => server.listen(0, "127.0.0.1", () => resolvePromise()));
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Failed to start local HTTP server.");
  }

  return {
    port: address.port,
    close: () => new Promise((resolvePromise, rejectPromise) => {
      server.close((error) => {
        if (error) {
          rejectPromise(error);
          return;
        }
        resolvePromise();
      });
    }),
  };
}

function printHelp(): void {
  console.log(`Winfox Build Tester\n\nUsage:\n  npm run test --workspace winfox-build-tester -- [binary_path] [options]\n\nOptions:\n  --executable-path PATH  Path to winfox binary or app bundle\n  --headful               Run with a visible window\n  --timeout-ms N          Wait timeout for page checks (default: 120000)\n  --save-json PATH        Save raw results JSON\n  --save-cert PATH        Save ASCII certificate text\n  --secret KEY            HMAC signing key for the certificate\n  --no-cert               Skip certificate generation\n  --help                  Show this message\n`);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    printHelp();
    return;
  }

  const projectDir = resolve(process.cwd());
  const executablePath = resolveWinfoxExecutablePath({ executablePath: args.executablePath });
  const bundlePath = await ensureBundle(projectDir);
  const server = await startServer(projectDir);

  console.log("Winfox Build Tester");
  console.log(`Executable: ${executablePath}`);
  console.log(`Bundle:     ${bundlePath}`);
  console.log(`Server:     http://127.0.0.1:${server.port}/test`);

  const browser = await launchWinfox({
    executablePath,
    headless: !args.headful,
  });

  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${server.port}/test`, { waitUntil: "domcontentloaded", timeout: args.timeoutMs });
    await page.waitForFunction("Boolean(window.__testComplete__)", undefined, { timeout: args.timeoutMs });

    const error = await page.evaluate<string | null>("window.__testError__ ?? null");
    if (error) {
      throw new Error(error);
    }

    const results = await page.evaluate<TesterResults>("window.__testResults__");
    const counts = countAllChecks(results);
    const profileResult: TesterProfileResult = {
      profile: {
        name: "Build Verification",
        os: process.platform === "darwin" ? "macos" : process.platform === "win32" ? "windows" : "linux",
      },
      results,
      matchResults: [],
      grade: "F",
      passCount: counts.passed,
      totalChecks: counts.total,
    };
    const fullResult = buildFullResult({
      profiles: [profileResult],
      binaryPath: executablePath,
    });
    profileResult.grade = fullResult.overallGrade;

    printProfileResult(profileResult);

    console.log(`Grade:      ${fullResult.overallGrade}`);
    console.log(`Score:      ${fullResult.totalPassed}/${fullResult.totalChecks}`);

    if (args.saveJson) {
      await writeFile(resolve(args.saveJson), JSON.stringify(fullResult, null, 2), "utf8");
      console.log(`Saved JSON: ${resolve(args.saveJson)}`);
    }

    if (!args.noCert) {
      const title = "WINFOX BUILD VERIFICATION CERTIFICATE";
      const certificate = generateCertificate(fullResult, {
        title,
        platform: "Build Tester",
        secret: args.secret,
      });
      printCertificate(certificate, fullResult.crossProfile, fullResult.overallGrade, title);
      if (certificate.failedTests.length > 0) {
        console.log("Failed checks:");
        for (const failedTest of certificate.failedTests) {
          console.log(`  - ${failedTest}`);
        }
      }
      if (args.saveCert) {
        await writeFile(resolve(args.saveCert), buildCertificateText(certificate, fullResult.crossProfile, fullResult.overallGrade, title), "utf8");
        console.log(`Saved certificate: ${resolve(args.saveCert)}`);
      }
    }

    process.exitCode = fullResult.overallGrade === "A" || fullResult.overallGrade === "B" ? 0 : 1;
  } finally {
    await browser.close();
    await server.close();
  }
}

main().catch((error) => {
  console.error(`ERROR: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
