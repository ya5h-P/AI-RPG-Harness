from __future__ import annotations

import json
import subprocess
from typing import Any

NODE_SANDBOX_SCRIPT = r"""
const vm = require("vm");
const fs = require("fs");

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const logs = [];
const formatArg = (a) => {
  if (typeof a === "string") return a;
  try { return JSON.stringify(a); } catch { return String(a); }
};

const sandboxConsole = {
  log: (...args) => logs.push("[log] " + args.map(formatArg).join(" ")),
  info: (...args) => logs.push("[info] " + args.map(formatArg).join(" ")),
  warn: (...args) => logs.push("[warn] " + args.map(formatArg).join(" ")),
  error: (...args) => logs.push("[error] " + args.map(formatArg).join(" ")),
};

const storyCards = Array.isArray(input.storyCards)
  ? input.storyCards.map((c) => ({ ...c }))
  : [];

const addStoryCard = (keys, entry, type = "Custom", title = "") => {
  const kStr = String(keys || "");
  if (kStr && storyCards.some((c) => String(c.keys || "") === kStr)) {
    return false;
  }
  const card = {
    id: Math.random().toString(16).slice(2, 12),
    title: String(title || keys || "Card"),
    type: String(type || "Custom"),
    card_type: String(type || "Custom"),
    keys: kStr,
    entry: String(entry || ""),
  };
  storyCards.push(card);
  return storyCards.length - 1;
};

const updateStoryCard = (index, keys, entry, type, title) => {
  const i = Number(index);
  if (!Number.isInteger(i) || i < 0 || i >= storyCards.length) {
    throw new Error(`Story card index out of range: ${index}`);
  }
  const c = storyCards[i];
  if (keys !== undefined) c.keys = String(keys);
  if (entry !== undefined) c.entry = String(entry);
  if (type !== undefined) { c.type = String(type); c.card_type = String(type); }
  if (title !== undefined) c.title = String(title);
  return true;
};

const removeStoryCard = (index) => {
  const i = Number(index);
  if (!Number.isInteger(i) || i < 0 || i >= storyCards.length) {
    throw new Error(`Story card index out of range: ${index}`);
  }
  storyCards.splice(i, 1);
  return true;
};

const sandbox = {
  text: input.text,
  state: input.state && typeof input.state === "object" ? input.state : {},
  info: input.info && typeof input.info === "object" ? input.info : {},
  history: Array.isArray(input.history) ? input.history : [],
  storyCards,
  worldInfo: storyCards,
  quests: Array.isArray(input.quests) ? input.quests : [],
  console: sandboxConsole,
  sandboxConsole,
  log: sandboxConsole.log,
  addStoryCard,
  addWorldEntry: addStoryCard,
  updateStoryCard,
  updateWorldEntry: updateStoryCard,
  removeStoryCard,
  removeWorldEntry: removeStoryCard,
  Math,
  Date,
  JSON,
  Array,
  Object,
  String,
  Number,
  Boolean,
  RegExp,
  Map,
  Set,
  parseInt,
  parseFloat,
  isNaN,
  isFinite,
};

const ctx = vm.createContext(sandbox);

try {
  if (input.library && input.library.trim()) {
    vm.runInContext(input.library, ctx, { timeout: 1500, filename: "library.js" });
  }
  const result = vm.runInContext(input.code, ctx, { timeout: 2000, filename: `${input.hook || "hook"}.js` });

  let outText = sandbox.text;
  let stop = false;
  if (result && typeof result === "object") {
    if ("text" in result) outText = result.text;
    if ("stop" in result) stop = Boolean(result.stop);
  } else if (typeof result === "string") {
    outText = result;
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    text: outText,
    stop,
    state: sandbox.state,
    storyCards: sandbox.storyCards,
    quests: sandbox.quests,
    logs,
  }));
} catch (err) {
  process.stdout.write(JSON.stringify({
    ok: false,
    error: err && err.stack ? String(err.stack).split("\n").slice(0, 4).join("\n") : String(err),
    text: input.text,
    stop: false,
    state: sandbox.state,
    storyCards: sandbox.storyCards,
    quests: sandbox.quests,
    logs,
  }));
}
"""


def run_js_hook(
    *,
    hook: str,
    code: str,
    library: str = "",
    text: str | None = "",
    state: dict[str, Any] | None = None,
    info: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    story_cards: list[dict[str, Any]] | None = None,
    quests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute a single AI Dungeon-compatible JS modifier hook in an isolated Node vm."""
    if not code or not code.strip():
        return {
            "ok": True,
            "text": text,
            "stop": False,
            "state": state if state is not None else {},
            "storyCards": story_cards if story_cards is not None else [],
            "quests": quests if quests is not None else [],
            "logs": [],
        }

    payload = {
        "hook": hook,
        "code": code,
        "library": library or "",
        "text": text,
        "state": state if state is not None else {},
        "info": info if info is not None else {},
        "history": history if history is not None else [],
        "storyCards": story_cards if story_cards is not None else [],
        "quests": quests if quests is not None else [],
    }

    try:
        proc = subprocess.run(
            ["node", "-e", NODE_SANDBOX_SCRIPT],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=3.5,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Script '{hook}' timed out.",
            "text": text,
            "stop": False,
            "state": payload["state"],
            "storyCards": payload["storyCards"],
            "quests": payload["quests"],
            "logs": [f"[error] Script '{hook}' timed out"],
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to execute Node script runner: {e}",
            "text": text,
            "stop": False,
            "state": payload["state"],
            "storyCards": payload["storyCards"],
            "quests": payload["quests"],
            "logs": [f"[error] {e}"],
        }

    if proc.returncode != 0 and not proc.stdout.strip():
        return {
            "ok": False,
            "error": proc.stderr.strip() or f"Node exited with code {proc.returncode}",
            "text": text,
            "stop": False,
            "state": payload["state"],
            "storyCards": payload["storyCards"],
            "quests": payload["quests"],
            "logs": [f"[error] {proc.stderr.strip()}"],
        }

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "error": f"Invalid output from script runner: {e}",
            "text": text,
            "stop": False,
            "state": payload["state"],
            "storyCards": payload["storyCards"],
            "quests": payload["quests"],
            "logs": [f"[error] {e}"],
        }
