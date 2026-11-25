from __future__ import annotations

import io
import json
import math
import os
import random
import re
import subprocess
import time
import urllib.request
import uuid
import zipfile
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from script_runner import run_js_hook

STORIES_DIR = Path(__file__).parent / "stories"
SCENARIOS_DIR = Path(__file__).parent / "scenarios"
SCRIPTS_DIR = Path(__file__).parent / "scripts"

DEFAULT_AI_INSTRUCTIONS = (
    "You are an AI Game Master providing an immersive, interactive RPG experience.\n"
    "Follow these instructions:\n"
    "- Write in second-person present tense (\"You...\") unless Third Person mode is active.\n"
    "- Continue the story seamlessly right from the latest event, dialogue, action, or inline story text.\n"
    "- Never repeat, summarize, or rephrase the player's last input—jump straight into the world's reaction and consequences.\n"
    "- Never control or decide the player character's future dialogue or choices; let the player act next.\n"
    "- Keep NPCs distinct, consistent, and reactive. Maintain physical continuity, inventory, and scene details.\n"
    "- Aim for vivid, grounded prose (1 to 3 paragraphs per turn unless the moment calls for brevity).\n"
    "- Output only the narrative continuation—no out-of-character notes, meta-commentary, or markdown headers."
)
DEFAULT_SYSTEM_PROMPT = DEFAULT_AI_INSTRUCTIONS

STARTER_SCENARIOS: list[dict[str, str]] = [
    {
        "id": "tavern",
        "name": "The Rusty Lantern",
        "opening": (
            "Rain hammers against the shuttered windows of The Rusty Lantern. "
            "Inside, a peat fire crackles weakly in the hearth, casting long shadows across rough-hewn tables. "
            "Behind the scarred oak bar, a one-eyed innkeeper polishes a mug with a gray rag while a hooded figure in the far corner watches the door. "
            "An empty wooden bucket sits beside the hearth."
        ),
    },
    {
        "id": "station",
        "name": "Orbital Relay 9",
        "opening": (
            "Amber emergency strobes pulse down the narrow corridor of Orbital Relay 9. "
            "Your boots clank softly against the grated deck as your wrist-lamp cuts through drifting wisps of coolant mist. "
            "Ahead, the airlock to the central ops bay hangs half-open, and a faint, rhythmic tapping echoes from somewhere inside."
        ),
    },
]

VALID_PLAYER_MODES = ("say", "do", "story")


def _convert_first_person_to_second(text: str) -> str:
    """Convert first-person pronouns/verbs in `do` mode into second-person."""
    replacements = [
        (r"\bi['’]m\b", "you're"),
        (r"\bi['’]ve\b", "you've"),
        (r"\bi['’]ll\b", "you'll"),
        (r"\bi['’]d\b", "you'd"),
        (r"\bi\s+am\b", "you are"),
        (r"\bi\s+wasn['’]t\b", "you weren't"),
        (r"\bi\s+was\b", "you were"),
        (r"\bi\b", "you"),
        (r"\bmyself\b", "yourself"),
        (r"\bmine\b", "yours"),
        (r"\bmy\b", "your"),
    ]
    out = text
    for pattern, repl in replacements:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    return out


def format_player_text(
    mode: str,
    raw_text: str,
    third_person: bool = False,
    character_name: str = "",
) -> str:
    """Format player input according to one of the 3 RPG chat modes."""
    text = raw_text.strip()
    if not text:
        return ""

    if mode == "say":
        if len(text) >= 2 and (
            (text.startswith('"') and text.endswith('"'))
            or (text.startswith("'") and text.endswith("'"))
        ):
            text = text[1:-1].strip()
        if third_person:
            name = character_name.strip()
            if name:
                return f'{name} says, "{text}"'
            return f'They say, "{text}"'
        return f'You say, "{text}"'

    if mode == "do":
        if third_person:
            subject = character_name.strip() or "They"
            stripped = re.sub(r"^(?:i|you)\b\s*", "", text, flags=re.IGNORECASE).strip()
            if not stripped:
                stripped = text
            if character_name.strip() and re.match(
                rf"^{re.escape(character_name.strip())}\b", stripped, re.IGNORECASE
            ):
                formatted = character_name.strip() + stripped[len(character_name.strip()):]
            elif not character_name.strip() and re.match(r"^they\b", stripped, re.IGNORECASE):
                formatted = "They" + stripped[4:]
            else:
                if len(stripped) > 1 and stripped[0].isupper() and stripped[1].islower():
                    stripped = stripped[0].lower() + stripped[1:]
                elif len(stripped) == 1 and stripped[0].isupper():
                    stripped = stripped.lower()
                formatted = f"{subject} {stripped}"
            if formatted and formatted[-1] not in '.!?"\'…':
                formatted += "."
            return formatted

        converted = _convert_first_person_to_second(text)
        if re.match(r"^you(?:'|\b)", converted, re.IGNORECASE):
            formatted = "You" + converted[3:]
        elif re.match(r"^your\b", converted, re.IGNORECASE):
            formatted = "Your" + converted[4:]
        else:
            if len(converted) > 1 and converted[0].isupper() and converted[1].islower():
                converted = converted[0].lower() + converted[1:]
            elif len(converted) == 1 and converted[0].isupper():
                converted = converted.lower()
            formatted = f"You {converted}"

        if formatted and formatted[-1] not in '.!?"\'…':
            formatted += "."
        return formatted

    if mode == "story":
        return text

    raise ValueError(f"Unsupported player mode: {mode!r}")


@dataclass
class Segment:
    id: str
    kind: str  # "opening" | "say" | "do" | "story" | "ai"
    text: str
    raw_input: str = ""
    created_at: float = field(default_factory=time.time)
    variants: list[str] = field(default_factory=list)
    variant_idx: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Segment:
        raw_vars = [str(v) for v in (data.get("variants") or []) if str(v).strip()]
        idx = int(data.get("variant_idx", max(0, len(raw_vars) - 1)))
        if raw_vars:
            idx = max(0, min(len(raw_vars) - 1, idx))
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:10]),
            kind=str(data.get("kind") or "story"),
            text=str(data.get("text") or ""),
            raw_input=str(data.get("raw_input") or ""),
            created_at=float(data.get("created_at") or time.time()),
            variants=raw_vars,
            variant_idx=idx,
        )


@dataclass
class StorySettings:
    temperature: float = 0.85
    top_p: float = 0.95
    top_k: int = 64
    max_tokens: int = 320
    repeat_penalty: float = 1.05
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    context_length: int = 16384
    enable_thinking: bool = False
    auto_summarize: bool = False
    memory_bank_enabled: bool = False
    raw_model_output: bool = False
    follow_latest_text: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StorySettings:
        if not data:
            return cls()
        ctx_len = int(data.get("context_length", 16384))
        ctx_len = max(1024, min(98304, ctx_len))
        return cls(
            temperature=float(data.get("temperature", 0.85)),
            top_p=float(data.get("top_p", 0.95)),
            top_k=int(data.get("top_k", 64)),
            max_tokens=int(data.get("max_tokens", 320)),
            repeat_penalty=float(data.get("repeat_penalty", 1.05)),
            presence_penalty=float(data.get("presence_penalty", 0.0)),
            frequency_penalty=float(data.get("frequency_penalty", 0.0)),
            context_length=ctx_len,
            enable_thinking=bool(data.get("enable_thinking", False)),
            auto_summarize=bool(data.get("auto_summarize", False)),
            memory_bank_enabled=bool(data.get("memory_bank_enabled", False)),
            raw_model_output=bool(data.get("raw_model_output", False)),
            follow_latest_text=bool(data.get("follow_latest_text", True)),
        )


def _settings_file() -> Path:
    return STORIES_DIR.parent / "settings.json"


def _read_settings_doc() -> dict[str, Any]:
    p = _settings_file()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_settings_doc(doc: dict[str, Any]) -> None:
    p = _settings_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    tmp.replace(p)


def load_default_settings() -> StorySettings:
    """Load persisted user default AI settings, or defaults if absent."""
    doc = _read_settings_doc()
    return StorySettings.from_dict(doc or None)


def save_default_settings(settings: StorySettings) -> StorySettings:
    """Persist user default AI settings atomically to settings.json (preserving endpoint config)."""
    doc = _read_settings_doc()
    endpoint = doc.get("endpoint")
    new_doc = asdict(settings)
    if isinstance(endpoint, dict):
        new_doc["endpoint"] = endpoint
    _write_settings_doc(new_doc)
    return settings


def default_endpoint_config() -> dict[str, Any]:
    return {
        "llm_url": os.environ.get("LLM_URL", "http://127.0.0.1:8080").strip().rstrip("/") or "http://127.0.0.1:8080",
        "api_key": os.environ.get("LLM_API_KEY", "").strip(),
        "model": os.environ.get("LLM_MODEL", "").strip(),
        "provider_type": "auto",
        "presets": [],
    }


def _normalize_presets(raw_presets: Any) -> list[dict[str, str]]:
    if not isinstance(raw_presets, list):
        return []
    out: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for p in raw_presets[:20]:
        if not isinstance(p, dict):
            continue
        url = str(p.get("llm_url") or "").strip().rstrip("/")
        name = str(p.get("name") or url or "Custom Endpoint").strip()
        if not url:
            continue
        pid = str(p.get("id") or uuid.uuid4().hex[:8])
        if pid in seen_ids:
            pid = uuid.uuid4().hex[:8]
        seen_ids.add(pid)
        ptype = str(p.get("provider_type") or "auto").strip()
        if ptype not in ("auto", "llama_cpp", "openai_compat"):
            ptype = "auto"
        out.append({
            "id": pid,
            "name": name,
            "llm_url": url,
            "model": str(p.get("model") or "").strip(),
            "provider_type": ptype,
            "api_key": str(p.get("api_key") or "").strip(),
        })
    return out


def load_endpoint_config() -> dict[str, Any]:
    """Load active LLM endpoint & saved presets from settings.json (with env fallbacks)."""
    base = default_endpoint_config()
    doc = _read_settings_doc()
    raw = doc.get("endpoint") if isinstance(doc.get("endpoint"), dict) else {}
    url = str(raw.get("llm_url") or base["llm_url"]).strip().rstrip("/")
    ptype = str(raw.get("provider_type") or base["provider_type"]).strip()
    if ptype not in ("auto", "llama_cpp", "openai_compat"):
        ptype = "auto"
    return {
        "llm_url": url or base["llm_url"],
        "api_key": str(raw.get("api_key") if "api_key" in raw else base["api_key"]).strip(),
        "model": str(raw.get("model") if "model" in raw else base["model"]).strip(),
        "provider_type": ptype,
        "presets": _normalize_presets(raw.get("presets")),
    }


def save_endpoint_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Persist active LLM endpoint & saved presets atomically to settings.json."""
    cur = load_endpoint_config()
    presets = _normalize_presets(cfg["presets"]) if "presets" in cfg else list(cur["presets"])

    delete_id = str(cfg.get("delete_preset_id") or "").strip()
    if delete_id:
        presets = [p for p in presets if p["id"] != delete_id]

    activate_id = str(cfg.get("activate_preset_id") or "").strip()
    if activate_id:
        match = next((p for p in presets if p["id"] == activate_id), None)
        if match:
            cfg = {
                **cfg,
                "llm_url": match["llm_url"],
                "model": match["model"],
                "provider_type": match["provider_type"],
                "api_key": match["api_key"],
                "clear_api_key": not bool(match["api_key"]),
            }

    url = str(cfg.get("llm_url") or cur["llm_url"]).strip().rstrip("/") or cur["llm_url"]
    ptype = str(cfg.get("provider_type") or cur["provider_type"]).strip()
    if ptype not in ("auto", "llama_cpp", "openai_compat"):
        ptype = "auto"
    if cfg.get("clear_api_key"):
        api_key = ""
    elif "api_key" in cfg and str(cfg["api_key"]).strip():
        api_key = str(cfg["api_key"]).strip()
    else:
        api_key = cur["api_key"]
    model = str(cfg["model"]).strip() if "model" in cfg else cur["model"]

    preset_name = str(cfg.get("save_preset_name") or "").strip()
    if preset_name:
        existing = next((p for p in presets if p["name"].lower() == preset_name.lower()), None)
        entry = {
            "id": existing["id"] if existing else uuid.uuid4().hex[:8],
            "name": preset_name,
            "llm_url": url,
            "model": model,
            "provider_type": ptype,
            "api_key": api_key,
        }
        if existing:
            presets = [entry if p["id"] == existing["id"] else p for p in presets]
        else:
            presets.append(entry)

    saved = {
        "llm_url": url,
        "api_key": api_key,
        "model": model,
        "provider_type": ptype,
        "presets": presets,
    }
    doc = _read_settings_doc()
    doc["endpoint"] = saved
    _write_settings_doc(doc)
    return saved


def public_endpoint_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return UI-safe endpoint config with API keys masked."""
    def mask(k: str) -> str:
        if not k:
            return ""
        if len(k) <= 8:
            return "•" * len(k)
        return f"{k[:4]}…{k[-4:]}"

    return {
        "llm_url": cfg.get("llm_url", ""),
        "model": cfg.get("model", ""),
        "provider_type": cfg.get("provider_type", "auto"),
        "has_api_key": bool(cfg.get("api_key")),
        "api_key_preview": mask(str(cfg.get("api_key") or "")),
        "presets": [
            {
                "id": p["id"],
                "name": p["name"],
                "llm_url": p["llm_url"],
                "model": p["model"],
                "provider_type": p["provider_type"],
                "has_api_key": bool(p.get("api_key")),
            }
            for p in (cfg.get("presets") or [])
        ],
    }


@dataclass
class MemoryItem:
    id: str
    text: str
    start_idx: int = 0
    end_idx: int = 0
    uses: int = 0
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryItem:
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:10]),
            text=str(data.get("text") or ""),
            start_idx=int(data.get("start_idx", 0)),
            end_idx=int(data.get("end_idx", 0)),
            uses=int(data.get("uses", 0)),
            created_at=float(data.get("created_at") or time.time()),
        )


@dataclass
class StoryCard:
    id: str
    title: str
    card_type: str = "Custom"
    keys: str = ""  # comma-separated trigger keywords
    entry: str = ""
    description: str = ""
    is_pinned: bool = False
    use_for_character_creation: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryCard:
        entry = data.get("entry")
        if entry is None:
            entry = data.get("value")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:10]),
            title=str(data.get("title") or "Untitled Card"),
            card_type=str(data.get("card_type") or data.get("type") or "Custom"),
            keys=str(data.get("keys") or ""),
            entry=str(entry or ""),
            description=str(data.get("description") or ""),
            is_pinned=bool(data.get("is_pinned", data.get("isPinned", False))),
            use_for_character_creation=bool(
                data.get("use_for_character_creation", data.get("useForCharacterCreation", False))
            ),
        )


def _default_builtin_script() -> dict[str, Any]:
    return {
        "enabled": True,
        "library": "",
        "input": "",
        "context": "",
        "output": "",
    }


def _normalize_builtin_script(data: dict[str, Any] | None) -> dict[str, Any]:
    d = data if isinstance(data, dict) else {}
    return {
        "enabled": bool(d.get("enabled", True)),
        "library": str(d.get("library") or ""),
        "input": str(d.get("input") or ""),
        "context": str(d.get("context") or ""),
        "output": str(d.get("output") or ""),
    }


def _normalize_attached_scripts(items: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in (items or [])[:10]:
        if isinstance(item, dict) and item.get("script_id"):
            out.append({
                "script_id": str(item["script_id"]),
                "enabled": bool(item.get("enabled", True)),
            })
    return out


@dataclass
class Script:
    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    library: str = ""
    input: str = ""
    context: str = ""
    output: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Script:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or "Untitled Script"),
            description=str(data.get("description") or ""),
            version=str(data.get("version") or "1.0"),
            library=str(data.get("library") or ""),
            input=str(data.get("input") or ""),
            context=str(data.get("context") or ""),
            output=str(data.get("output") or ""),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )


def _normalize_choices_tree(items: list[Any] | None, depth: int = 0) -> list[dict[str, Any]]:
    if not isinstance(items, list) or depth > 12:
        return []
    out: list[dict[str, Any]] = []
    for ch in items:
        if not isinstance(ch, dict) or ch.get("deletedAt"):
            continue
        opt_state = ch.get("state") if isinstance(ch.get("state"), dict) else {}
        inst_obj = ch.get("ai_instructions") if ch.get("ai_instructions") is not None else opt_state.get("instructions")
        if isinstance(inst_obj, dict):
            ai_inst = str(inst_obj.get("scenario") or inst_obj.get("text") or "").strip()
        else:
            ai_inst = str(inst_obj or "").strip()
        raw_cards = ch.get("story_cards") or ch.get("storyCards") or []
        norm_cards = [
            asdict(StoryCard.from_dict(c))
            for c in raw_cards
            if isinstance(c, dict) and not c.get("deletedAt")
        ]
        raw_children = ch.get("choices") or ch.get("options") or []
        raw_tp = ch.get("third_person", ch.get("thirdPerson"))
        out.append({
            "id": str(ch.get("id") or ch.get("shortId") or uuid.uuid4().hex[:8]),
            "label": str(ch.get("label") or ch.get("title") or "Option").strip() or "Option",
            "description": str(ch.get("description") or "").strip(),
            "opening": str(ch.get("opening") or ch.get("prompt") or opt_state.get("prompt") or "").strip(),
            "plot_essentials": str(
                ch.get("plot_essentials")
                or ch.get("plotEssentials")
                or opt_state.get("plotEssentials")
                or opt_state.get("memory")
                or ""
            ).strip(),
            "ai_instructions": ai_inst,
            "story_summary": str(ch.get("story_summary") or opt_state.get("storySummary") or "").strip(),
            "authors_note": str(ch.get("authors_note") or ch.get("authorsNote") or opt_state.get("authorsNote") or "").strip(),
            "third_person": bool(raw_tp) if raw_tp is not None else None,
            "character_name": str(ch.get("character_name") or "").strip(),
            "story_cards": norm_cards,
            "builtin_script": _normalize_builtin_script(ch.get("builtin_script")),
            "attached_scripts": _normalize_attached_scripts(ch.get("attached_scripts")),
            "choices": _normalize_choices_tree(raw_children, depth + 1),
        })
    return out


def _find_choice_path_by_id(nodes: list[dict[str, Any]], target_id: str) -> list[dict[str, Any]] | None:
    for node in nodes:
        if node.get("id") == target_id:
            return [node]
        sub = _find_choice_path_by_id(node.get("choices") or [], target_id)
        if sub is not None:
            return [node] + sub
    return None


def _resolve_choice_chain(
    root_choices: list[dict[str, Any]],
    choice_path: list[str] | None = None,
    choice_id: str | None = None,
) -> list[dict[str, Any]]:
    if not root_choices:
        return []
    chain: list[dict[str, Any]] = []
    if choice_path:
        pool = root_choices
        for cid in choice_path:
            if not pool:
                break
            match = next((c for c in pool if c.get("id") == cid), None)
            if match is None:
                break
            chain.append(match)
            pool = match.get("choices") or []
    elif choice_id:
        found = _find_choice_path_by_id(root_choices, choice_id)
        if found:
            chain = found

    if not chain:
        chain = [root_choices[0]]

    # Descend to a leaf if the caller stopped at a branch node that has child options.
    while chain[-1].get("choices"):
        chain.append(chain[-1]["choices"][0])
    return chain


@dataclass
class Scenario:
    id: str
    name: str
    description: str = ""
    scenario_type: str = "story"  # "story" | "multiple_choice" | "character_creator"
    opening: str = ""
    choices: list[dict[str, Any]] = field(default_factory=list)
    ai_instructions: str = ""
    story_summary: str = ""
    plot_essentials: str = ""
    authors_note: str = ""
    third_person: bool = False
    character_name: str = ""
    story_cards: list[StoryCard] = field(default_factory=list)
    builtin_script: dict[str, Any] = field(default_factory=_default_builtin_script)
    attached_scripts: list[dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "story_cards": [asdict(c) for c in self.story_cards],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scenario:
        stype = str(data.get("scenario_type") or "story")
        if stype not in ("story", "multiple_choice", "character_creator"):
            stype = "story"
        choices = _normalize_choices_tree(data.get("choices") or [])
        return cls(
            id=str(data["id"]),
            name=str(data.get("name") or data.get("title") or "Untitled Scenario"),
            description=str(data.get("description") or ""),
            scenario_type=stype,
            opening=str(data.get("opening") or ""),
            choices=choices,
            ai_instructions=str(data.get("ai_instructions") or ""),
            story_summary=str(data.get("story_summary") or ""),
            plot_essentials=str(data.get("plot_essentials") or ""),
            authors_note=str(data.get("authors_note") or ""),
            third_person=bool(data.get("third_person", False)),
            character_name=str(data.get("character_name") or ""),
            story_cards=[StoryCard.from_dict(c) for c in data.get("story_cards", [])],
            builtin_script=_normalize_builtin_script(data.get("builtin_script")),
            attached_scripts=_normalize_attached_scripts(data.get("attached_scripts")),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )


@dataclass
class Story:
    id: str
    title: str
    scenario_id: str = ""
    description: str = ""
    world_description: str = ""
    tags: list[str] = field(default_factory=list)
    ai_instructions: str = DEFAULT_AI_INSTRUCTIONS
    story_summary: str = ""
    plot_essentials: str = ""
    authors_note: str = ""
    third_person: bool = False
    character_name: str = ""
    story_cards: list[StoryCard] = field(default_factory=list)
    memories: list[MemoryItem] = field(default_factory=list)
    last_summarized_count: int = 0
    last_memory_bank_count: int = 0
    builtin_script: dict[str, Any] = field(default_factory=_default_builtin_script)
    attached_scripts: list[dict[str, Any]] = field(default_factory=list)
    script_state: dict[str, Any] = field(default_factory=dict)
    dismissed_script_message: str | None = None
    quests: list[dict[str, Any]] = field(default_factory=list)
    script_logs: list[str] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    undo_stack: list[list[dict[str, Any]]] = field(default_factory=list)
    redo_stack: list[list[dict[str, Any]]] = field(default_factory=list)
    last_generation_context: dict[str, Any] | None = None
    settings: StorySettings = field(default_factory=StorySettings)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "scenario_id": self.scenario_id,
            "description": self.description,
            "world_description": self.world_description,
            "tags": self.tags,
            "ai_instructions": self.ai_instructions,
            "story_summary": self.story_summary,
            "plot_essentials": self.plot_essentials,
            "authors_note": self.authors_note,
            "third_person": self.third_person,
            "character_name": self.character_name,
            "story_cards": [asdict(c) for c in self.story_cards],
            "memories": [asdict(m) for m in self.memories],
            "last_summarized_count": self.last_summarized_count,
            "last_memory_bank_count": self.last_memory_bank_count,
            "builtin_script": self.builtin_script,
            "attached_scripts": self.attached_scripts,
            "script_state": self.script_state,
            "dismissed_script_message": self.dismissed_script_message,
            "quests": self.quests,
            "script_logs": self.script_logs,
            "segments": [asdict(seg) for seg in self.segments],
            "undo_stack": self.undo_stack,
            "redo_stack": self.redo_stack,
            "last_generation_context": self.last_generation_context,
            "settings": asdict(self.settings),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Story:
        ai_instructions = data.get("ai_instructions")
        if ai_instructions is None:
            ai_instructions = data.get("system_prompt")
        plot_essentials = data.get("plot_essentials")
        if plot_essentials is None:
            plot_essentials = data.get("memory")
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or "Untitled Adventure"),
            scenario_id=str(data.get("scenario_id") or ""),
            description=str(data.get("description") or ""),
            world_description=str(data.get("world_description") or ""),
            tags=[str(t) for t in (data.get("tags") or []) if str(t).strip()],
            ai_instructions=str(ai_instructions if ai_instructions is not None else DEFAULT_AI_INSTRUCTIONS),
            story_summary=str(data.get("story_summary") or ""),
            plot_essentials=str(plot_essentials or ""),
            authors_note=str(data.get("authors_note") or ""),
            third_person=bool(data.get("third_person", False)),
            character_name=str(data.get("character_name") or ""),
            story_cards=[StoryCard.from_dict(c) for c in data.get("story_cards", [])],
            memories=[MemoryItem.from_dict(m) for m in data.get("memories", [])],
            last_summarized_count=int(data.get("last_summarized_count", 0)),
            last_memory_bank_count=int(data.get("last_memory_bank_count", 0)),
            builtin_script=_normalize_builtin_script(data.get("builtin_script")),
            attached_scripts=_normalize_attached_scripts(data.get("attached_scripts")),
            script_state=dict(data.get("script_state") or {}),
            dismissed_script_message=(
                str(data["dismissed_script_message"])
                if data.get("dismissed_script_message") is not None
                else None
            ),
            quests=list(data.get("quests") or []),
            script_logs=list(data.get("script_logs") or [])[-60:],
            segments=[Segment.from_dict(s) for s in data.get("segments", [])],
            undo_stack=list(data.get("undo_stack") or [])[-25:],
            redo_stack=list(data.get("redo_stack") or [])[-25:],
            last_generation_context=(
                data.get("last_generation_context")
                if isinstance(data.get("last_generation_context"), dict)
                else None
            ),
            settings=StorySettings.from_dict(data.get("settings")),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
        )


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def _trim_to_token_budget(text: str, budget_tokens: int) -> str:
    if budget_tokens <= 0:
        return ""
    if estimate_tokens(text) <= budget_tokens:
        return text
    max_chars = budget_tokens * 4
    return text[:max_chars].rstrip()


def trim_incomplete_sentence(text: str) -> str:
    """Trim trailing partial sentence fragment when generation ends mid-sentence."""
    s = text.strip()
    if not s or s[-1] in '.!?"\'…\n':
        return s
    last_end = max(s.rfind("."), s.rfind("!"), s.rfind("?"), s.rfind("…"), s.rfind("\n"))
    if last_end > len(s) // 4:
        return s[: last_end + 1].strip()
    return s


def _extract_continuation_tail(text: str, max_chars: int = 220) -> str:
    """Return the trailing excerpt of an AI segment for anchored inline continuation."""
    s = (text or "").strip()
    if not s:
        return ""
    if len(s) <= max_chars:
        return s
    tail = s[-max_chars:]
    space_idx = tail.find(" ")
    if 0 <= space_idx < len(tail) - 20:
        tail = tail[space_idx + 1 :]
    return f"...{tail.lstrip()}"


def _has_incomplete_tail(text: str) -> bool:
    """Return True if `text` ends mid-sentence, with an ellipsis, or with an unclosed quote."""
    prev = (text or "").rstrip()
    if not prev:
        return False
    # Trailing ellipsis (... or …) is an interrupted beat, not a finished paragraph.
    if prev.endswith("...") or prev.endswith("…"):
        return True
    last_para = prev.rsplit("\n", 1)[-1]
    if last_para.count('"') % 2 == 1:
        return True
    if last_para.count("\u201c") > last_para.count("\u201d"):
        return True
    last_char = prev[-1]
    if last_char in "—–-,;:(":
        return True
    ended_sentence = last_char in ".!?" or (
        len(prev) >= 2 and last_char in '"\u201d\'\u2019)' and prev[-2] in ".!?"
    )
    return not ended_sentence


def join_ai_continuation(prev_text: str, addition: str) -> str:
    """Join a newly generated continuation smoothly onto an existing AI segment."""
    prev = (prev_text or "").rstrip()
    add = (addition or "").lstrip()
    if not prev:
        return add
    if not add:
        return prev

    # Mid-word / punctuation-attached continuation needs no extra whitespace.
    if add[0] in ",.;:!?\")'\u201d\u2019)]":
        return prev + add
    if prev[-1] in "—–-\u201c":
        return prev + add

    if _has_incomplete_tail(prev) or add[0].islower():
        return f"{prev} {add}"

    return f"{prev}\n\n{add}"


def _strip_suffix_prefix_overlap(text: str, prev_text: str) -> tuple[str, str]:
    """Strip overlapping suffix-prefix clauses or echoed trailing dialogue from `text`."""
    s = text.strip()
    prev = (prev_text or "").strip()
    if not s or not prev:
        return s, ""

    incomplete_tail = _has_incomplete_tail(prev)

    # 0. Direct suffix-prefix character overlap (e.g. `"You are...` echoed at start of continuation).
    max_char_ov = min(220, len(prev), len(s) - 1)
    s_lower = s.lower()
    prev_lower = prev.lower()
    min_char_ov = 6 if incomplete_tail else 16
    for ln in range(max_char_ov, min_char_ov - 1, -1):
        # Require match to start on a clean boundary in `prev` (start, whitespace, or quote/punct).
        start_idx = len(prev) - ln
        if start_idx > 0 and prev[start_idx - 1].isalnum():
            continue
        if prev_lower[start_idx:] == s_lower[:ln]:
            cut = ln
            while cut < len(s) and s[cut] in '.…,:;"\'\u201d\u2019)]' and prev[-1] in '.…':
                cut += 1
            remainder = s[cut:].lstrip()
            if remainder:
                return remainder, s[:cut].strip()

    # 1. Word-level suffix-prefix overlap (e.g. model re-emits trailing words, even 2+ on interrupted beats).
    prev_tail = prev[-500:]
    prev_words = [m.group(0).lower() for m in re.finditer(r"[a-z0-9'\u2019]+", prev_tail, re.IGNORECASE)]
    gen_matches = list(re.finditer(r"[a-z0-9'\u2019]+", s[:500], re.IGNORECASE))
    min_k = 2 if incomplete_tail else 4
    min_chars = 6 if incomplete_tail else 16
    if prev_words and len(gen_matches) > 1:
        max_k = min(24, len(prev_words), len(gen_matches) - 1)
        for k in range(max_k, min_k - 1, -1):
            gen_slice = [m.group(0).lower() for m in gen_matches[:k]]
            if prev_words[-k:] == gen_slice:
                overlap_str = " ".join(gen_slice)
                if len(overlap_str) >= min_chars:
                    cut_end = gen_matches[k - 1].end()
                    while cut_end < len(s) and s[cut_end] in '.!?,;:"\'\u201d\u2019)]…':
                        cut_end += 1
                    remainder = s[cut_end:].lstrip()
                    if remainder:
                        return remainder, s[:cut_end].strip()

    # 2. Echoed trailing quoted dialogue (with optional short speaker attribution).
    quotes = list(re.finditer(r'["\u201c]([^"\u201d\n]{12,240})["\u201d]', prev_tail))
    if quotes:
        last_q_norm = re.sub(r"\W+", " ", quotes[-1].group(1)).strip().lower()
        if len(last_q_norm) >= 12:
            lead_m = re.match(
                r'^(?:[^"\u201c\n]{0,45}?)?["\u201c]([^"\u201d\n]{12,240})["\u201d](?:\s*[,.!?]?\s*)',
                s,
            )
            if lead_m:
                lead_q_norm = re.sub(r"\W+", " ", lead_m.group(1)).strip().lower()
                if lead_q_norm == last_q_norm:
                    remainder = s[lead_m.end():].lstrip()
                    if remainder:
                        return remainder, s[:lead_m.end()].strip()

    return s, ""


def remove_repeated_leading_sentences(
    generated_text: str,
    recent_texts: list[str],
) -> tuple[str, list[str]]:
    """
    Strip leading sentences or suffix-prefix dialogue overlap from AI output that
    duplicates the recent story tail (matching AI Dungeon's 'Remove repeated sentences' default).
    """
    text = generated_text.strip()
    if not text or not recent_texts:
        return text, []

    sent_split_re = r"(?<=[.!?…])\s+|(?<=[.!?…][\"'\u201d\u2019)])\s+"
    recent_norm: set[str] = set()
    for block in recent_texts[-4:]:
        for sent in re.split(sent_split_re + r"|\n+", block.strip()):
            norm = re.sub(r"\W+", " ", sent).strip().lower()
            if len(norm) >= 8:
                recent_norm.add(norm)

    removed: list[str] = []
    if recent_norm:
        sentences = re.split(sent_split_re, text)
        if len(sentences) > 1:
            idx = 0
            while idx < len(sentences) - 1:
                norm = re.sub(r"\W+", " ", sentences[idx]).strip().lower()
                if norm and norm in recent_norm:
                    removed.append(sentences[idx])
                    idx += 1
                else:
                    break
            if removed:
                text = " ".join(sentences[idx:]).strip()

    stripped, overlap_removed = _strip_suffix_prefix_overlap(text, recent_texts[-1])
    if overlap_removed:
        removed.append(overlap_removed)
        text = stripped

    return text, removed


def _tokenize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def rank_memories(memories: list[MemoryItem], query_text: str) -> list[tuple[MemoryItem, float]]:
    """Rank Memory Bank items by TF-IDF cosine similarity against query_text."""
    if not memories:
        return []
    query_tokens = _tokenize_words(query_text)
    if not query_tokens:
        return [(m, 0.0) for m in reversed(memories)]

    docs = [_tokenize_words(m.text) for m in memories]
    n_docs = len(docs)
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))

    def tfidf_vec(tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for tok, cnt in tf.items():
            idf = math.log((n_docs + 1) / (df.get(tok, 0) + 1)) + 1.0
            vec[tok] = cnt * idf
        return vec

    q_vec = tfidf_vec(query_tokens)
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

    scored: list[tuple[MemoryItem, float]] = []
    for m, d_toks in zip(memories, docs):
        d_vec = tfidf_vec(d_toks)
        d_norm = math.sqrt(sum(v * v for v in d_vec.values())) or 1.0
        dot = sum(q_vec[k] * d_vec.get(k, 0.0) for k in q_vec)
        score = dot / (q_norm * d_norm)
        scored.append((m, round(score, 4)))

    scored.sort(key=lambda item: (item[1], item[0].created_at), reverse=True)
    return scored


def find_triggered_story_cards(
    story: Story,
    scan_segments: int = 4,
    card_budget_tokens: int | None = None,
) -> list[StoryCard]:
    """
    Return pinned Story Cards and keyword-matched cards prioritized by recency
    and frequency, optionally bounded by card_budget_tokens.
    """
    if not story.story_cards:
        return []
    if card_budget_tokens is not None and card_budget_tokens > 500:
        scan_segments = max(scan_segments, card_budget_tokens // 100)

    scan_texts = [seg.text for seg in story.segments[-scan_segments:]] if story.segments else []
    if not scan_texts and story.world_description.strip():
        scan_texts = [story.world_description]
    scored_cards: list[tuple[int, int, int, StoryCard]] = []

    for idx, card in enumerate(story.story_cards):
        if not card.entry.strip():
            continue
        if card.is_pinned:
            scored_cards.append((2, 10**6, -idx, card))
            continue
        if not scan_texts or not card.keys.strip():
            continue
        keywords = [k.strip() for k in card.keys.split(",") if k.strip()]
        latest_seg = -1
        hit_count = 0
        for seg_pos, txt in enumerate(scan_texts):
            for kw in keywords:
                hits = len(re.findall(rf"(?<!\w){re.escape(kw)}(?!\w)", txt, re.IGNORECASE))
                if hits > 0:
                    hit_count += hits
                    latest_seg = max(latest_seg, seg_pos)
        if hit_count > 0:
            scored_cards.append((1, latest_seg * 100 + hit_count, -idx, card))

    scored_cards.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)

    selected: list[StoryCard] = []
    used_tokens = 0
    for _, _, _, card in scored_cards:
        toks = estimate_tokens(card.entry.strip())
        if card_budget_tokens is not None and selected and used_tokens + toks > card_budget_tokens:
            continue
        if card_budget_tokens is not None and not selected and toks > card_budget_tokens:
            continue
        selected.append(card)
        used_tokens += toks
    return selected


def push_undo_snapshot(story: Story) -> None:
    snap = [asdict(s) for s in story.segments]
    story.undo_stack.append(snap)
    story.undo_stack = story.undo_stack[-25:]
    story.redo_stack = []


def undo_story(story: Story) -> bool:
    if story.undo_stack:
        story.redo_stack.append([asdict(s) for s in story.segments])
        story.redo_stack = story.redo_stack[-25:]
        prev = story.undo_stack.pop()
        story.segments = [Segment.from_dict(s) for s in prev]
        return True
    if story.segments and not (len(story.segments) == 1 and story.segments[0].kind == "opening"):
        story.redo_stack.append([asdict(s) for s in story.segments])
        story.redo_stack = story.redo_stack[-25:]
        story.segments.pop()
        return True
    return False


def redo_story(story: Story) -> bool:
    if not story.redo_stack:
        return False
    story.undo_stack.append([asdict(s) for s in story.segments])
    story.undo_stack = story.undo_stack[-25:]
    nxt = story.redo_stack.pop()
    story.segments = [Segment.from_dict(s) for s in nxt]
    return True


def erase_last_segment(story: Story) -> bool:
    if not story.segments or (len(story.segments) == 1 and story.segments[0].kind == "opening"):
        return False
    push_undo_snapshot(story)
    story.segments.pop()
    return True


def cycle_retry_variant(
    story: Story,
    direction: int = 1,
    variant_idx: int | None = None,
) -> bool:
    if not story.segments or story.segments[-1].kind != "ai":
        return False
    seg = story.segments[-1]
    if len(seg.variants) <= 1:
        return False
    if variant_idx is not None:
        new_idx = max(0, min(len(seg.variants) - 1, int(variant_idx)))
        if new_idx == seg.variant_idx:
            return False
    else:
        new_idx = (seg.variant_idx + (1 if direction >= 0 else -1)) % len(seg.variants)
    push_undo_snapshot(story)
    seg.variant_idx = new_idx
    seg.text = seg.variants[new_idx]
    return True


def erase_to_here(story: Story, seg_id: str) -> int:
    idx = next((i for i, s in enumerate(story.segments) if s.id == seg_id), -1)
    if idx < 0:
        return 0
    push_undo_snapshot(story)
    # Keep fixed opening if user triggered erase-to-here on the opening segment itself.
    cut_idx = 1 if (idx == 0 and story.segments[0].kind == "opening") else idx
    erased = len(story.segments) - cut_idx
    if erased <= 0:
        story.undo_stack.pop()
        return 0
    story.segments = story.segments[:cut_idx]
    return erased


def export_story_cards_aidungeon(story: Story) -> list[dict[str, Any]]:
    return [
        {
            "keys": c.keys,
            "value": c.entry,
            "type": c.card_type,
            "title": c.title,
            "description": c.description,
            "isPinned": c.is_pinned,
            "useForCharacterCreation": c.use_for_character_creation,
        }
        for c in story.story_cards
    ]


def import_story_cards_aidungeon(story: Story, raw_cards: list[Any]) -> dict[str, int]:
    """Replace story's Story Cards with an imported array, deduplicating exact (keys, value)."""
    seen: set[tuple[str, str]] = set()
    imported: list[StoryCard] = []
    skipped = 0
    duplicates = 0
    for item in raw_cards:
        if not isinstance(item, dict):
            skipped += 1
            continue
        keys = str(item.get("keys") or "").strip()
        val = str(item.get("value") if item.get("value") is not None else (item.get("entry") or "")).strip()
        if not keys or not val:
            skipped += 1
            continue
        sig = (keys, val)
        if sig in seen:
            duplicates += 1
            continue
        seen.add(sig)
        imported.append(StoryCard.from_dict(item))
    story.story_cards = imported
    return {"imported": len(imported), "duplicates": duplicates, "skipped": skipped}


def export_adventure_zip(story: Story) -> bytes:
    buf = io.BytesIO()
    transcript = "\n\n".join(s.text for s in story.segments if s.text.strip())
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("story.txt", transcript)
        zf.writestr("adventure.json", json.dumps(story.to_dict(), indent=2))
        zf.writestr("story_cards.json", json.dumps(export_story_cards_aidungeon(story), indent=2))
    return buf.getvalue()


def _effective_plot_essentials(story: Story) -> str:
    mem_obj = story.script_state.get("memory")
    if isinstance(mem_obj, dict) and isinstance(mem_obj.get("context"), str) and mem_obj["context"].strip():
        return mem_obj["context"].strip()
    return story.plot_essentials.strip()


def _effective_authors_note(story: Story) -> str:
    mem_obj = story.script_state.get("memory")
    if isinstance(mem_obj, dict) and isinstance(mem_obj.get("authorsNote"), str) and mem_obj["authorsNote"].strip():
        return mem_obj["authorsNote"].strip()
    return story.authors_note.strip()


def _effective_front_memory(story: Story) -> str:
    mem_obj = story.script_state.get("memory")
    if isinstance(mem_obj, dict) and isinstance(mem_obj.get("frontMemory"), str) and mem_obj["frontMemory"].strip():
        return mem_obj["frontMemory"].strip()
    return ""


def _active_scripts_for_story(story: Story) -> list[dict[str, str]]:
    """Collect active scripts (builtin + attached in order) for execution."""
    active: list[dict[str, str]] = []
    if story.builtin_script.get("enabled", True):
        b = story.builtin_script
        if any(str(b.get(k) or "").strip() for k in ("input", "context", "output")):
            active.append({
                "name": "Built-in Script",
                "library": str(b.get("library") or ""),
                "input": str(b.get("input") or ""),
                "context": str(b.get("context") or ""),
                "output": str(b.get("output") or ""),
            })
    for entry in story.attached_scripts:
        if not entry.get("enabled", True):
            continue
        sc = load_script(str(entry.get("script_id") or ""))
        if sc is not None:
            active.append({
                "name": sc.name,
                "library": sc.library,
                "input": sc.input,
                "context": sc.context,
                "output": sc.output,
            })
    return active


def run_story_scripts(
    story: Story,
    hook: str,
    text: str | None,
    extra_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all active scripts for a hook (`input` | `context` | `output`) in order."""
    scripts = _active_scripts_for_story(story)
    current_text = text
    stopped = False
    all_logs: list[str] = []
    all_errors: list[str] = []

    if not any(s.get(hook, "").strip() for s in scripts):
        return {"text": current_text, "stop": False, "logs": [], "errors": []}

    history_payload = [
        {
            "text": seg.text,
            "rawText": seg.raw_input or seg.text,
            "type": (
                "continue"
                if seg.kind == "ai"
                else ("start" if seg.kind == "opening" else seg.kind)
            ),
            "rawKind": seg.kind,
        }
        for seg in story.segments
    ]
    cards_payload = [
        {
            "id": c.id,
            "title": c.title,
            "type": c.card_type,
            "card_type": c.card_type,
            "keys": c.keys,
            "entry": c.entry,
            "value": c.entry,
            "description": c.description,
            "is_pinned": c.is_pinned,
            "isPinned": c.is_pinned,
            "use_for_character_creation": c.use_for_character_creation,
            "useForCharacterCreation": c.use_for_character_creation,
        }
        for c in story.story_cards
    ]
    ctx_limit = max(1024, min(98304, int(story.settings.context_length or 16384)))
    info_payload = {
        "actionCount": len(story.segments),
        "characterName": story.character_name,
        "characterNames": [story.character_name] if story.character_name.strip() else [],
        "thirdPerson": story.third_person,
        "memoryLength": len(_effective_plot_essentials(story)),
        "maxChars": ctx_limit * 4,
        "title": story.title,
        **(extra_info or {}),
    }

    for sc in scripts:
        code = sc.get(hook, "").strip()
        if not code:
            continue
        res = run_js_hook(
            hook=hook,
            code=code,
            library=sc.get("library", ""),
            text=current_text,
            state=story.script_state,
            info=info_payload,
            history=history_payload,
            story_cards=cards_payload,
            quests=story.quests,
        )
        story.script_state = res.get("state") if isinstance(res.get("state"), dict) else story.script_state
        if isinstance(res.get("quests"), list):
            story.quests = res["quests"]
        if isinstance(res.get("storyCards"), list):
            cards_payload = res["storyCards"]
            story.story_cards = [StoryCard.from_dict(c) for c in cards_payload]

        for line in res.get("logs") or []:
            entry_line = f"[{sc['name']}/{hook}] {line}"
            all_logs.append(entry_line)
            story.script_logs.append(entry_line)

        if not res.get("ok", True) and res.get("error"):
            err_line = f"[{sc['name']}/{hook}] ERROR: {res['error']}"
            all_errors.append(err_line)
            story.script_logs.append(err_line)
        else:
            current_text = res.get("text")
            if res.get("stop"):
                stopped = True
                break

    story.script_logs = story.script_logs[-60:]
    return {
        "text": current_text,
        "stop": stopped,
        "logs": all_logs,
        "errors": all_errors,
    }


def build_context_plan(
    story: Story,
    apply_context_scripts: bool = False,
    bump_memory_uses: bool = False,
    guide_text: str = "",
    retry_instructions: str = "",
    previous_draft: str = "",
) -> dict[str, Any]:
    """
    Build the prompt messages and full Context Viewer breakdown following
    AI Dungeon's Required (70% max) vs Dynamic (Story Cards, Memory Bank, History)
    context priority rules.
    """
    ctx_limit = max(1024, min(98304, int(story.settings.context_length or 16384)))
    req_cap = int(ctx_limit * 0.70)

    raw_instructions = story.ai_instructions.strip() or DEFAULT_AI_INSTRUCTIONS
    raw_summary = story.story_summary.strip()
    raw_plot = _effective_plot_essentials(story)
    raw_authors = _effective_authors_note(story)
    raw_front = _effective_front_memory(story)
    last_seg_text = story.segments[-1].text.strip() if story.segments else ""

    # Required elements priority (never cut Front Memory or Last Action):
    # 1. Front Memory & Last Action -> 2. Author's Note -> 3. Plot Essentials -> 4. AI Instructions -> 5. Story Summary
    reserved_req = estimate_tokens(raw_front) + estimate_tokens(last_seg_text)
    rem_req = max(0, req_cap - reserved_req)

    def alloc_req(txt: str) -> str:
        nonlocal rem_req
        if not txt or rem_req <= 0:
            return ""
        toks = estimate_tokens(txt)
        if toks <= rem_req:
            rem_req -= toks
            return txt
        trimmed = _trim_to_token_budget(txt, rem_req)
        rem_req = 0
        return trimmed

    used_authors = alloc_req(raw_authors)
    used_plot = alloc_req(raw_plot)
    used_instructions = alloc_req(raw_instructions)
    used_summary = alloc_req(raw_summary)

    req_used_tokens = (
        reserved_req
        + estimate_tokens(used_authors)
        + estimate_tokens(used_plot)
        + estimate_tokens(used_instructions)
        + estimate_tokens(used_summary)
    )
    dynamic_budget = max(256, ctx_limit - req_used_tokens)

    # Dynamic allocation: ~25% Story Cards, ~25% Memory Bank (if enabled), ~50% (or ~75%) History
    cards_budget = int(dynamic_budget * 0.25)
    mem_budget = int(dynamic_budget * 0.25) if story.settings.memory_bank_enabled else 0
    history_budget = max(128, dynamic_budget - cards_budget - mem_budget)

    # Dynamically select triggered Story Cards within cards_budget
    all_triggered_unbounded = find_triggered_story_cards(story, card_budget_tokens=None)
    triggered_cards = find_triggered_story_cards(story, card_budget_tokens=cards_budget)
    dropped_cards = max(0, len(all_triggered_unbounded) - len(triggered_cards))

    # Memory Bank retrieval
    used_memories: list[dict[str, Any]] = []
    stored_memories: list[dict[str, Any]] = []
    dropped_memories = 0
    if story.settings.memory_bank_enabled and story.memories:
        query = "\n".join(s.text for s in story.segments[-3:]) if story.segments else ""
        ranked = rank_memories(story.memories, query)
        mem_toks = 0
        for mem, score in ranked:
            t = estimate_tokens(mem.text)
            entry = {**asdict(mem), "score": score, "used": False}
            if mem_toks + t <= mem_budget:
                mem_toks += t
                entry["used"] = True
                if bump_memory_uses:
                    mem.uses += 1
                used_memories.append(entry)
            else:
                dropped_memories += 1
            stored_memories.append(entry)
    elif story.memories:
        stored_memories = [{**asdict(m), "score": 0.0, "used": False} for m in story.memories]

    # Select History segments from newest backward within history_budget (always keep last segment)
    kept_segments: list[Segment] = []
    hist_toks = 0
    for idx in range(len(story.segments) - 1, -1, -1):
        seg = story.segments[idx]
        t = estimate_tokens(seg.text)
        if kept_segments and hist_toks + t > history_budget:
            break
        kept_segments.append(seg)
        hist_toks += t
    kept_segments.reverse()
    dropped_segments = max(0, len(story.segments) - len(kept_segments))

    warnings: list[str] = []
    if raw_summary and len(used_summary) < len(raw_summary):
        warnings.append("Story Summary truncated to fit Required context limit.")
    if raw_instructions and len(used_instructions) < len(raw_instructions):
        warnings.append("AI Instructions truncated to fit Required context limit.")
    if raw_plot and len(used_plot) < len(raw_plot):
        warnings.append("Plot Essentials truncated to fit Required context limit.")
    if raw_authors and len(used_authors) < len(raw_authors):
        warnings.append("Author's Note truncated to fit Required context limit.")
    if dropped_cards > 0:
        warnings.append(f"{dropped_cards} triggered Story Card(s) omitted due to context budget.")
    if dropped_memories > 0:
        warnings.append(f"{dropped_memories} Memory Bank item(s) omitted due to context budget.")
    if dropped_segments > 0:
        warnings.append(f"{dropped_segments} older story segment(s) trimmed to fit context length.")

    world_desc = story.world_description.strip()
    system_parts = []
    if used_instructions:
        system_parts.append(used_instructions)
    if used_summary:
        system_parts.append(f"## Story Summary\n{used_summary}")
    if world_desc:
        system_parts.append(f"## World Description\n{world_desc}")
    if used_plot:
        system_parts.append(f"## Plot Essentials\n{used_plot}")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": "\n\n".join(system_parts) or DEFAULT_AI_INSTRUCTIONS}
    ]

    pending_user_blocks: list[str] = []

    def format_pending(blocks: list[str], had_opening: bool, only_story: bool) -> str:
        joined = "\n\n".join(blocks)
        if had_opening and len(blocks) == 1:
            return f"Opening scene:\n{joined}\n\nContinue the story seamlessly from here."
        if only_story:
            return f"{joined}\n\nContinue the narrative seamlessly from this point."
        return joined

    pending_has_opening = False
    pending_only_story = True

    for seg in kept_segments:
        text = seg.text.strip()
        if not text:
            continue

        if seg.kind == "ai":
            if pending_user_blocks:
                messages.append({
                    "role": "user",
                    "content": format_pending(
                        pending_user_blocks, pending_has_opening, pending_only_story
                    ),
                })
                pending_user_blocks = []
                pending_has_opening = False
                pending_only_story = True
            elif messages[-1]["role"] == "assistant":
                messages.append({
                    "role": "user",
                    "content": "Continue the story seamlessly from where it left off.",
                })
            messages.append({"role": "assistant", "content": text})
        else:
            if seg.kind == "opening":
                pending_has_opening = True
                pending_user_blocks.append(text)
            elif seg.kind == "story":
                pending_user_blocks.append(text)
            else:
                pending_only_story = False
                ai_line = text if text.startswith(">") else f"> {text}"
                pending_user_blocks.append(ai_line)

    if pending_user_blocks:
        messages.append({
            "role": "user",
            "content": format_pending(
                pending_user_blocks, pending_has_opening, pending_only_story
            ),
        })
    elif messages[-1]["role"] != "user":
        if not story.segments:
            prompt_msg = (
                "Write a vivid opening scene for this adventure introducing the protagonist and setting based on Plot Essentials and World Info."
            )
        else:
            trailing_ai = ""
            for s in reversed(kept_segments):
                if s.kind != "ai":
                    break
                t = s.text.strip()
                if t:
                    trailing_ai = join_ai_continuation(t, trailing_ai) if trailing_ai else t
            anchor_tail = _extract_continuation_tail(trailing_ai or messages[-1]["content"])
            if anchor_tail:
                prompt_msg = (
                    "Continue seamlessly from the exact trailing text below. Output ONLY the next words "
                    "that come directly after it (do NOT repeat the trailing words, and do NOT reopen "
                    "a quotation mark if one is already open):\n"
                    f"{anchor_tail}"
                )
            else:
                prompt_msg = "Continue the story seamlessly from where it left off."
        messages.append({
            "role": "user",
            "content": prompt_msg,
        })

    cards_text = "\n\n".join(c.entry.strip() for c in triggered_cards)
    memories_text = "\n".join(f"- {m['text']}" for m in used_memories)

    tail_additions: list[str] = []
    if cards_text:
        tail_additions.append(f"World Lore:\n{cards_text}")
    if memories_text:
        tail_additions.append(f"## Memories\n{memories_text}")
    if used_authors:
        tail_additions.append(f"[Author's Note: {used_authors}]")
    if guide_text.strip():
        tail_additions.append(
            f"[Player Guidance (steer this response accordingly without quoting this instruction): {guide_text.strip()}]"
        )
    if retry_instructions.strip():
        draft_note = (
            f"\nPrevious response to revise:\n{previous_draft.strip()}"
            if previous_draft.strip()
            else ""
        )
        tail_additions.append(
            f"[Retry Instructions (rewrite/adjust response according to): {retry_instructions.strip()}{draft_note}]"
        )
    if raw_front:
        tail_additions.append(raw_front)

    if tail_additions:
        # Place reference context before the active turn/continuation anchor so
        # the model sees the exact latest dialogue/action immediately prior to generating.
        context_block = "\n\n".join(tail_additions)
        messages[-1]["content"] = f"{context_block}\n\n{messages[-1]['content']}"

    script_stop = False
    if apply_context_scripts and any(s.get("context", "").strip() for s in _active_scripts_for_story(story)):
        mem_prefix = (used_plot + "\n\n") if used_plot else ""
        body_text = "\n\n".join(m["content"] for m in messages[1:])
        full_ctx = mem_prefix + body_text
        res = run_story_scripts(
            story,
            "context",
            full_ctx,
            extra_info={
                "memoryLength": len(mem_prefix),
                "maxChars": ctx_limit * 4,
            },
        )
        script_stop = bool(res.get("stop"))
        modified_ctx = res.get("text")
        if isinstance(modified_ctx, str) and modified_ctx != full_ctx:
            # If the script replaced the prompt wholesale (e.g., Auto-Cards generating a card),
            # omit the RPG narrator system prompt so it doesn't fight the script's meta-prompt.
            tail_probe = body_text[-40:] if len(body_text) >= 40 else body_text
            head_probe = full_ctx[:40] if len(full_ctx) >= 40 else full_ctx
            replaced_wholesale = (
                bool(tail_probe)
                and tail_probe not in modified_ctx
                and head_probe not in modified_ctx
            )
            if replaced_wholesale:
                messages = [{"role": "user", "content": modified_ctx}]
            elif len(messages) > 2:
                messages = [messages[0], {"role": "user", "content": modified_ctx}]
            else:
                messages[-1]["content"] = modified_ctx

    history_parts: list[str] = []
    for seg in kept_segments:
        stxt = seg.text.strip()
        if not stxt:
            continue
        if seg.kind in ("do", "say") and not stxt.startswith(">"):
            stxt = f"> {stxt}"
        history_parts.append(stxt)
    history_text = "\n\n".join(history_parts)
    return {
        "context_limit": ctx_limit,
        "sections": [
            {
                "key": "ai_instructions",
                "label": "AI Instructions",
                "text": used_instructions,
            },
            {
                "key": "story_summary",
                "label": "Story Summary",
                "text": used_summary,
            },
            {
                "key": "plot_essentials",
                "label": "Plot Essentials",
                "text": used_plot,
            },
            *(
                [{"key": "world_description", "label": "World Description", "text": world_desc}]
                if world_desc
                else []
            ),
            {
                "key": "story_cards",
                "label": f"Story Cards ({len(triggered_cards)}/{len(story.story_cards)} triggered)",
                "text": cards_text,
            },
            {
                "key": "memory_bank",
                "label": f"Memory Bank ({len(used_memories)}/{len(story.memories)} used)",
                "text": memories_text,
            },
            {
                "key": "history",
                "label": f"Story History ({len(kept_segments)}/{len(story.segments)} segments)",
                "text": history_text,
            },
            {
                "key": "authors_note",
                "label": "Author's Note",
                "text": used_authors,
            },
        ],
        "triggered_cards": [asdict(c) for c in triggered_cards],
        "used_memories": used_memories,
        "stored_memories": stored_memories,
        "warnings": warnings,
        "reserved_response_tokens": story.settings.max_tokens,
        "messages": messages,
        "script_stop": script_stop,
    }


def build_chat_messages(
    story: Story,
    apply_context_scripts: bool = False,
    guide_text: str = "",
    retry_instructions: str = "",
    previous_draft: str = "",
) -> list[dict[str, str]]:
    return build_context_plan(
        story,
        apply_context_scripts=apply_context_scripts,
        bump_memory_uses=apply_context_scripts,
        guide_text=guide_text,
        retry_instructions=retry_instructions,
        previous_draft=previous_draft,
    )["messages"]


def inspect_story_context(story: Story) -> dict[str, Any]:
    """Return structured context sections for the Context Viewer."""
    return build_context_plan(story, apply_context_scripts=False, bump_memory_uses=False)


def _safe_id(raw_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", raw_id)
    if not safe:
        raise ValueError("Invalid id")
    return safe


def ensure_scripts_dir() -> None:
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)


def _script_path(script_id: str) -> Path:
    return SCRIPTS_DIR / f"{_safe_id(script_id)}.json"


def save_script(script: Script) -> Script:
    ensure_scripts_dir()
    script.updated_at = time.time()
    path = _script_path(script.id)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(script.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
    return script


COMMUNITY_SCRIPTS: dict[str, dict[str, str]] = {
    "inner_self": {
        "id": "community-inner-self",
        "name": "Inner Self (🎭)",
        "version": "1.0.2",
        "description": "NPC memory, goals, secrets, and self-reflection (LewdLeah/Inner-Self).",
        "raw_base": "https://raw.githubusercontent.com/LewdLeah/Inner-Self/main/src",
    },
    "auto_cards": {
        "id": "community-auto-cards",
        "name": "Auto-Cards",
        "version": "1.1.3",
        "description": "Automatic Story Card creation and updates during gameplay (LewdLeah/Auto-Cards).",
        "raw_base": "https://raw.githubusercontent.com/LewdLeah/Auto-Cards/main/src",
    },
}


def _fetch_community_source(raw_base: str, filename: str, timeout: int = 20) -> str:
    url = f"{raw_base.rstrip('/')}/{filename}"
    req = urllib.request.Request(url, headers={"User-Agent": "AI-RPG-Harness/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to download {filename} from {url}: {e}") from e


def ensure_community_script(kind: str, *, include_ac: bool = False) -> Script:
    """Return (and cache locally from GitHub on first use) a community AI Dungeon script."""
    norm_kind = kind.strip().lower().replace("-", "_")
    if norm_kind not in COMMUNITY_SCRIPTS:
        raise ValueError(f"Unknown community script: {kind!r}")

    if norm_kind == "inner_self" and include_ac:
        combo_id = "community-inner-self-ac"
        existing_combo = load_script(combo_id)
        if existing_combo is not None:
            return existing_combo
        base_is = ensure_community_script("inner_self", include_ac=False)
        lib = base_is.library
        if "IS_AC_ENABLED_BY_DEFAULT: false" in lib:
            lib = lib.replace("IS_AC_ENABLED_BY_DEFAULT: false", "IS_AC_ENABLED_BY_DEFAULT: true", 1)
        else:
            lib = (
                lib
                + "\nif (globalThis.MainSettings && globalThis.MainSettings.InnerSelf) { "
                "globalThis.MainSettings.InnerSelf.IS_AC_ENABLED_BY_DEFAULT = true; }\n"
            )
        combo = Script(
            id=combo_id,
            name="Inner Self + Auto-Cards (🎭)",
            description="Inner Self with built-in Auto-Cards enabled (LewdLeah/Inner-Self).",
            version=base_is.version,
            library=lib,
            input=base_is.input,
            context=base_is.context,
            output=base_is.output,
        )
        return save_script(combo)

    meta = COMMUNITY_SCRIPTS[norm_kind]
    existing = load_script(meta["id"])
    if existing is not None:
        return existing

    raw_base = meta["raw_base"]
    sc = Script(
        id=meta["id"],
        name=meta["name"],
        description=meta["description"],
        version=meta["version"],
        library=_fetch_community_source(raw_base, "library.js"),
        input=_fetch_community_source(raw_base, "input.js"),
        context=_fetch_community_source(raw_base, "context.js"),
        output=_fetch_community_source(raw_base, "output.js"),
    )
    return save_script(sc)


def create_script(
    name: str,
    description: str = "",
    version: str = "1.0",
    library: str = "",
    input_code: str = "",
    context_code: str = "",
    output_code: str = "",
) -> Script:
    sc = Script(
        id=uuid.uuid4().hex[:10],
        name=name.strip() or "Untitled Script",
        description=description.strip(),
        version=version.strip() or "1.0",
        library=library,
        input=input_code,
        context=context_code,
        output=output_code,
    )
    return save_script(sc)


def load_script(script_id: str) -> Script | None:
    ensure_scripts_dir()
    path = _script_path(script_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Script.from_dict(data)


def delete_script(script_id: str) -> bool:
    ensure_scripts_dir()
    path = _script_path(script_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_scripts() -> list[dict[str, Any]]:
    ensure_scripts_dir()
    items: list[dict[str, Any]] = []
    for path in SCRIPTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append(Script.from_dict(data).to_dict())
        except Exception:
            continue
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return items


def ensure_scenarios_dir() -> None:
    if not SCENARIOS_DIR.exists():
        SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
        for item in STARTER_SCENARIOS:
            sc = Scenario(
                id=item["id"],
                name=item["name"],
                opening=item["opening"],
            )
            save_scenario(sc)


def _scenario_path(scenario_id: str) -> Path:
    return SCENARIOS_DIR / f"{_safe_id(scenario_id)}.json"


def save_scenario(scenario: Scenario) -> Scenario:
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenario.updated_at = time.time()
    path = _scenario_path(scenario.id)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(scenario.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
    return scenario


PLACEHOLDER_RE = re.compile(r"\$\{([^{}]+)\}")


def apply_placeholders(text: str, answers: dict[str, str] | None) -> str:
    """Substitute case-sensitive ${...} placeholders in text."""
    if not text or not answers:
        return text

    def _repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in answers and answers[key] != "":
            return str(answers[key])
        return match.group(0)

    return PLACEHOLDER_RE.sub(_repl, text)


def create_scenario(
    name: str,
    opening: str = "",
    description: str = "",
    scenario_type: str = "story",
    choices: list[dict[str, Any]] | None = None,
    ai_instructions: str = "",
    story_summary: str = "",
    plot_essentials: str = "",
    authors_note: str = "",
    third_person: bool = False,
    character_name: str = "",
    story_cards: list[dict[str, Any]] | None = None,
    builtin_script: dict[str, Any] | None = None,
    attached_scripts: list[dict[str, Any]] | None = None,
) -> Scenario:
    ensure_scenarios_dir()
    clean_name = name.strip() or "Untitled Scenario"
    stype = scenario_type if scenario_type in ("story", "multiple_choice", "character_creator") else "story"
    clean_choices = _normalize_choices_tree(choices)
    sc = Scenario(
        id=uuid.uuid4().hex[:10],
        name=clean_name,
        description=description.strip(),
        scenario_type=stype,
        opening=opening.strip(),
        choices=clean_choices,
        ai_instructions=ai_instructions.strip(),
        story_summary=story_summary.strip(),
        plot_essentials=plot_essentials.strip(),
        authors_note=authors_note.strip(),
        third_person=bool(third_person),
        character_name=character_name.strip(),
        story_cards=[StoryCard.from_dict(c) for c in (story_cards or [])],
        builtin_script=_normalize_builtin_script(builtin_script),
        attached_scripts=_normalize_attached_scripts(attached_scripts),
    )
    return save_scenario(sc)


def load_scenario(scenario_id: str) -> Scenario | None:
    ensure_scenarios_dir()
    path = _scenario_path(scenario_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Scenario.from_dict(data)


def delete_scenario(scenario_id: str) -> bool:
    ensure_scenarios_dir()
    path = _scenario_path(scenario_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_scenarios() -> list[dict[str, Any]]:
    ensure_scenarios_dir()
    items: list[dict[str, Any]] = []
    for path in SCENARIOS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items.append(Scenario.from_dict(data).to_dict())
        except Exception:
            continue
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return items


def fetch_aidungeon_url_payload(url_or_id: str, timeout: int = 75) -> dict[str, Any]:
    """Fetch full Scenario JSON from play.aidungeon.com via the Playwright helper."""
    target = str(url_or_id or "").strip()
    if not target:
        raise ValueError("AI Dungeon scenario URL or shortId is required")
    script_path = Path(__file__).parent / "aidungeon_importer.mjs"
    if not script_path.exists():
        raise RuntimeError(f"Missing importer script: {script_path}")

    proc = subprocess.run(
        ["node", str(script_path), target],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "Unknown Playwright importer failure").strip()
        if proc.returncode == 2:
            raise ValueError(err)
        raise RuntimeError(err)
    data = json.loads(proc.stdout)
    if not isinstance(data, dict):
        raise RuntimeError("Importer returned invalid payload")
    return data


def import_aidungeon_json(raw: dict[str, Any]) -> Scenario:
    """Import an AI Dungeon export (metadata.json, Scenario GraphQL JSON, or URL capture) as a Scenario."""
    adv = raw.get("adventure") if isinstance(raw.get("adventure"), dict) else {}
    sc_obj = raw.get("scenario") if isinstance(raw.get("scenario"), dict) else {}
    details = raw.get("details") if isinstance(raw.get("details"), dict) else {}

    st_candidates = [raw.get("state"), sc_obj.get("state"), details.get("state")]
    st: dict[str, Any] = next((s for s in st_candidates if isinstance(s, dict)), {})

    src = adv or sc_obj or details or raw
    title = str(
        details.get("title")
        or src.get("title")
        or src.get("name")
        or "Imported Scenario"
    ).strip()
    description = str(
        details.get("description")
        or src.get("description")
        or ""
    ).strip()
    plot_essentials = str(
        src.get("memory")
        or src.get("plot_essentials")
        or src.get("plotEssentials")
        or st.get("plotEssentials")
        or st.get("memory")
        or ""
    ).strip()
    authors_note = str(
        src.get("authorsNote")
        or src.get("authors_note")
        or st.get("authorsNote")
        or ""
    ).strip()
    third_person = bool(
        details.get("thirdPerson", src.get("thirdPerson", src.get("third_person", False)))
    )
    story_summary = str(
        st.get("storySummary")
        or raw.get("storySummary")
        or raw.get("story_summary")
        or ""
    ).strip()

    instructions_obj = st.get("instructions") or raw.get("instructions")
    if isinstance(instructions_obj, dict):
        ai_instructions = str(
            instructions_obj.get("scenario")
            or instructions_obj.get("text")
            or ""
        ).strip()
    elif isinstance(instructions_obj, str):
        ai_instructions = instructions_obj.strip()
    else:
        ai_instructions = str(raw.get("ai_instructions") or "").strip()

    opening = str(
        src.get("prompt")
        or src.get("opening")
        or st.get("prompt")
        or (details.get("state") or {}).get("prompt")
        or raw.get("opening")
        or ""
    ).strip()

    card_sources = [
        sc_obj.get("inheritedStoryCards"),
        raw.get("inheritedStoryCards"),
        sc_obj.get("storyCards"),
        st.get("storyCards"),
        raw.get("storyCards"),
        raw.get("story_cards"),
    ]
    cards: list[StoryCard] = []
    seen_card_keys: set[tuple[str, str, str]] = set()
    for card_list in card_sources:
        if not isinstance(card_list, list):
            continue
        for c in card_list:
            if not isinstance(c, dict) or c.get("deletedAt"):
                continue
            card = StoryCard.from_dict(c)
            sig = (str(c.get("id") or ""), card.keys, card.entry)
            if sig in seen_card_keys:
                continue
            seen_card_keys.add(sig)
            cards.append(card)

    raw_options = (
        raw.get("choices")
        or sc_obj.get("options")
        or details.get("options")
        or raw.get("options")
        or []
    )
    choices = _normalize_choices_tree(raw_options)

    raw_stype = str(src.get("scenario_type") or details.get("type") or src.get("type") or "story")
    if choices or raw_stype in ("multiple_choice", "multipleChoice"):
        stype = "multiple_choice"
    elif raw_stype in ("character_creator", "characterCreator") or (not opening and cards and any(c.use_for_character_creation for c in cards)):
        stype = "character_creator"
    else:
        stype = "story"

    sc = Scenario(
        id=uuid.uuid4().hex[:10],
        name=title,
        description=description,
        scenario_type=stype,
        opening=opening,
        choices=choices,
        ai_instructions=ai_instructions,
        story_summary=story_summary,
        plot_essentials=plot_essentials,
        authors_note=authors_note,
        third_person=third_person,
        story_cards=cards,
    )
    return save_scenario(sc)


def ensure_stories_dir() -> None:
    STORIES_DIR.mkdir(parents=True, exist_ok=True)


def _story_path(story_id: str) -> Path:
    return STORIES_DIR / f"{_safe_id(story_id)}.json"


def save_story(story: Story) -> Story:
    ensure_stories_dir()
    story.updated_at = time.time()
    path = _story_path(story.id)
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(story.to_dict(), indent=2), encoding="utf-8")
    os.replace(tmp_path, path)
    return story


def load_story(story_id: str) -> Story | None:
    path = _story_path(story_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return Story.from_dict(data)


def delete_story(story_id: str) -> bool:
    path = _story_path(story_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_stories() -> list[dict[str, Any]]:
    ensure_stories_dir()
    items: list[dict[str, Any]] = []
    for path in STORIES_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            segments = data.get("segments", [])
            preview = ""
            if segments:
                preview = str(segments[-1].get("text", ""))[:120]
            items.append({
                "id": data["id"],
                "title": data.get("title", "Untitled Adventure"),
                "segment_count": len(segments),
                "preview": preview,
                "updated_at": data.get("updated_at", path.stat().st_mtime),
            })
        except Exception:
            continue
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return items


_QUICKSTART_NAMES = ["Aelindra", "Kaelen", "Seraphina", "Rowan", "Theron", "Lyra", "Dorian", "Vesper"]
_QUICKSTART_GENDERS = ["Female", "Male", "Non-binary"]


def create_story_from_scenario(
    scenario_id: str = "",
    title: str | None = None,
    choice_id: str | None = None,
    choice_path: list[str] | None = None,
    placeholder_answers: dict[str, str] | None = None,
    selected_card_ids: list[str] | None = None,
    quickstart: bool = False,
    enable_inner_self: bool = False,
    enable_auto_cards: bool = False,
) -> Story:
    scenario = load_scenario(scenario_id) if scenario_id else None
    if scenario is None:
        scenarios = list_scenarios()
        if scenarios:
            scenario = Scenario.from_dict(scenarios[0])

    answers = dict(placeholder_answers or {})
    raw_opening = scenario.opening if scenario else ""
    extra_plot_parts: list[str] = []
    eff_ai_instructions = scenario.ai_instructions if scenario else ""
    eff_story_summary = scenario.story_summary if scenario else ""
    eff_authors_note = scenario.authors_note if scenario else ""
    eff_third_person = scenario.third_person if scenario else False
    eff_char_name = scenario.character_name if scenario else ""
    eff_cards_raw = (
        [StoryCard.from_dict(asdict(c)) for c in scenario.story_cards]
        if scenario
        else []
    )
    story_builtin_script = (
        _normalize_builtin_script(scenario.builtin_script)
        if scenario
        else _default_builtin_script()
    )
    story_attached_scripts = (
        _normalize_attached_scripts(scenario.attached_scripts)
        if scenario
        else []
    )
    if enable_inner_self or enable_auto_cards:
        target_script = (
            ensure_community_script("inner_self", include_ac=bool(enable_auto_cards))
            if enable_inner_self
            else ensure_community_script("auto_cards")
        )
        community_ids = {"community-inner-self", "community-inner-self-ac", "community-auto-cards"}
        if enable_inner_self:
            # Replace standalone auto-cards or base inner-self with the coordinated script
            story_attached_scripts = [
                s for s in story_attached_scripts if s.get("script_id") not in community_ids
            ]
        elif any(
            s.get("script_id") in ("community-inner-self", "community-inner-self-ac")
            and s.get("enabled", True)
            for s in story_attached_scripts
        ):
            # Upgrade an already-attached Inner Self to include Auto-Cards
            target_script = ensure_community_script("inner_self", include_ac=True)
            story_attached_scripts = [
                s for s in story_attached_scripts if s.get("script_id") not in community_ids
            ]
        if not any(s.get("script_id") == target_script.id for s in story_attached_scripts):
            if len(story_attached_scripts) < 10:
                story_attached_scripts.append({"script_id": target_script.id, "enabled": True})
    resolved_mc_title: str | None = None

    world_desc = ""
    if scenario and scenario.scenario_type == "multiple_choice" and scenario.choices:
        chain = _resolve_choice_chain(scenario.choices, choice_path=choice_path, choice_id=choice_id)
        for node in chain:
            if str(node.get("opening") or "").strip():
                raw_opening = str(node["opening"])
            if str(node.get("plot_essentials") or "").strip():
                extra_plot_parts.append(str(node["plot_essentials"]).strip())
            if str(node.get("ai_instructions") or "").strip():
                eff_ai_instructions = str(node["ai_instructions"])
            if str(node.get("story_summary") or "").strip():
                eff_story_summary = str(node["story_summary"])
            if str(node.get("authors_note") or "").strip():
                eff_authors_note = str(node["authors_note"])
            if node.get("third_person") is not None:
                eff_third_person = bool(node["third_person"])
            if str(node.get("character_name") or "").strip():
                eff_char_name = str(node["character_name"])
            if isinstance(node.get("story_cards"), list) and len(node["story_cards"]) > 0:
                eff_cards_raw = [StoryCard.from_dict(c) for c in node["story_cards"] if isinstance(c, dict)]
            if node.get("builtin_script") and any(
                str(node["builtin_script"].get(k) or "").strip()
                for k in ("input", "context", "output")
            ):
                story_builtin_script = _normalize_builtin_script(node["builtin_script"])
            if node.get("attached_scripts"):
                seen_sids = {x["script_id"] for x in story_attached_scripts}
                for item in _normalize_attached_scripts(node["attached_scripts"]):
                    if item["script_id"] not in seen_sids:
                        story_attached_scripts.append(item)
                        seen_sids.add(item["script_id"])
            lbl = str(node.get("label") or "").strip()
            if lbl and lbl != "Option":
                resolved_mc_title = lbl
    elif scenario and scenario.scenario_type == "character_creator":
        # Character Creator displays world description before the AI-generated starting prompt.
        world_desc = apply_placeholders(raw_opening, answers).strip()
        raw_opening = ""
        if quickstart:
            if not str(answers.get("character.name") or "").strip():
                answers["character.name"] = random.choice(_QUICKSTART_NAMES)
            if not str(answers.get("character.gender") or "").strip():
                answers["character.gender"] = random.choice(_QUICKSTART_GENDERS)
            if not selected_card_ids and scenario.story_cards:
                cc_pool = [c for c in scenario.story_cards if c.use_for_character_creation] or scenario.story_cards
                by_cat: dict[str, list[StoryCard]] = {}
                for c in cc_pool:
                    cat = (c.card_type or "Custom").strip().lower()
                    by_cat.setdefault(cat, []).append(c)
                selected_card_ids = [random.choice(group).id for group in by_cat.values()]

    resolved_opening = apply_placeholders(raw_opening, answers).strip()
    story_id = uuid.uuid4().hex[:12]
    segments: list[Segment] = []
    if resolved_opening:
        segments.append(
            Segment(
                id=uuid.uuid4().hex[:10],
                kind="opening",
                text=resolved_opening,
            )
        )

    raw_cards = eff_cards_raw
    for card in raw_cards:
        # Placeholders apply to Title, Keys, and Entry—never card_type.
        card.title = apply_placeholders(card.title, answers)
        card.keys = apply_placeholders(card.keys, answers)
        card.entry = apply_placeholders(card.entry, answers)

    plot_parts = []
    base_plot = apply_placeholders(scenario.plot_essentials if scenario else "", answers).strip()
    if base_plot:
        plot_parts.append(base_plot)
    for ep in extra_plot_parts:
        resolved_ep = apply_placeholders(ep, answers).strip()
        if resolved_ep and resolved_ep not in plot_parts:
            plot_parts.append(resolved_ep)

    if scenario and scenario.scenario_type == "character_creator":
        char_lines: list[str] = ["CHARACTER INFORMATION"]
        cname = str(answers.get("character.name") or eff_char_name or "").strip()
        cgender = str(answers.get("character.gender") or "").strip()
        if cname:
            char_lines.append(f"Name: {cname}")
        if cgender:
            char_lines.append(f"Gender: {cgender}")

        trait_tags: list[str] = []
        if cgender:
            trait_tags.append(cgender)
        selected_set = set(selected_card_ids or [])
        for card in raw_cards:
            if card.id in selected_set:
                card.is_pinned = True
                label = card.card_type.strip().capitalize() if card.card_type.strip() else "Trait"
                detail = card.entry.strip() or card.description.strip()
                if card.title and detail:
                    char_lines.append(f"{label}: {card.title} — {detail}")
                elif card.title:
                    char_lines.append(f"{label}: {card.title}")
                elif detail:
                    char_lines.append(f"{label}: {detail}")
                if card.title:
                    trait_tags.append(card.title)
        if cname and trait_tags:
            char_lines.append(f"You are {cname}, [{', '.join(trait_tags)}]")
        elif cname:
            char_lines.append(f"You are {cname}.")
        if len(char_lines) > 1:
            plot_parts.append("\n".join(char_lines))

    char_name = apply_placeholders(eff_char_name, answers).strip()
    if not char_name and "character.name" in answers:
        char_name = str(answers["character.name"]).strip()

    init_placeholders = [
        {"question": k, "answer": str(v)}
        for k, v in answers.items()
    ]

    default_title = resolved_mc_title or (scenario.name if scenario else "Untitled Adventure")
    story = Story(
        id=story_id,
        title=(title.strip() if title and title.strip() else default_title),
        scenario_id=scenario.id if scenario else "",
        description=scenario.description if scenario else "",
        world_description=world_desc,
        ai_instructions=apply_placeholders(
            eff_ai_instructions.strip()
            if eff_ai_instructions.strip()
            else DEFAULT_AI_INSTRUCTIONS,
            answers,
        ),
        story_summary=apply_placeholders(eff_story_summary, answers),
        plot_essentials="\n\n".join(p for p in plot_parts if p),
        authors_note=apply_placeholders(eff_authors_note, answers),
        third_person=eff_third_person,
        character_name=char_name,
        story_cards=raw_cards,
        builtin_script=story_builtin_script,
        attached_scripts=story_attached_scripts,
        script_state={"placeholders": init_placeholders} if init_placeholders else {},
        segments=segments,
        settings=load_default_settings(),
    )
    return save_story(story)


def ensure_default_story() -> Story:
    existing = list_stories()
    if existing:
        loaded = load_story(existing[0]["id"])
        if loaded is not None:
            return loaded
    return create_story_from_scenario("tavern")
