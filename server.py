from __future__ import annotations

import http.client
import json
import mimetypes
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from harness import (
    DEFAULT_AI_INSTRUCTIONS,
    MemoryItem,
    Scenario,
    Script,
    Segment,
    Story,
    StoryCard,
    StorySettings,
    _normalize_attached_scripts,
    _normalize_builtin_script,
    _normalize_choices_tree,
    build_chat_messages,
    build_context_plan,
    create_scenario,
    create_script,
    create_story_from_scenario,
    cycle_retry_variant,
    delete_scenario,
    delete_script,
    delete_story,
    ensure_community_script,
    ensure_scenarios_dir,
    erase_last_segment,
    erase_to_here,
    export_adventure_zip,
    export_story_cards_aidungeon,
    fetch_aidungeon_url_payload,
    format_player_text,
    import_aidungeon_json,
    import_story_cards_aidungeon,
    inspect_story_context,
    list_scenarios,
    list_scripts,
    list_stories,
    load_default_settings,
    load_endpoint_config,
    load_scenario,
    load_script,
    load_story,
    public_endpoint_config,
    push_undo_snapshot,
    redo_story,
    remove_repeated_leading_sentences,
    run_story_scripts,
    save_default_settings,
    save_endpoint_config,
    save_scenario,
    save_script,
    save_story,
    trim_incomplete_sentence,
    undo_story,
)
from script_runner import run_js_hook

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
LOGS_DIR = BASE_DIR / "logs"

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8080").rstrip("/")
_BOOT_LLM_URL = LLM_URL
_detected_llama_urls: set[str] = set()
_discovered_models_cache: dict[str, list[str]] = {}
_discovered_max_ctx_cache: dict[str, int] = {}
_discovered_model_max_ctx: dict[str, dict[str, int]] = {}
_discovered_thinking_mode_cache: dict[str, str] = {}
_discovered_model_thinking_cache: dict[str, dict[str, str]] = {}


def _active_endpoint() -> dict[str, Any]:
    # Respect direct runtime overrides of server.LLM_URL (e.g., inside unit tests).
    if LLM_URL != _BOOT_LLM_URL:
        return {
            "llm_url": LLM_URL.rstrip("/"),
            "api_key": "",
            "model": os.environ.get("LLM_MODEL", "").strip(),
            "provider_type": "auto",
            "presets": [],
        }
    return load_endpoint_config()


def _v1_url(base_url: str, endpoint: str) -> str:
    """Join an OpenAI-compatible base URL with `/models` or `/chat/completions` cleanly."""
    clean = base_url.rstrip("/")
    suffix = "/" + endpoint.lstrip("/")
    if clean.endswith("/v1"):
        return f"{clean}{suffix}"
    return f"{clean}/v1{suffix}"


def _llm_headers(api_key: str = "") -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _is_llama_cpp(cfg: dict[str, Any]) -> bool:
    ptype = str(cfg.get("provider_type") or "auto")
    if ptype == "llama_cpp":
        return True
    if ptype == "openai_compat":
        return False
    url = str(cfg.get("llm_url") or "").rstrip("/")
    if url in _detected_llama_urls:
        return True
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" or cfg.get("api_key"):
        return False
    if parsed.port in (11434, 1234) or parsed.path.rstrip("/").endswith("/v1"):
        return False
    return host in ("127.0.0.1", "localhost", "::1")


def _resolve_model_name(cfg: dict[str, Any]) -> str:
    chosen = str(cfg.get("model") or "").strip()
    if chosen:
        return chosen
    url = str(cfg.get("llm_url") or "").rstrip("/")
    cached = _discovered_models_cache.get(url) or []
    if cached:
        return cached[0]
    try:
        req = urllib.request.Request(
            _v1_url(url, "/models"),
            headers=_llm_headers(str(cfg.get("api_key") or "")),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            mdata = json.loads(resp.read().decode("utf-8", errors="replace"))
            ids = [str(m.get("id")) for m in (mdata.get("data") or []) if m.get("id")]
            if ids:
                _discovered_models_cache[url] = ids
                return ids[0]
    except Exception:
        pass
    return "default"


def _build_chat_payload(
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    stream: bool,
    temperature: float = 0.85,
    max_tokens: int = 320,
    top_p: float | None = None,
    top_k: int | None = None,
    repeat_penalty: float | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    enable_thinking: bool = False,
    reasoning_effort: str = "off",
) -> dict[str, Any]:
    effort = (reasoning_effort or ("medium" if enable_thinking else "off")).strip().lower()
    if effort not in ("off", "low", "medium", "high", "xhigh"):
        effort = "medium" if enable_thinking else "off"
    thinking_on = effort != "off"
    payload: dict[str, Any] = {
        "model": _resolve_model_name(cfg),
        "messages": messages,
        "stream": stream,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if presence_penalty is not None:
        payload["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        payload["frequency_penalty"] = frequency_penalty
    if _is_llama_cpp(cfg):
        if top_k is not None:
            payload["top_k"] = top_k
        if repeat_penalty is not None:
            payload["repeat_penalty"] = repeat_penalty
        payload["chat_template_kwargs"] = {"enable_thinking": thinking_on}
        if thinking_on:
            payload["reasoning_effort"] = effort
    elif thinking_on:
        payload["reasoning_effort"] = effort
    return payload


def _resolve_serve_script() -> Path | None:
    env_val = os.environ.get("LLAMA_SERVE_SCRIPT", "").strip()
    if env_val:
        return Path(env_val)
    sibling = BASE_DIR.parent / "llama.cpp" / "serve-gemma4-26b-96k.sh"
    return sibling if sibling.exists() else None


SERVE_SCRIPT = _resolve_serve_script()
APP_HOST = os.environ.get("HOST", "127.0.0.1")
APP_PORT = int(os.environ.get("PORT", "7860"))

_llm_lock = threading.Lock()
_llm_proc: subprocess.Popen[bytes] | None = None
_story_locks: dict[str, threading.Lock] = {}
_story_locks_guard = threading.Lock()


def get_story_lock(story_id: str) -> threading.Lock:
    with _story_locks_guard:
        lock = _story_locks.get(story_id)
        if lock is None:
            lock = threading.Lock()
            _story_locks[story_id] = lock
        return lock


def _infer_thinking_mode_from_model(
    model_id: str | None,
    supported_params: list[str] | None = None,
) -> str:
    """Classify a model's reasoning control: 'effort' (stepped), 'toggle' (on/off), or 'none'."""
    if supported_params:
        params_lower = {str(p).lower() for p in supported_params}
        if "reasoning_effort" in params_lower or "reasoning" in params_lower:
            return "effort"
    mid = str(model_id or "").strip().lower()
    if not mid:
        return "none"
    effort_markers = (
        "gpt-oss",
        "o1",
        "o3",
        "o4",
        "gpt-5",
        "grok-3-mini",
        "grok-4",
        "claude-3-7",
        "claude-3.7",
        "claude-4",
        "claude-sonnet-4",
        "claude-opus-4",
        "claude-haiku-4",
        "gemini-2.5",
        "gemini-3",
        "gemini-4",
    )
    if any(m in mid for m in effort_markers):
        return "effort"
    toggle_markers = (
        "gemma-4",
        "gemma4",
        "qwen3",
        "qwen-3",
        "qwen3.5",
        "qwq",
        "deepseek-r1",
        "deepseek-reasoner",
        "smollm3",
        "glm-4",
    )
    if any(m in mid for m in toggle_markers):
        return "toggle"
    return "none"


def _probe_llama_props(active_url: str, api_key: str) -> tuple[int | None, str | None]:
    """Query llama.cpp /props (and fallback /slots) for context limit and thinking mode."""
    base = active_url.rstrip("/")
    headers = _llm_headers(api_key)
    found_ctx: int | None = None
    found_thinking: str | None = None
    for path in ("/props", "/slots"):
        try:
            req = urllib.request.Request(f"{base}{path}", headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception:
            continue
        n_ctx: Any = None
        if isinstance(data, dict):
            dgs = data.get("default_generation_settings")
            if isinstance(dgs, dict):
                n_ctx = dgs.get("n_ctx")
            if n_ctx is None:
                n_ctx = data.get("n_ctx")
            if path == "/props" and found_thinking is None:
                caps = data.get("chat_template_caps")
                tmpl = str(data.get("chat_template") or "")
                if isinstance(caps, dict) and caps.get("supports_reasoning_effort"):
                    found_thinking = "effort"
                elif "enable_thinking" in tmpl:
                    found_thinking = "toggle"
                elif caps is not None or tmpl:
                    found_thinking = "none"
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            n_ctx = data[0].get("n_ctx")
        if found_ctx is None and isinstance(n_ctx, (int, float)) and int(n_ctx) >= 1024:
            found_ctx = int(n_ctx)
            _discovered_max_ctx_cache[base] = found_ctx
        if found_ctx is not None and (found_thinking is not None or path != "/props"):
            break
    if found_thinking is not None:
        _discovered_thinking_mode_cache[base] = found_thinking
    return found_ctx, found_thinking


def _probe_llama_max_context(active_url: str, api_key: str) -> int | None:
    """Query llama.cpp /props (and fallback /slots) for the active slot context limit."""
    ctx, _ = _probe_llama_props(active_url, api_key)
    return ctx


def _extract_model_max_context(model_obj: dict[str, Any]) -> int | None:
    """Extract per-model max context length from an OpenAI-compat /v1/models entry."""
    if not isinstance(model_obj, dict):
        return None
    candidates: list[Any] = [
        model_obj.get("context_length"),
        model_obj.get("max_model_len"),
        model_obj.get("max_context_length"),
        model_obj.get("input_token_limit"),
        model_obj.get("context_window"),
    ]
    top_prov = model_obj.get("top_provider")
    if isinstance(top_prov, dict):
        candidates.append(top_prov.get("context_length"))
    meta = model_obj.get("meta")
    if isinstance(meta, dict):
        candidates.append(meta.get("n_ctx"))
        candidates.append(meta.get("n_ctx_train"))
    for val in candidates:
        if isinstance(val, (int, float)) and int(val) >= 1024:
            return int(val)
    return None


def _cache_models_payload(active_url: str, mdata: Any) -> list[str]:
    """Parse /v1/models JSON, caching model IDs, context lengths, and thinking modes."""
    base = active_url.rstrip("/")
    models: list[str] = []
    ctx_map: dict[str, int] = {}
    think_map: dict[str, str] = {}
    items = mdata.get("data") if isinstance(mdata, dict) else None
    if isinstance(items, list):
        for m in items:
            if not isinstance(m, dict) or not m.get("id"):
                continue
            mid = str(m["id"])
            models.append(mid)
            ctx = _extract_model_max_context(m)
            if ctx is not None:
                ctx_map[mid] = ctx
            supp = m.get("supported_parameters")
            think_map[mid] = _infer_thinking_mode_from_model(
                mid, supp if isinstance(supp, list) else None
            )
    _discovered_models_cache[base] = models
    if ctx_map:
        _discovered_model_max_ctx[base] = ctx_map
    else:
        _discovered_model_max_ctx.pop(base, None)
    if think_map:
        _discovered_model_thinking_cache[base] = think_map
    else:
        _discovered_model_thinking_cache.pop(base, None)
    return models


def get_effective_max_context() -> int | None:
    """Return the active LLM's current max context length (llama.cpp /props or /v1/models)."""
    cfg = _active_endpoint()
    active_url = str(cfg.get("llm_url") or LLM_URL).rstrip("/")
    cached = _discovered_max_ctx_cache.get(active_url)
    if cached is not None:
        return cached
    parsed = urllib.parse.urlparse(active_url)
    probe_health = parsed.scheme != "https" and str(cfg.get("provider_type") or "auto") != "openai_compat"
    if probe_health:
        llama_ctx = _probe_llama_max_context(active_url, str(cfg.get("api_key") or ""))
        if llama_ctx is not None:
            return llama_ctx
    # Fallback to per-model context length discovered from /v1/models (OpenRouter, vLLM, etc.)
    model_map = _discovered_model_max_ctx.get(active_url) or {}
    if model_map:
        chosen = str(cfg.get("model") or "").strip()
        if chosen and chosen in model_map:
            return model_map[chosen]
        discovered = _discovered_models_cache.get(active_url) or []
        if discovered and discovered[0] in model_map:
            return model_map[discovered[0]]
    return None


def check_llm_status() -> dict[str, Any]:
    cfg = _active_endpoint()
    active_url = str(cfg.get("llm_url") or LLM_URL).rstrip("/")
    api_key = str(cfg.get("api_key") or "")
    parsed = urllib.parse.urlparse(active_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    status_info: dict[str, Any] = {
        "url": active_url,
        "state": "offline",
        "model": cfg.get("model") or None,
        "available_models": [],
        "max_context": None,
        "max_context_source": None,
        "thinking_mode": "none",
        "detail": "Server not reachable",
        "process_running": _is_managed_proc_alive(),
        "config": public_endpoint_config(cfg),
    }

    # Skip llama-server-specific /health probe for remote/explicit OpenAI-compat URLs
    probe_health = parsed.scheme != "https" and str(cfg.get("provider_type") or "auto") != "openai_compat"
    if probe_health:
        try:
            req = urllib.request.Request(f"{active_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                data = json.loads(body) if body.strip() else {}
                status_val = data.get("status", "ok")
                if "status" in data:
                    _detected_llama_urls.add(active_url)
                if resp.status == 200 and status_val == "ok":
                    status_info["state"] = "ready"
                    status_info["detail"] = "Model loaded and ready"
                elif status_val == "loading model":
                    status_info["state"] = "loading"
                    status_info["detail"] = "Loading model into VRAM/RAM..."
                else:
                    status_info["state"] = str(status_val)
                    status_info["detail"] = body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 503:
                status_info["state"] = "loading"
                status_info["detail"] = "Loading model into VRAM/RAM..."
            elif e.code != 404:
                status_info["state"] = "error"
                status_info["detail"] = f"HTTP {e.code}: {body[:200]}"
                return status_info
        except Exception as e:
            if _is_managed_proc_alive():
                status_info["state"] = "loading"
                status_info["detail"] = f"Starting LLM on {host}:{port}..."
                return status_info
            status_info["detail"] = str(e)
            return status_info

    # Query /v1/models (works for llama-server, Ollama, LM Studio, vLLM, OpenRouter, OpenAI, etc.)
    try:
        req = urllib.request.Request(
            _v1_url(active_url, "/models"),
            headers=_llm_headers(api_key),
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            mdata = json.loads(resp.read().decode("utf-8", errors="replace"))
            models = _cache_models_payload(active_url, mdata)
            status_info["available_models"] = models[:100]
            if status_info["state"] == "offline":
                status_info["state"] = "ready"
                status_info["detail"] = "Endpoint connected"
            if not status_info["model"] and models:
                status_info["model"] = models[0]
    except urllib.error.HTTPError as e:
        if status_info["state"] == "offline":
            body = e.read().decode("utf-8", errors="replace")
            if e.code in (401, 403):
                status_info["state"] = "error"
                status_info["detail"] = f"Authentication failed (HTTP {e.code})"
            elif e.code == 404 and cfg.get("model"):
                # Some minimal OpenAI-compatible proxies omit /v1/models
                status_info["state"] = "ready"
                status_info["detail"] = "Configured endpoint (model list unavailable)"
            else:
                status_info["state"] = "error"
                status_info["detail"] = f"HTTP {e.code}: {body[:200]}"
    except Exception as e:
        if status_info["state"] == "offline":
            status_info["detail"] = str(e)

    if status_info["state"] == "ready":
        active_model = str(status_info.get("model") or "").strip()
        llama_thinking: str | None = None
        if probe_health or active_url in _detected_llama_urls:
            llama_ctx, llama_thinking = _probe_llama_props(active_url, api_key)
            if llama_ctx is not None:
                status_info["max_context"] = llama_ctx
                status_info["max_context_source"] = "llama.cpp"
        if status_info["max_context"] is None:
            model_map = _discovered_model_max_ctx.get(active_url) or {}
            if active_model and active_model in model_map:
                status_info["max_context"] = model_map[active_model]
                status_info["max_context_source"] = "model"
        if llama_thinking is not None:
            status_info["thinking_mode"] = llama_thinking
        else:
            tmap = _discovered_model_thinking_cache.get(active_url) or {}
            if active_model and active_model in tmap:
                status_info["thinking_mode"] = tmap[active_model]
            else:
                status_info["thinking_mode"] = _infer_thinking_mode_from_model(active_model)
    else:
        _discovered_max_ctx_cache.pop(active_url, None)
        _discovered_model_max_ctx.pop(active_url, None)
        _discovered_thinking_mode_cache.pop(active_url, None)
        _discovered_model_thinking_cache.pop(active_url, None)

    return status_info


def _is_managed_proc_alive() -> bool:
    global _llm_proc
    with _llm_lock:
        if _llm_proc is None:
            return False
        if _llm_proc.poll() is not None:
            _llm_proc = None
            return False
        return True


def start_llm_server() -> dict[str, Any]:
    global _llm_proc
    status = check_llm_status()
    if status["state"] in ("ready", "loading"):
        return {"started": False, "message": "LLM server is already running", "status": status}

    if SERVE_SCRIPT is None or not SERVE_SCRIPT.exists():
        return {
            "started": False,
            "message": "Set LLAMA_SERVE_SCRIPT or start an OpenAI-compatible LLM server at LLM_URL.",
            "status": status,
        }

    with _llm_lock:
        if _llm_proc is not None and _llm_proc.poll() is None:
            return {
                "started": False,
                "message": "LLM server process is already starting",
                "status": check_llm_status(),
            }

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOGS_DIR / "llama-server.log"
        log_file = open(log_path, "ab")
        _llm_proc = subprocess.Popen(
            ["bash", str(SERVE_SCRIPT)],
            cwd=str(SERVE_SCRIPT.parent),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        log_file.close()

    return {
        "started": True,
        "message": f"Launched {SERVE_SCRIPT.name}",
        "log_path": str(LOGS_DIR / "llama-server.log"),
        "status": check_llm_status(),
    }


class RPGHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Clients disconnecting mid-request (page reloads, closed tabs, phone
        # sleeping, browser pre-connect sockets) is routine, not a server bug.
        # socketserver otherwise dumps a full traceback for every occurrence.
        exc = sys.exc_info()[1]
        if isinstance(
            exc,
            (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError),
        ):
            return
        super().handle_error(request, client_address)


class RPGRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # Don't keep idle keep-alive connections open forever; browsers (especially
    # mobile ones over Tailscale) open speculative sockets and drop them.
    timeout = 30

    def log_message(self, format: str, *args: Any) -> None:
        # Keep terminal output clean; log errors or API calls concisely.
        pass

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _serve_static(self, rel_path: str) -> None:
        if rel_path in ("", "/"):
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        target = (STATIC_DIR / rel_path).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_sse_event(self, event_name: str, data: dict[str, Any]) -> None:
        msg = f"event: {event_name}\ndata: {json.dumps(data)}\n\n".encode("utf-8")
        self.wfile.write(msg)
        self.wfile.flush()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/llm/status":
            self._send_json(200, check_llm_status())
            return

        if path == "/api/llm/config":
            self._send_json(200, {"config": public_endpoint_config(_active_endpoint())})
            return

        if path == "/api/settings":
            self._send_json(200, {"settings": asdict(load_default_settings())})
            return

        if path == "/api/scenarios":
            self._send_json(
                200,
                {
                    "scenarios": list_scenarios(),
                    "default_ai_instructions": DEFAULT_AI_INSTRUCTIONS,
                },
            )
            return

        if path.startswith("/api/scenarios/"):
            scenario_id = path[len("/api/scenarios/"):].strip("/")
            if "/" in scenario_id or not scenario_id:
                self._send_error_json(404, "Scenario not found")
                return
            scenario = load_scenario(scenario_id)
            if scenario is None:
                self._send_error_json(404, "Scenario not found")
                return
            self._send_json(200, {"scenario": scenario.to_dict()})
            return

        if path == "/api/scripts":
            self._send_json(200, {"scripts": list_scripts()})
            return

        if path.startswith("/api/scripts/"):
            script_id = path[len("/api/scripts/"):].strip("/")
            if "/" in script_id or not script_id:
                self._send_error_json(404, "Script not found")
                return
            sc = load_script(script_id)
            if sc is None:
                self._send_error_json(404, "Script not found")
                return
            self._send_json(200, {"script": sc.to_dict()})
            return

        if path == "/api/stories":
            self._send_json(200, {"stories": list_stories()})
            return

        if path.startswith("/api/stories/"):
            rest = [p for p in path[len("/api/stories/"):].split("/") if p]
            if len(rest) == 2 and rest[1] == "context":
                story = load_story(rest[0])
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                self._send_json(200, self._build_context_report(story))
                return
            if len(rest) == 2 and rest[1] == "export":
                story = load_story(rest[0])
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                zip_bytes = export_adventure_zip(story)
                safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in story.title) or "adventure"
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{safe_title}.zip"')
                self.send_header("Content-Length", str(len(zip_bytes)))
                self.end_headers()
                self.wfile.write(zip_bytes)
                return
            if len(rest) == 3 and rest[1] == "cards" and rest[2] == "export":
                story = load_story(rest[0])
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                self._send_json(200, {"cards": export_story_cards_aidungeon(story)})
                return
            if len(rest) != 1:
                self._send_error_json(404, "Story not found")
                return
            story = load_story(rest[0])
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            self._send_json(200, {"story": story.to_dict()})
            return

        if not path.startswith("/api/"):
            self._serve_static(path)
            return

        self._send_error_json(404, "Unknown endpoint")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()
        except Exception as e:
            self._send_error_json(400, f"Invalid JSON body: {e}")
            return

        if path == "/api/llm/start":
            self._send_json(200, start_llm_server())
            return

        if path == "/api/llm/config":
            saved = save_endpoint_config(body)
            saved_url = str(saved.get("llm_url") or "").rstrip("/")
            _discovered_models_cache.pop(saved_url, None)
            _discovered_max_ctx_cache.pop(saved_url, None)
            _discovered_model_max_ctx.pop(saved_url, None)
            self._send_json(
                200,
                {
                    "config": public_endpoint_config(saved),
                    "status": check_llm_status(),
                },
            )
            return

        if path == "/api/llm/models":
            cur = _active_endpoint()
            probe_url = str(body.get("llm_url") or cur.get("llm_url") or LLM_URL).strip().rstrip("/")
            typed_key = str(body.get("api_key") or "").strip()
            use_key = typed_key or ("" if body.get("clear_api_key") else str(cur.get("api_key") or ""))
            try:
                req = urllib.request.Request(
                    _v1_url(probe_url, "/models"),
                    headers=_llm_headers(use_key),
                    method="GET",
                )
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    mdata = json.loads(resp.read().decode("utf-8", errors="replace"))
                    models = [str(m.get("id")) for m in (mdata.get("data") or []) if m.get("id")]
                    _discovered_models_cache[probe_url] = models
                    self._send_json(200, {"models": models[:100]})
            except Exception as e:
                self._send_error_json(502, f"Could not fetch models from {probe_url}: {e}")
            return

        if path == "/api/scripts/test":
            res = run_js_hook(
                hook=str(body.get("hook") or "input"),
                code=str(body.get("code") or ""),
                library=str(body.get("library") or ""),
                text=str(body.get("text") or ""),
                state=body.get("state") if isinstance(body.get("state"), dict) else {},
                info=body.get("info") if isinstance(body.get("info"), dict) else {"actionCount": 0, "memoryLength": 0, "maxChars": 320000},
                history=body.get("history") if isinstance(body.get("history"), list) else [],
                story_cards=body.get("story_cards") if isinstance(body.get("story_cards"), list) else [],
                quests=body.get("quests") if isinstance(body.get("quests"), list) else [],
            )
            self._send_json(200, res)
            return

        if path == "/api/scripts/install-community":
            kind = str(body.get("kind") or "")
            include_ac = bool(body.get("include_ac", False))
            try:
                sc = ensure_community_script(kind, include_ac=include_ac)
            except ValueError as e:
                self._send_error_json(400, str(e))
                return
            except Exception as e:
                self._send_error_json(502, str(e))
                return
            self._send_json(200, {"script": sc.to_dict()})
            return

        if path == "/api/scripts":
            name = str(body.get("name") or "").strip()
            if not name:
                self._send_error_json(400, "Script name is required")
                return
            sc = create_script(
                name=name,
                description=str(body.get("description") or ""),
                version=str(body.get("version") or "1.0"),
                library=str(body.get("library") or ""),
                input_code=str(body.get("input") or ""),
                context_code=str(body.get("context") or ""),
                output_code=str(body.get("output") or ""),
            )
            self._send_json(201, {"script": sc.to_dict()})
            return

        if path == "/api/scenarios/import":
            raw_obj = body.get("data") if isinstance(body.get("data"), dict) else body
            if not isinstance(raw_obj, dict) or not raw_obj:
                self._send_error_json(400, "Expected JSON object to import")
                return
            sc = import_aidungeon_json(raw_obj)
            self._send_json(201, {"scenario": sc.to_dict()})
            return

        if path == "/api/scenarios/import-url":
            url_or_id = str(body.get("url") or "").strip()
            if not url_or_id:
                self._send_error_json(400, "AI Dungeon scenario URL or shortId is required")
                return
            try:
                raw_obj = fetch_aidungeon_url_payload(url_or_id)
            except ValueError as e:
                self._send_error_json(400, str(e))
                return
            except Exception as e:
                self._send_error_json(502, f"Failed to fetch AI Dungeon scenario: {e}")
                return
            sc = import_aidungeon_json(raw_obj)
            self._send_json(201, {"scenario": sc.to_dict()})
            return

        if path == "/api/scenarios":
            name = str(body.get("name") or "").strip()
            scenario_type = str(body.get("scenario_type") or "story")
            opening = str(body.get("opening") or "").strip()
            choices = body.get("choices") if isinstance(body.get("choices"), list) else []
            if not name:
                self._send_error_json(400, "Scenario name is required")
                return
            if scenario_type == "multiple_choice" and not choices:
                self._send_error_json(400, "Add at least one choice for Multiple Choice scenarios")
                return
            sc = create_scenario(
                name=name,
                opening=opening,
                description=str(body.get("description") or ""),
                scenario_type=scenario_type,
                choices=choices,
                ai_instructions=str(body.get("ai_instructions") or ""),
                story_summary=str(body.get("story_summary") or ""),
                plot_essentials=str(body.get("plot_essentials") or ""),
                authors_note=str(body.get("authors_note") or ""),
                third_person=bool(body.get("third_person", False)),
                character_name=str(body.get("character_name") or ""),
                story_cards=body.get("story_cards") if isinstance(body.get("story_cards"), list) else None,
                builtin_script=body.get("builtin_script") if isinstance(body.get("builtin_script"), dict) else None,
                attached_scripts=body.get("attached_scripts") if isinstance(body.get("attached_scripts"), list) else None,
            )
            self._send_json(201, {"scenario": sc.to_dict()})
            return

        if path == "/api/stories":
            scenario_id = str(body.get("scenario_id") or "")
            title = body.get("title")
            choice_id = body.get("choice_id")
            placeholder_answers = (
                body.get("placeholder_answers")
                if isinstance(body.get("placeholder_answers"), dict)
                else None
            )
            selected_card_ids = (
                body.get("selected_card_ids")
                if isinstance(body.get("selected_card_ids"), list)
                else None
            )
            choice_path = (
                [str(x) for x in body.get("choice_path")]
                if isinstance(body.get("choice_path"), list)
                else None
            )
            try:
                story = create_story_from_scenario(
                    scenario_id=scenario_id,
                    title=title,
                    choice_id=str(choice_id) if choice_id else None,
                    choice_path=choice_path,
                    placeholder_answers=placeholder_answers,
                    selected_card_ids=[str(x) for x in selected_card_ids] if selected_card_ids else None,
                    quickstart=bool(body.get("quickstart", False)),
                    enable_inner_self=bool(body.get("enable_inner_self", False)),
                    enable_auto_cards=bool(body.get("enable_auto_cards", False)),
                )
            except RuntimeError as e:
                self._send_error_json(502, str(e))
                return
            if "plot_essentials" in body and body["plot_essentials"] is not None:
                story.plot_essentials = str(body["plot_essentials"])
            save_story(story)
            self._send_json(201, {"story": story.to_dict()})
            return

        parts = [p for p in path.split("/") if p]
        if len(parts) == 5 and parts[0] == "api" and parts[1] == "stories" and parts[3] == "cards" and parts[4] == "import":
            story_id = parts[2]
            raw_cards = body.get("cards") if isinstance(body.get("cards"), list) else (body if isinstance(body, list) else None)
            if raw_cards is None:
                self._send_error_json(400, "Expected JSON array of Story Cards")
                return
            with get_story_lock(story_id):
                story = load_story(story_id)
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                stats = import_story_cards_aidungeon(story, raw_cards)
                save_story(story)
            self._send_json(200, {"stats": stats, "story": story.to_dict()})
            return

        if len(parts) == 5 and parts[0] == "api" and parts[1] == "stories" and parts[3] == "cards" and parts[4] == "generate":
            self._handle_generate_story_card(parts[2], body)
            return

        if len(parts) == 4 and parts[0] == "api" and parts[1] == "stories":
            story_id, action = parts[2], parts[3]
            if action == "append":
                self._handle_append(story_id, body)
                return
            if action == "undo":
                self._handle_undo(story_id)
                return
            if action == "redo":
                self._handle_redo(story_id)
                return
            if action == "erase":
                self._handle_erase_last(story_id)
                return
            if action == "retry-cycle":
                raw_idx = body.get("variant_idx")
                v_idx = int(raw_idx) if raw_idx is not None else None
                self._handle_retry_cycle(story_id, int(body.get("direction", 1)), variant_idx=v_idx)
                return
            if action == "erase-to-here":
                self._handle_erase_to_here(story_id, str(body.get("seg_id") or ""))
                return
            if action == "generate":
                self._handle_generate_stream(story_id, body)
                return
            if action == "summarize":
                self._handle_summarize(story_id)
                return

        self._send_error_json(404, "Unknown endpoint")

    def do_PATCH(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            body = self._read_json_body()
        except Exception as e:
            self._send_error_json(400, f"Invalid JSON body: {e}")
            return

        if parts == ["api", "settings"]:
            raw_settings = body.get("settings") if isinstance(body.get("settings"), dict) else body
            merged = {**asdict(load_default_settings()), **raw_settings}
            saved = save_default_settings(StorySettings.from_dict(merged))
            self._send_json(200, {"settings": asdict(saved)})
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "scripts":
            script_id = parts[2]
            sc = load_script(script_id)
            if sc is None:
                self._send_error_json(404, "Script not found")
                return
            if "name" in body:
                name = str(body["name"]).strip()
                if not name:
                    self._send_error_json(400, "Script name cannot be empty")
                    return
                sc.name = name
            for fld in ("description", "version", "library", "input", "context", "output"):
                if fld in body:
                    setattr(sc, fld, str(body[fld]))
            save_script(sc)
            self._send_json(200, {"script": sc.to_dict()})
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "scenarios":
            scenario_id = parts[2]
            sc = load_scenario(scenario_id)
            if sc is None:
                self._send_error_json(404, "Scenario not found")
                return
            if "name" in body:
                name = str(body["name"]).strip()
                if not name:
                    self._send_error_json(400, "Scenario name cannot be empty")
                    return
                sc.name = name
            if "description" in body:
                sc.description = str(body["description"]).strip()
            if "scenario_type" in body and body["scenario_type"] in ("story", "multiple_choice", "character_creator"):
                sc.scenario_type = str(body["scenario_type"])
            if "opening" in body:
                sc.opening = str(body["opening"]).strip()
            if "choices" in body and isinstance(body["choices"], list):
                sc.choices = _normalize_choices_tree(body["choices"])
            if "ai_instructions" in body:
                sc.ai_instructions = str(body["ai_instructions"]).strip()
            if "story_summary" in body:
                sc.story_summary = str(body["story_summary"]).strip()
            if "plot_essentials" in body:
                sc.plot_essentials = str(body["plot_essentials"]).strip()
            if "authors_note" in body:
                sc.authors_note = str(body["authors_note"]).strip()
            if "third_person" in body:
                sc.third_person = bool(body["third_person"])
            if "character_name" in body:
                sc.character_name = str(body["character_name"]).strip()
            if "story_cards" in body and isinstance(body["story_cards"], list):
                sc.story_cards = [StoryCard.from_dict(c) for c in body["story_cards"]]
            if "builtin_script" in body and isinstance(body["builtin_script"], dict):
                sc.builtin_script = _normalize_builtin_script(body["builtin_script"])
            if "attached_scripts" in body and isinstance(body["attached_scripts"], list):
                sc.attached_scripts = _normalize_attached_scripts(body["attached_scripts"])
            save_scenario(sc)
            self._send_json(200, {"scenario": sc.to_dict()})
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "stories":
            story_id = parts[2]
            with get_story_lock(story_id):
                story = load_story(story_id)
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                if "title" in body:
                    story.title = str(body["title"]).strip() or "Untitled Adventure"
                if "description" in body:
                    story.description = str(body["description"]).strip()
                if "tags" in body and isinstance(body["tags"], list):
                    story.tags = [str(t).strip() for t in body["tags"] if str(t).strip()]
                if "ai_instructions" in body:
                    story.ai_instructions = str(body["ai_instructions"])
                elif "system_prompt" in body:
                    story.ai_instructions = str(body["system_prompt"])
                if "story_summary" in body:
                    story.story_summary = str(body["story_summary"])
                if "plot_essentials" in body:
                    story.plot_essentials = str(body["plot_essentials"])
                elif "memory" in body:
                    story.plot_essentials = str(body["memory"])
                if "authors_note" in body:
                    story.authors_note = str(body["authors_note"])
                if "third_person" in body:
                    story.third_person = bool(body["third_person"])
                if "character_name" in body:
                    story.character_name = str(body["character_name"]).strip()
                if "story_cards" in body and isinstance(body["story_cards"], list):
                    story.story_cards = [StoryCard.from_dict(c) for c in body["story_cards"]]
                if "builtin_script" in body and isinstance(body["builtin_script"], dict):
                    story.builtin_script = _normalize_builtin_script(body["builtin_script"])
                if "attached_scripts" in body and isinstance(body["attached_scripts"], list):
                    story.attached_scripts = _normalize_attached_scripts(body["attached_scripts"])
                if "script_state" in body and isinstance(body["script_state"], dict):
                    story.script_state = dict(body["script_state"])
                if "quests" in body and isinstance(body["quests"], list):
                    story.quests = list(body["quests"])
                if body.get("clear_logs"):
                    story.script_logs = []
                if "settings" in body and isinstance(body["settings"], dict):
                    merged = {**story.settings.__dict__, **body["settings"]}
                    story.settings = StorySettings.from_dict(merged)
                    if body.get("save_as_default"):
                        save_default_settings(story.settings)
                save_story(story)
            self._send_json(200, {"story": story.to_dict()})
            return

        if len(parts) == 5 and parts[0] == "api" and parts[1] == "stories" and parts[3] == "segments":
            story_id, seg_id = parts[2], parts[4]
            with get_story_lock(story_id):
                story = load_story(story_id)
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                target = next((s for s in story.segments if s.id == seg_id), None)
                if target is None:
                    self._send_error_json(404, "Segment not found")
                    return
                if "text" in body:
                    new_text = str(body["text"]).strip()
                    if new_text.lower() in ("/erase-to-here", "/eth"):
                        erase_to_here(story, seg_id)
                        save_story(story)
                        self._send_json(200, {"erased_to_here": True, "story": story.to_dict()})
                        return
                    push_undo_snapshot(story)
                    target.text = new_text
                if "kind" in body and body["kind"] in ("opening", "say", "do", "story", "ai"):
                    target.kind = str(body["kind"])
                save_story(story)
            self._send_json(200, {"story": story.to_dict()})
            return

        self._send_error_json(404, "Unknown endpoint")

    def do_DELETE(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]

        if parts == ["api", "settings"]:
            raw_settings = body.get("settings") if isinstance(body.get("settings"), dict) else body
            merged = {**asdict(load_default_settings()), **raw_settings}
            saved = save_default_settings(StorySettings.from_dict(merged))
            self._send_json(200, {"settings": asdict(saved)})
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "scripts":
            script_id = parts[2]
            deleted = delete_script(script_id)
            if not deleted:
                self._send_error_json(404, "Script not found")
                return
            self._send_json(200, {"deleted": True})
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "scenarios":
            scenario_id = parts[2]
            deleted = delete_scenario(scenario_id)
            if not deleted:
                self._send_error_json(404, "Scenario not found")
                return
            self._send_json(200, {"deleted": True})
            return

        if len(parts) == 3 and parts[0] == "api" and parts[1] == "stories":
            story_id = parts[2]
            with get_story_lock(story_id):
                deleted = delete_story(story_id)
            if not deleted:
                self._send_error_json(404, "Story not found")
                return
            self._send_json(200, {"deleted": True})
            return

        if len(parts) == 5 and parts[0] == "api" and parts[1] == "stories" and parts[3] == "memories":
            story_id, mem_id = parts[2], parts[4]
            with get_story_lock(story_id):
                story = load_story(story_id)
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                story.memories = [m for m in story.memories if m.id != mem_id]
                save_story(story)
            self._send_json(200, {"story": story.to_dict()})
            return

        if len(parts) == 5 and parts[0] == "api" and parts[1] == "stories" and parts[3] == "segments":
            story_id, seg_id = parts[2], parts[4]
            with get_story_lock(story_id):
                story = load_story(story_id)
                if story is None:
                    self._send_error_json(404, "Story not found")
                    return
                before = len(story.segments)
                push_undo_snapshot(story)
                story.segments = [s for s in story.segments if s.id != seg_id]
                if len(story.segments) == before:
                    story.undo_stack.pop()
                    self._send_error_json(404, "Segment not found")
                    return
                save_story(story)
            self._send_json(200, {"story": story.to_dict()})
            return

        self._send_error_json(404, "Unknown endpoint")

    def _count_tokens(self, text: str) -> tuple[int, bool]:
        if not text:
            return 0, True
        cfg = _active_endpoint()
        if not _is_llama_cpp(cfg):
            return max(1, (len(text) + 3) // 4), False
        active_url = str(cfg.get("llm_url") or LLM_URL).rstrip("/")
        try:
            req = urllib.request.Request(
                f"{active_url}/tokenize",
                data=json.dumps({"content": text}).encode("utf-8"),
                headers=_llm_headers(str(cfg.get("api_key") or "")),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return len(data.get("tokens") or []), True
        except Exception:
            return max(1, (len(text) + 3) // 4), False

    def _build_context_report(self, story: Story) -> dict[str, Any]:
        max_ctx = get_effective_max_context()
        report = inspect_story_context(story, max_context_limit=max_ctx)
        if max_ctx is not None:
            report["max_context"] = max_ctx
        exact = True
        total_tokens = 0
        for sec in report["sections"]:
            toks, is_exact = self._count_tokens(sec["text"])
            sec["tokens"] = toks
            exact = exact and is_exact
            total_tokens += toks
        report["total_tokens"] = total_tokens
        report["exact_tokens"] = exact
        return report

    def _handle_summarize(self, story_id: str) -> None:
        story = load_story(story_id)
        if story is None:
            self._send_error_json(404, "Story not found")
            return
        transcript = "\n\n".join(s.text for s in story.segments if s.text.strip())
        if not transcript:
            self._send_error_json(400, "Nothing to summarize yet.")
            return

        prompt_parts = []
        if story.story_summary.strip():
            prompt_parts.append(f"Existing summary:\n{story.story_summary.strip()}")
        prompt_parts.append(f"Story transcript:\n{transcript}")
        prompt_parts.append(
            "Write a concise, factual 3-5 sentence Story Summary capturing the key events, character goals, current location, and unresolved threads. Output only the summary."
        )

        cfg = _active_endpoint()
        active_url = str(cfg.get("llm_url") or LLM_URL).rstrip("/")
        api_key = str(cfg.get("api_key") or "")
        payload = _build_chat_payload(
            cfg,
            [
                {"role": "system", "content": "You summarize RPG adventures concisely and accurately."},
                {"role": "user", "content": "\n\n".join(prompt_parts)},
            ],
            stream=False,
            temperature=0.3,
            max_tokens=220,
            enable_thinking=False,
        )
        try:
            req = urllib.request.Request(
                _v1_url(active_url, "/chat/completions"),
                data=json.dumps(payload).encode("utf-8"),
                headers=_llm_headers(api_key),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                summary = (
                    ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                ).strip()
        except Exception as e:
            self._send_error_json(503, f"Could not summarize via LLM endpoint: {e}")
            return

        with get_story_lock(story_id):
            latest = load_story(story_id)
            if latest is None:
                self._send_error_json(404, "Story not found")
                return
            latest.story_summary = summary
            save_story(latest)

        self._send_json(200, {"story_summary": summary, "story": latest.to_dict()})

    def _dismiss_prior_script_message(self, story: Story) -> None:
        """Mark prior turn's state.message dismissed without deleting it from script_state.

        Community scripts such as Auto-Cards compare state.message against their
        own previous value across turns, so keeping script_state['message'] intact
        while recording the dismissed text prevents stale banners from reappearing.
        """
        msg = (
            story.script_state.get("message")
            if isinstance(story.script_state, dict)
            else None
        )
        story.dismissed_script_message = str(msg) if msg else None

    def _handle_append(self, story_id: str, body: dict[str, Any]) -> None:
        mode = str(body.get("mode") or "")
        raw_text = str(body.get("text") or "")
        if mode not in ("say", "do", "story"):
            self._send_error_json(400, "Mode must be one of: say, do, story")
            return
        if not raw_text.strip():
            self._send_error_json(400, "Text cannot be empty")
            return

        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            self._dismiss_prior_script_message(story)
            formatted = format_player_text(
                mode,
                raw_text,
                third_person=story.third_person,
                character_name=story.character_name,
            )
            hook_res = run_story_scripts(story, "input", formatted)
            mod_text = hook_res.get("text")
            if hook_res.get("stop") or mod_text is None or not str(mod_text).strip():
                save_story(story)
                self._send_json(
                    200,
                    {
                        "stopped": bool(hook_res.get("stop")),
                        "segment": None,
                        "story": story.to_dict(),
                    },
                )
                return

            seg = Segment(
                id=uuid.uuid4().hex[:10],
                kind=mode,
                text=str(mod_text).strip(),
                raw_input=raw_text.strip(),
            )
            push_undo_snapshot(story)
            story.segments.append(seg)
            save_story(story)

        self._send_json(200, {"segment": seg.__dict__, "story": story.to_dict()})

    def _handle_undo(self, story_id: str) -> None:
        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            changed = undo_story(story)
            if changed:
                save_story(story)
        self._send_json(200, {"undone": changed, "story": story.to_dict()})

    def _handle_redo(self, story_id: str) -> None:
        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            changed = redo_story(story)
            if changed:
                save_story(story)
        self._send_json(200, {"redone": changed, "story": story.to_dict()})

    def _handle_erase_last(self, story_id: str) -> None:
        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            erased = erase_last_segment(story)
            if erased:
                save_story(story)
        self._send_json(200, {"erased": erased, "story": story.to_dict()})

    def _handle_retry_cycle(
        self,
        story_id: str,
        direction: int = 1,
        variant_idx: int | None = None,
    ) -> None:
        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            changed = cycle_retry_variant(story, direction, variant_idx=variant_idx)
            if changed:
                save_story(story)
        self._send_json(200, {"changed": changed, "story": story.to_dict()})

    def _handle_generate_story_card(self, story_id: str, body: dict[str, Any]) -> None:
        story = load_story(story_id)
        if story is None:
            self._send_error_json(404, "Story not found")
            return
        title = str(body.get("title") or "").strip()
        card_type = str(body.get("card_type") or "Custom").strip()
        if not title:
            self._send_error_json(400, "Card title is required to generate an entry")
            return
        cmd_template = str(
            body.get("command")
            or f"Write a concise, factual 2-4 sentence RPG Story Card entry for {card_type} '{{{{title}}}}' consistent with the story context."
        ).strip()
        command = cmd_template.replace("{{title}}", title)
        context_bits = []
        if story.world_description.strip():
            context_bits.append(f"World Description:\n{story.world_description.strip()}")
        if story.plot_essentials.strip():
            context_bits.append(f"Plot Essentials:\n{story.plot_essentials.strip()}")
        recent = "\n\n".join(s.text for s in story.segments[-6:] if s.text.strip())
        if recent:
            context_bits.append(f"Recent Story:\n{recent}")
        context_bits.append(f"Card Type: {card_type}\nCard Name: {title}\nTask: {command}")
        try:
            entry = _call_llm_oneshot(
                "You create concise, evocative RPG Story Card entries without spoilers or meta commentary.",
                "\n\n".join(context_bits),
                max_tokens=220,
            )
        except Exception as e:
            self._send_error_json(502, f"Could not generate Story Card entry: {e}")
            return
        wrap = str(body.get("wrap") or "")
        if wrap == "{}" and entry and not (entry.startswith("{") and entry.endswith("}")):
            entry = f"{{{entry}}}"
        elif wrap == "[]" and entry and not (entry.startswith("[") and entry.endswith("]")):
            entry = f"[{entry}]"
        self._send_json(200, {"entry": entry})

    def _handle_erase_to_here(self, story_id: str, seg_id: str) -> None:
        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            erased = erase_to_here(story, seg_id)
            if erased > 0:
                save_story(story)
        self._send_json(200, {"erased": erased, "story": story.to_dict()})

    def _handle_generate_stream(self, story_id: str, body: dict[str, Any]) -> None:
        mode = body.get("mode")
        raw_text = str(body.get("text") or "")
        retry = bool(body.get("retry", False))
        retry_instructions = str(body.get("retry_instructions") or "").strip()

        with get_story_lock(story_id):
            story = load_story(story_id)
            if story is None:
                self._send_error_json(404, "Story not found")
                return
            self._dismiss_prior_script_message(story)

            user_seg: Segment | None = None
            input_stopped = False
            guide_text = ""
            previous_draft = ""
            prior_variants: list[str] = []
            if mode is not None and raw_text.strip():
                if mode not in ("say", "do", "story", "guide"):
                    self._send_error_json(400, "Mode must be one of: say, do, story, guide")
                    return
                if mode == "guide":
                    hook_res = run_story_scripts(story, "input", raw_text.strip())
                    if hook_res.get("stop"):
                        input_stopped = True
                        save_story(story)
                    else:
                        guide_text = str(hook_res.get("text") or raw_text).strip()
                else:
                    formatted = format_player_text(
                        str(mode),
                        raw_text,
                        third_person=story.third_person,
                        character_name=story.character_name,
                    )
                    hook_res = run_story_scripts(story, "input", formatted)
                    mod_text = hook_res.get("text")
                    if hook_res.get("stop"):
                        input_stopped = True
                        save_story(story)
                    elif mod_text is not None and str(mod_text).strip():
                        push_undo_snapshot(story)
                        user_seg = Segment(
                            id=uuid.uuid4().hex[:10],
                            kind=str(mode),
                            text=str(mod_text).strip(),
                            raw_input=raw_text.strip(),
                        )
                        story.segments.append(user_seg)
                        save_story(story)
                    else:
                        save_story(story)
            elif retry and story.segments and story.segments[-1].kind == "ai":
                push_undo_snapshot(story)
                popped = story.segments.pop()
                previous_draft = popped.text
                prior_variants = (
                    list(popped.variants)
                    if popped.variants
                    else ([popped.text] if popped.text.strip() else [])
                )
                save_story(story)

            context_stopped = False
            if not input_stopped:
                max_ctx = get_effective_max_context()
                plan = build_context_plan(
                    story,
                    apply_context_scripts=True,
                    bump_memory_uses=True,
                    guide_text=guide_text,
                    retry_instructions=retry_instructions,
                    previous_draft=previous_draft,
                    max_context_limit=max_ctx,
                )
                context_stopped = bool(plan.get("script_stop"))
                messages = plan["messages"]
                settings = story.settings
                story.last_generation_context = {
                    "context_limit": plan["context_limit"],
                    "sections": plan["sections"],
                    "triggered_cards": plan["triggered_cards"],
                    "used_memories": plan["used_memories"],
                    "warnings": plan.get("warnings", []),
                    "reserved_response_tokens": plan.get("reserved_response_tokens", settings.max_tokens),
                    "messages": messages,
                    "guide_text": guide_text,
                    "retry_instructions": retry_instructions,
                    "removed_context": [],
                    "captured_at": time.time(),
                }
                save_story(story)

        # Switch to SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        if input_stopped or context_stopped:
            if user_seg is not None:
                self._send_sse_event("user_segment", {"segment": user_seg.__dict__})
            self._send_sse_event("done", {"segment": None, "reasoning": "", "story": story.to_dict()})
            return

        if user_seg is not None:
            self._send_sse_event("user_segment", {"segment": user_seg.__dict__})
        elif retry:
            self._send_sse_event("story_sync", {"story": story.to_dict()})

        cfg = _active_endpoint()
        active_url = str(cfg.get("llm_url") or LLM_URL).rstrip("/")
        api_key = str(cfg.get("api_key") or "")
        chat_url = _v1_url(active_url, "/chat/completions")
        parsed = urllib.parse.urlparse(chat_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        req_path = (parsed.path or "/v1/chat/completions") + (f"?{parsed.query}" if parsed.query else "")

        payload = _build_chat_payload(
            cfg,
            messages,
            stream=True,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
            top_k=settings.top_k,
            repeat_penalty=settings.repeat_penalty,
            presence_penalty=settings.presence_penalty,
            frequency_penalty=settings.frequency_penalty,
            enable_thinking=settings.enable_thinking,
            reasoning_effort=settings.reasoning_effort,
        )

        is_continue = (
            user_seg is None
            and not retry
            and not guide_text.strip()
        )
        is_continue_ai = (
            is_continue
            and bool(story.segments)
            and story.segments[-1].kind == "ai"
            and not settings.raw_model_output
        )
        continue_recent = (
            [s.text for s in story.segments[-4:] if s.text.strip()]
            if is_continue_ai
            else []
        )
        prefix_flushed = not is_continue_ai
        pre_removed_sentences: list[str] = []

        conn: http.client.HTTPConnection | None = None
        collected_tokens: list[str] = []
        collected_reasoning: list[str] = []
        finish_reason: str | None = None
        client_disconnected = False

        def _flush_continue_prefix() -> None:
            nonlocal prefix_flushed, collected_tokens, pre_removed_sentences
            if prefix_flushed:
                return
            prefix_flushed = True
            raw_prefix = "".join(collected_tokens)
            cleaned_prefix, pre_removed = remove_repeated_leading_sentences(
                raw_prefix, continue_recent
            )
            if pre_removed:
                pre_removed_sentences.extend(pre_removed)
                collected_tokens = [cleaned_prefix] if cleaned_prefix else []
                out_tok = cleaned_prefix
            else:
                out_tok = raw_prefix
            if out_tok:
                self._send_sse_event("token", {"token": out_tok})

        try:
            conn_cls = (
                http.client.HTTPSConnection
                if parsed.scheme == "https"
                else http.client.HTTPConnection
            )
            conn = conn_cls(host, port, timeout=180)
            conn.request(
                "POST",
                req_path,
                body=json.dumps(payload).encode("utf-8"),
                headers=_llm_headers(api_key),
            )
            resp = conn.getresponse()
            if resp.status != 200:
                err_body = resp.read().decode("utf-8", errors="replace")
                self._send_sse_event(
                    "error",
                    {"message": f"LLM returned HTTP {resp.status}: {err_body[:300]}"},
                )
                return

            while True:
                raw_line = resp.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                if choices[0].get("finish_reason"):
                    finish_reason = choices[0].get("finish_reason")
                delta = choices[0].get("delta") or {}

                r_tok = delta.get("reasoning_content")
                if r_tok:
                    collected_reasoning.append(r_tok)
                    self._send_sse_event("reasoning", {"token": r_tok})

                tok = delta.get("content")
                if tok:
                    collected_tokens.append(tok)
                    if not prefix_flushed:
                        if len("".join(collected_tokens)) >= 100:
                            _flush_continue_prefix()
                    else:
                        self._send_sse_event("token", {"token": tok})

            if not prefix_flushed and collected_tokens:
                _flush_continue_prefix()

        except (BrokenPipeError, ConnectionResetError):
            client_disconnected = True
        except Exception as e:
            try:
                self._send_sse_event(
                    "error",
                    {
                        "message": (
                            f"Could not reach llama-server at {LLM_URL}: {e}. "
                            "Make sure serve-gemma4-26b-96k.sh is running."
                        )
                    },
                )
            except Exception:
                pass
            return
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        full_text = "".join(collected_tokens).strip()
        if full_text and finish_reason == "length" and not settings.raw_model_output:
            full_text = trim_incomplete_sentence(full_text)
        removed_sentences: list[str] = list(pre_removed_sentences)
        ai_seg: Segment | None = None
        if not client_disconnected:
            with get_story_lock(story_id):
                latest = load_story(story_id)
                if latest is not None:
                    if full_text and not latest.settings.raw_model_output:
                        recent_texts = [s.text for s in latest.segments[-4:] if s.text.strip()]
                        full_text, post_removed = remove_repeated_leading_sentences(
                            full_text, recent_texts
                        )
                        if post_removed:
                            removed_sentences.extend(post_removed)
                        if removed_sentences and isinstance(latest.last_generation_context, dict):
                            latest.last_generation_context["removed_context"] = removed_sentences
                    out_res = run_story_scripts(latest, "output", full_text)
                    final_out = out_res.get("text")
                    final_text = str(final_out).strip() if final_out is not None else ""
                    if final_text:
                        if user_seg is None:
                            push_undo_snapshot(latest)
                        variants = (prior_variants + [final_text]) if prior_variants else [final_text]
                        ai_seg = Segment(
                            id=uuid.uuid4().hex[:10],
                            kind="ai",
                            text=final_text,
                            variants=variants,
                            variant_idx=len(variants) - 1,
                        )
                        latest.segments.append(ai_seg)
                    save_story(latest)
                    story = latest
            if story.settings.auto_summarize or story.settings.memory_bank_enabled:
                threading.Thread(
                    target=_run_memory_maintenance,
                    args=(story_id,),
                    daemon=True,
                ).start()
        elif full_text:
            with get_story_lock(story_id):
                latest = load_story(story_id)
                if latest is not None:
                    ai_seg = Segment(
                        id=uuid.uuid4().hex[:10],
                        kind="ai",
                        text=full_text,
                    )
                    latest.segments.append(ai_seg)
                    save_story(latest)
                    story = latest

        if not client_disconnected:
            try:
                self._send_sse_event(
                    "done",
                    {
                        "segment": ai_seg.__dict__ if ai_seg else None,
                        "reasoning": "".join(collected_reasoning).strip(),
                        "story": story.to_dict(),
                    },
                )
            except (BrokenPipeError, ConnectionResetError):
                pass


def _call_llm_oneshot(system_prompt: str, user_prompt: str, max_tokens: int = 200) -> str:
    cfg = _active_endpoint()
    active_url = str(cfg.get("llm_url") or LLM_URL).rstrip("/")
    api_key = str(cfg.get("api_key") or "")
    payload = _build_chat_payload(
        cfg,
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        stream=False,
        temperature=0.3,
        max_tokens=max_tokens,
        enable_thinking=False,
    )
    req = urllib.request.Request(
        _v1_url(active_url, "/chat/completions"),
        data=json.dumps(payload).encode("utf-8"),
        headers=_llm_headers(api_key),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()


def _run_memory_maintenance(story_id: str) -> None:
    """
    Run Memory Bank (every 6 actions starting at 12, keeping newest 6 unsummarized)
    and Auto Summarization (every 15 actions) per AI Dungeon's Memory System spec.
    """
    story = load_story(story_id)
    if story is None:
        return
    n_segs = len(story.segments)

    # 1. Memory Bank: compress oldest unsummarized 6-segment chunk once >= 12 segments exist
    if story.settings.memory_bank_enabled:
        while n_segs - story.last_memory_bank_count >= 12:
            start = story.last_memory_bank_count
            end = start + 6
            chunk_text = "\n\n".join(s.text for s in story.segments[start:end] if s.text.strip())
            if not chunk_text:
                story.last_memory_bank_count = end
                continue
            try:
                mem_text = _call_llm_oneshot(
                    "Compress RPG events into a dense 1-3 sentence memory preserving specific names, items, locations, and promises.",
                    chunk_text,
                    max_tokens=160,
                )
            except Exception:
                break
            if mem_text:
                with get_story_lock(story_id):
                    latest = load_story(story_id)
                    if latest is None:
                        return
                    latest.memories.append(
                        MemoryItem(
                            id=uuid.uuid4().hex[:10],
                            text=mem_text,
                            start_idx=start,
                            end_idx=end,
                        )
                    )
                    latest.last_memory_bank_count = end
                    save_story(latest)
                    story = latest
            else:
                break

    # 2. Auto Summarization: update Story Summary every 15 actions
    if story.settings.auto_summarize and n_segs >= 15 and (n_segs - story.last_summarized_count >= 15):
        recent_slice = "\n\n".join(
            s.text for s in story.segments[story.last_summarized_count :] if s.text.strip()
        )
        parts = []
        if story.story_summary.strip():
            parts.append(f"Current Story Summary (incorporate user edits):\n{story.story_summary.strip()}")
        parts.append(f"New story events:\n{recent_slice}")
        parts.append(
            "Produce an updated, concise 3-5 sentence Story Summary capturing the overarching plot, goals, and key events."
        )
        try:
            new_summary = _call_llm_oneshot(
                "You summarize RPG adventures concisely and accurately.",
                "\n\n".join(parts),
                max_tokens=220,
            )
        except Exception:
            return
        if new_summary:
            with get_story_lock(story_id):
                latest = load_story(story_id)
                if latest is None:
                    return
                latest.story_summary = new_summary
                latest.last_summarized_count = len(latest.segments)
                save_story(latest)


def _get_tailscale_info() -> tuple[str | None, str | None]:
    """Return (tailscale_ipv4, tailscale_dns_name) if Tailscale CLI is connected."""
    ts_ip: str | None = None
    ts_dns: str | None = None
    try:
        out = subprocess.check_output(["tailscale", "ip", "-4"], timeout=2, stderr=subprocess.DEVNULL)
        lines = [line.strip() for line in out.decode("utf-8", errors="ignore").splitlines() if line.strip()]
        if lines:
            ts_ip = lines[0]
    except Exception:
        pass
    try:
        out = subprocess.check_output(["tailscale", "status", "--json"], timeout=2, stderr=subprocess.DEVNULL)
        data = json.loads(out.decode("utf-8", errors="ignore"))
        dns = str((data.get("Self") or {}).get("DNSName") or "").rstrip(".")
        if dns:
            ts_dns = dns
    except Exception:
        pass
    return ts_ip, ts_dns


def main() -> None:
    ensure_scenarios_dir()
    use_tailscale = "--tailscale" in sys.argv[1:] or os.environ.get("TAILSCALE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    bind_hosts: list[str] = [APP_HOST]
    ts_ip, ts_dns = _get_tailscale_info() if (use_tailscale or APP_HOST in {"0.0.0.0", "::"}) else (None, None)

    if use_tailscale and APP_HOST in {"127.0.0.1", "localhost"}:
        if not ts_ip:
            raise RuntimeError("TAILSCALE requested, but no Tailscale IPv4 address was found.")
        bind_hosts = [APP_HOST, ts_ip]

    servers: list[ThreadingHTTPServer] = []
    threads: list[threading.Thread] = []
    for host in bind_hosts:
        srv = RPGHTTPServer((host, APP_PORT), RPGRequestHandler)
        servers.append(srv)
        print(f"AI RPG Harness listening on http://{host}:{APP_PORT}", flush=True)

    if ts_ip and ("0.0.0.0" in bind_hosts or ts_ip in bind_hosts):
        print(f"Tailscale IP URL:  http://{ts_ip}:{APP_PORT}", flush=True)
    if ts_dns and ("0.0.0.0" in bind_hosts or ts_ip in bind_hosts):
        print(f"Tailscale DNS URL: http://{ts_dns}:{APP_PORT}", flush=True)
    print(f"Expecting llama-server at {LLM_URL}", flush=True)

    for srv in servers[1:]:
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        threads.append(t)

    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        for srv in servers:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    main()
