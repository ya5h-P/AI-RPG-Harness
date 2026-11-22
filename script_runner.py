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

const initState = input.state && typeof input.state === "object" ? input.state : {};
const hadInitialMemory = Boolean(initState.memory && typeof initState.memory === "object");
if (!hadInitialMemory) {
  initState.memory = {};
}

const makeCompatCard = (raw) => {
  const src = raw && typeof raw === "object" ? raw : {};
  let entryVal = String(src.entry ?? src.value ?? "");
  let typeVal = String(src.type ?? src.card_type ?? "Custom");
  const card = {
    id: String(src.id || Math.random().toString(16).slice(2, 12)),
    title: String(src.title ?? src.keys ?? "Card"),
    keys: String(src.keys ?? ""),
    description: String(src.description ?? ""),
    is_pinned: Boolean(src.is_pinned ?? src.isPinned ?? false),
    isPinned: Boolean(src.isPinned ?? src.is_pinned ?? false),
    use_for_character_creation: Boolean(src.use_for_character_creation ?? src.useForCharacterCreation ?? false),
    useForCharacterCreation: Boolean(src.useForCharacterCreation ?? src.use_for_character_creation ?? false),
    _origEntry: entryVal,
  };
  Object.defineProperty(card, "entry", {
    enumerable: true,
    configurable: true,
    get: () => entryVal,
    set: (v) => { entryVal = String(v ?? ""); },
  });
  Object.defineProperty(card, "value", {
    enumerable: true,
    configurable: true,
    get: () => entryVal,
    set: (v) => { entryVal = String(v ?? ""); },
  });
  Object.defineProperty(card, "type", {
    enumerable: true,
    configurable: true,
    get: () => typeVal,
    set: (v) => { typeVal = String(v ?? "Custom"); },
  });
  Object.defineProperty(card, "card_type", {
    enumerable: true,
    configurable: true,
    get: () => typeVal,
    set: (v) => { typeVal = String(v ?? "Custom"); },
  });
  return card;
};

const serializeCompatCard = (raw) => {
  const src = raw && typeof raw === "object" ? raw : {};
  const orig = typeof src._origEntry === "string" ? src._origEntry : null;
  let entryVal = src.entry;
  if (orig !== null && src.value !== undefined && String(src.value) !== orig && String(src.entry ?? "") === orig) {
    entryVal = String(src.value);
  } else if (entryVal === undefined) {
    entryVal = src.value;
  }
  const typeVal = src.type ?? src.card_type ?? "Custom";
  return {
    id: String(src.id || Math.random().toString(16).slice(2, 12)),
    title: String(src.title ?? src.keys ?? "Card"),
    type: String(typeVal),
    card_type: String(typeVal),
    keys: String(src.keys ?? ""),
    entry: String(entryVal ?? ""),
    value: String(entryVal ?? ""),
    description: String(src.description ?? ""),
    is_pinned: Boolean(src.is_pinned ?? src.isPinned ?? false),
    use_for_character_creation: Boolean(src.use_for_character_creation ?? src.useForCharacterCreation ?? false),
  };
};

const storyCards = Array.isArray(input.storyCards)
  ? input.storyCards.map(makeCompatCard)
  : [];

const addStoryCard = (keys, entry, type = "Custom", title = "", description = "", options = null) => {
  let opts = options && typeof options === "object" ? options : null;
  let kVal = keys;
  let eVal = entry;
  let tVal = type;
  let tiVal = title;
  let dVal = description;
  if (kVal && typeof kVal === "object" && !Array.isArray(kVal)) {
    opts = kVal;
    kVal = opts.keys ?? "";
    eVal = opts.entry ?? opts.value ?? "";
    tVal = opts.type ?? opts.card_type ?? "Custom";
    tiVal = opts.title ?? "";
    dVal = opts.description ?? "";
  } else if (tVal && typeof tVal === "object") {
    opts = tVal;
    tVal = opts.type ?? "Custom";
  } else if (tiVal && typeof tiVal === "object") {
    opts = tiVal;
    tiVal = opts.title ?? "";
  } else if (dVal && typeof dVal === "object") {
    opts = dVal;
    dVal = opts.description ?? "";
  }
  const kStr = String(kVal || "");
  if (kStr && !opts?.allowDuplicate && storyCards.some((c) => String(c.keys || "") === kStr)) {
    return false;
  }
  const card = makeCompatCard({
    id: Math.random().toString(16).slice(2, 12),
    title: String(tiVal || kStr || "Card"),
    type: String(tVal || "Custom"),
    keys: kStr,
    entry: String(eVal || ""),
    description: String(dVal || ""),
  });
  storyCards.push(card);
  return opts && opts.returnCard ? card : storyCards.length - 1;
};

const updateStoryCard = (index, keys, entry, type, title, description) => {
  const i = Number(index);
  if (!Number.isInteger(i) || i < 0 || i >= storyCards.length) {
    throw new Error(`Story card index out of range: ${index}`);
  }
  const c = storyCards[i];
  if (keys && typeof keys === "object" && !Array.isArray(keys)) {
    const patch = keys;
    if (patch.keys !== undefined) c.keys = String(patch.keys);
    if (patch.entry !== undefined) c.entry = String(patch.entry);
    else if (patch.value !== undefined) c.value = String(patch.value);
    if (patch.type !== undefined) c.type = String(patch.type);
    else if (patch.card_type !== undefined) c.type = String(patch.card_type);
    if (patch.title !== undefined) c.title = String(patch.title);
    if (patch.description !== undefined) c.description = String(patch.description);
    return true;
  }
  if (keys !== undefined) c.keys = String(keys);
  if (entry !== undefined) c.entry = String(entry);
  if (type !== undefined) c.type = String(type);
  if (title !== undefined) c.title = String(title);
  if (description !== undefined) c.description = String(description);
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
  stop: Boolean(input.stop),
  state: initState,
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
  encodeURIComponent,
  decodeURIComponent,
  encodeURI,
  decodeURI,
};

const ctx = vm.createContext(sandbox);

try {
  if (input.library && input.library.trim()) {
    vm.runInContext(input.library, ctx, { timeout: 2500, filename: "library.js" });
  }
  const result = vm.runInContext(input.code, ctx, { timeout: 3000, filename: `${input.hook || "hook"}.js` });

  let outText = sandbox.text;
  let stop = Boolean(sandbox.stop);
  if (result && typeof result === "object") {
    if ("text" in result) outText = result.text;
    if ("stop" in result) stop = Boolean(result.stop);
  } else if (typeof result === "string") {
    outText = result;
  }

  if (!hadInitialMemory && sandbox.state && typeof sandbox.state.memory === "object" && Object.keys(sandbox.state.memory).length === 0) {
    delete sandbox.state.memory;
  }

  process.stdout.write(JSON.stringify({
    ok: true,
    text: outText,
    stop,
    state: sandbox.state,
    storyCards: Array.isArray(sandbox.storyCards) ? sandbox.storyCards.map(serializeCompatCard) : [],
    quests: sandbox.quests,
    logs,
  }));
} catch (err) {
  if (!hadInitialMemory && sandbox.state && typeof sandbox.state.memory === "object" && Object.keys(sandbox.state.memory).length === 0) {
    delete sandbox.state.memory;
  }
  process.stdout.write(JSON.stringify({
    ok: false,
    error: err && err.stack ? String(err.stack).split("\n").slice(0, 4).join("\n") : String(err),
    text: input.text,
    stop: false,
    state: sandbox.state,
    storyCards: Array.isArray(sandbox.storyCards) ? sandbox.storyCards.map(serializeCompatCard) : [],
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
            timeout=6.0,
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
