import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function loadPlaywright() {
  const candidates = ["playwright", "playwright-core"];
  for (const pkg of candidates) {
    try {
      return require(pkg);
    } catch {
      // try npx cache
    }
  }
  const npxDir = path.join(os.homedir(), ".npm", "_npx");
  if (fs.existsSync(npxDir)) {
    for (const entry of fs.readdirSync(npxDir)) {
      for (const pkg of candidates) {
        const pkgPath = path.join(npxDir, entry, "node_modules", pkg);
        if (fs.existsSync(pkgPath)) {
          try {
            return require(pkgPath);
          } catch {
            // continue searching
          }
        }
      }
    }
  }
  throw new Error(
    "Playwright Node package not found. Run: npm install playwright && npx playwright install firefox"
  );
}

function findCachedFirefoxExecutable() {
  const cacheRoot = path.join(os.homedir(), ".cache", "ms-playwright");
  if (!fs.existsSync(cacheRoot)) return undefined;
  const dirs = fs
    .readdirSync(cacheRoot)
    .filter((d) => d.startsWith("firefox-"))
    .sort()
    .reverse();
  for (const dir of dirs) {
    const exe = path.join(cacheRoot, dir, "firefox", "firefox");
    if (fs.existsSync(exe)) return exe;
  }
  return undefined;
}

export function extractShortId(input) {
  const raw = String(input || "").trim();
  if (!raw) return "";
  if (/^[A-Za-z0-9_-]{6,32}$/.test(raw)) return raw;
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return "";
  }
  if (!/(^|\.)aidungeon\.com$/i.test(parsed.hostname)) return "";
  const m = parsed.pathname.match(/\/scenario\/([A-Za-z0-9_-]+)/);
  return m ? m[1] : "";
}

async function fetchScenarioGraphql(page, shortId) {
  let details = null;
  let playScenario = null;

  const onResponse = async (resp) => {
    if (!resp.url().includes("api.aidungeon.com/graphql")) return;
    if (resp.status() !== 200) return;
    try {
      const json = await resp.json();
      const items = Array.isArray(json) ? json : [json];
      for (const item of items) {
        const sc = item?.data?.scenario;
        if (!sc || (sc.shortId && sc.shortId !== shortId)) continue;
        if (sc.title !== undefined || sc.tags !== undefined) {
          details = { ...(details || {}), ...sc };
        }
        if (
          sc.state &&
          (sc.state.plotEssentials !== undefined ||
            sc.state.authorsNote !== undefined ||
            sc.state.instructions !== undefined ||
            sc.storyCards !== undefined)
        ) {
          playScenario = sc;
        }
      }
    } catch {
      // ignore non-JSON responses
    }
  };

  page.on("response", onResponse);
  try {
    await page.goto(
      `https://play.aidungeon.com/scenario/${shortId}/scenario?published=true`,
      { waitUntil: "domcontentloaded", timeout: 30000 }
    );
    const waitStart = Date.now();
    while (!details && Date.now() - waitStart < 15000) {
      await page.waitForTimeout(250);
    }

    await page.goto(
      `https://play.aidungeon.com/scenario/${shortId}/scenario/play?published=true`,
      { waitUntil: "domcontentloaded", timeout: 30000 }
    );
    const playStart = Date.now();
    while (!playScenario && Date.now() - playStart < 20000) {
      await page.waitForTimeout(250);
    }
  } finally {
    page.off("response", onResponse);
  }

  return { details, playScenario };
}

async function fetchOptionScenario(page, shortId) {
  let playScenario = null;
  const onResponse = async (resp) => {
    if (!resp.url().includes("api.aidungeon.com/graphql") || resp.status() !== 200) return;
    try {
      const json = await resp.json();
      const items = Array.isArray(json) ? json : [json];
      for (const item of items) {
        const sc = item?.data?.scenario;
        if (sc && sc.shortId === shortId && sc.state) {
          playScenario = sc;
        }
      }
    } catch {
      // ignore
    }
  };
  page.on("response", onResponse);
  try {
    await page.goto(
      `https://play.aidungeon.com/scenario/${shortId}/option/play?published=true`,
      { waitUntil: "domcontentloaded", timeout: 25000 }
    );
    const start = Date.now();
    while (!playScenario && Date.now() - start < 12000) {
      await page.waitForTimeout(200);
    }
  } finally {
    page.off("response", onResponse);
  }
  return playScenario;
}

async function hydrateOptionsTree(page, options, visited, budget, depth = 0) {
  if (!Array.isArray(options) || depth > 4) return [];
  const out = [];
  for (const opt of options.slice(0, 15)) {
    if (!opt || opt.deletedAt || !opt.shortId) continue;
    if (visited.has(opt.shortId) || budget.count >= budget.max) {
      out.push({
        id: String(opt.id || opt.shortId),
        shortId: opt.shortId,
        label: String(opt.title || "Option"),
        title: String(opt.title || "Option"),
      });
      continue;
    }
    visited.add(opt.shortId);
    budget.count += 1;
    let optPlay = null;
    try {
      optPlay = await fetchOptionScenario(page, opt.shortId);
    } catch {
      // continue with basic option info
    }
    const optState = optPlay?.state || {};
    const subOpts = Array.isArray(optPlay?.options) ? optPlay.options : [];
    const childChoices = subOpts.length
      ? await hydrateOptionsTree(page, subOpts, visited, budget, depth + 1)
      : [];
    const cards = [
      ...(Array.isArray(optPlay?.inheritedStoryCards) ? optPlay.inheritedStoryCards : []),
      ...(Array.isArray(optPlay?.storyCards) ? optPlay.storyCards : []),
    ].filter((c) => c && !c.deletedAt);

    out.push({
      id: String(opt.id || opt.shortId),
      shortId: opt.shortId,
      label: String(opt.title || "Option"),
      title: String(opt.title || "Option"),
      opening: String(optState.prompt || ""),
      plot_essentials: String(optState.plotEssentials || optState.memory || ""),
      ai_instructions:
        typeof optState.instructions === "object"
          ? String(optState.instructions?.scenario || optState.instructions?.text || "")
          : String(optState.instructions || ""),
      story_summary: String(optState.storySummary || ""),
      authors_note: String(optState.authorsNote || ""),
      story_cards: cards,
      choices: childChoices,
    });
  }
  return out;
}

async function main() {
  const inputUrl = process.argv[2] || "";
  const shortId = extractShortId(inputUrl);
  if (!shortId) {
    console.error("Invalid AI Dungeon scenario URL or shortId.");
    process.exit(2);
  }

  const { firefox } = loadPlaywright();
  const executablePath = findCachedFirefoxExecutable();
  const launchOpts = { headless: true };
  if (executablePath) {
    launchOpts.executablePath = executablePath;
  }

  const browser = await firefox.launch(launchOpts);
  try {
    const context = await browser.newContext();
    const page = await context.newPage();

    const { details, playScenario } = await fetchScenarioGraphql(page, shortId);
    if (!playScenario && !details) {
      console.error("Timed out waiting for AI Dungeon scenario data.");
      process.exit(1);
    }

    const base = playScenario || details || {};
    const options = Array.isArray(base.options) ? base.options : [];
    const hydratedOptions = await hydrateOptionsTree(
      page,
      options,
      new Set([shortId]),
      { count: 0, max: 30 },
      0
    );

    const mergedScenario = {
      ...(details || {}),
      ...(playScenario || {}),
      state: {
        ...(details?.state || {}),
        ...(playScenario?.state || {}),
      },
      options: hydratedOptions.length ? hydratedOptions : options,
    };

    const output = {
      details: details || {},
      scenario: mergedScenario,
      state: mergedScenario.state || {},
      storyCards: mergedScenario.storyCards || [],
      inheritedStoryCards: mergedScenario.inheritedStoryCards || [],
      options: mergedScenario.options || [],
    };
    process.stdout.write(JSON.stringify(output));
  } finally {
    await browser.close();
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((err) => {
    console.error(err?.message || String(err));
    process.exit(1);
  });
}
