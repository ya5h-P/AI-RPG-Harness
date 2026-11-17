# AI RPG Harness

A local, self-hosted interactive fiction & AI RPG web application modeled after AI Dungeon's core gameplay loop—with zero Python third-party dependencies, full desktop and mobile web UI, nested Multiple Choice scenarios, Character Creator, Story Cards, dynamic memory & context budgeting, JavaScript scripting hooks, and one-command Tailscale mobile access.

> **Disclosure:** All of the code in this repository was generated with AI assistance.
> **Security Note:** This app has no authentication and runs JavaScript scenario scripts via Node.js `vm`. Run it only on `localhost` or a private network (such as Tailscale), and only execute scripts you trust.

---

## Features

- **Home Hub (`Adventures` & `Scenarios`)**: Clean 2-tab start page to resume adventures or browse, play, create, edit, and import scenarios.
- **4 Input Modes**: Compact collapsible pill switcher (`Do`, `Say`, `Story`, `Guide`) plus `Send` (streams SSE generation) and `+ Add` (appends beats without triggering generation yet).
- **Turn Editing & Retry Variants**:
  - `Undo` / `Redo`, `Continue`, `Erase`, `Retry`, and `Retry with changes`.
  - Smooth horizontal **swipe carousel** on mobile (`‹` / `›` on desktop) to switch between Retry generations.
  - Hover (desktop) or tap (mobile) any message to **Edit**, **Delete**, **Erase to Here**, **Change Name** (Third Person), or **View Context**.
- **Scenario Engine**:
  - **Story** scenarios with `${placeholder}` prompts and Third Person mode.
  - **Deep Nested Multiple Choice** trees with recursive inheritance of Story Cards, Scripts, Plot fields, and leaf option titles.
  - **Character Creator** with **Quickstart** (auto-rolled profile + cards) and a step-by-step Name / Gender / Card Category wizard.
  - **Scenario Importer**: Import from `play.aidungeon.com` Scenario URLs (via optional Playwright) or exported `metadata.json` / `.json` files.
- **Plot, Memory & Context Inspector**:
  - Dedicated **Adventure** (`Plot`, `Cards`, `Scripts`, `Details`) and **AI Settings** tabs; AI Settings persist globally in `settings.json` across new adventures.
  - Keyword-triggered & pinned **Story Cards** (`.json` import/export + AI entry generation).
  - Automatic **Story Summarization** (every 15 actions) & **Memory Bank** retrieval (every 6 actions).
  - **View Context** modal with proportional token-usage bar, `Context Warning` notices, `Removed Context` deduplication log, and Memory Bank Explorer.
  - **Scripting API**: Sandboxed Node.js `input`, `context`, and `output` modifier hooks (`Built-in` + up to 10 reusable scripts per story).
  - **Backups**: Export any adventure as a `.zip` archive (`Adventure` tab → `Details`).

---

## Requirements

- **Python 3.10+** (uses only the Python standard library — no `pip install` needed)
- **Node.js 18+** (used for JS scripting hooks and optional scenario URL import)
- **An OpenAI-compatible local LLM server**, such as:
  - [`llama.cpp`](https://github.com/ggml-org/llama.cpp) (`llama-server`)
  - Ollama, LM Studio, or vLLM
- *(Optional, for importing `play.aidungeon.com` URLs directly)*: Playwright + Firefox (`npm install && npx playwright install firefox`)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/ya5h-P/AI-RPG-Harness.git
cd AI-RPG-Harness
chmod +x start.sh
```

### 2. Optional: Enable `play.aidungeon.com` URL imports

If you only write scenarios locally or import `.json` files, you can skip this step. To import public scenarios directly by URL:

```bash
npm install
npx playwright install firefox
```

### 3. Start an OpenAI-compatible LLM server

Start your local model server (default expected address: `http://127.0.0.1:8080`). Example with `llama.cpp`:

```bash
llama-server -m /path/to/model.gguf --port 8080 -c 32768
```

*(If you use Ollama on `:11434` or LM Studio on `:1234`, set `LLM_URL` when starting—see Configuration below.)*

---

## Running the App

### Desktop (Local Only)

```bash
./start.sh
```

Open **http://127.0.0.1:7860** in your browser. Look for the green dot in the top-left corner—hovering it shows the connected model name.

### Play from Your Phone (Tailscale)

Make sure [Tailscale](https://tailscale.com/) is connected on both your host machine and phone, then run:

```bash
./start.sh --tailscale
```

`start.sh` prints your Tailscale IP URL (for example `http://100.x.y.z:7860`) and MagicDNS URL (`http://<hostname>.ts.net:7860`). Open either URL on your phone browser.

### Background Management Commands

```bash
./start.sh --bg --tailscale   # Run detached in background (writes logs/server.log)
./start.sh status             # Show LLM server, Web UI health, and phone URL
./start.sh stop               # Stop background Web UI server
./start.sh test               # Run the full automated unit test suite
./start.sh --help             # Show CLI options and environment variables
```

---

## Usage Guide

### 1. Starting & Playing an Adventure

- **Home Screen**: Switch between **Adventures** (saved stories) and **Scenarios** (starter templates, custom scenarios, or imported scenarios).
- **Modes** (tap/click the mode pill at bottom-left to expand `← Do | Say | Story | Guide`):
  - **Do** (`Alt+1`): Character actions, automatically formatted (`you` → `You <action>.`, or Third Person `<Name> <action>.`) and marked with `>` in AI context.
  - **Say** (`Alt+2`): Character dialogue (`You say, "<dialogue>"`).
  - **Story** (`Alt+3`): Direct inline narrative text without action formatting.
  - **Guide** (`Alt+4`): Temporary out-of-character GM instruction for the next AI turn only.
- **Send vs `+ Add`**:
  - **Send** adds your input and immediately streams the AI response (`Enter` sends; `Shift+Enter` inserts a newline).
  - **`+ Add`** appends your formatted turn to the feed *without* triggering generation yet so you can stack multiple beats before pressing **▶ Continue** or **Send**.
- **Top-Right Controls**: `↶ Undo`, `↷ Redo`, `🔍 Context` (inspect prompt tokens & warnings), and `⚙ Settings`.

### 2. Mobile Controls & Gestures

- **Tap any message** in the story feed to open its inline toolbar (`Edit`, `Delete`, `Erase to Here`, `View Context`, `Change Name`); tap again or tap outside to close. *(On desktop, hover over any message instead.)*
- **Swipe sideways** on the latest AI response when multiple Retry generations exist to glide smoothly between variants.

### 3. Settings (`Adventure` & `AI Settings`)

Click **`⚙ Settings`** in the top-right during any adventure:

- **Adventure Tab**:
  - **Plot**: `AI Instructions`, `Story Summary` (with manual `✨ Auto-Summarize`), `Plot Essentials`, `Author's Note`, and `Third Person` toggle/name.
  - **Cards**: Create, search, filter, pin, AI-generate entries, or import/export AI Dungeon Story Card `.json` files.
  - **Scripts**: Toggle built-in JS hooks or attach up to 10 reusable scripts with a live test runner & console log.
  - **Details**: Edit title/description/tags and download a full `.zip` backup.
- **AI Settings Tab**:
  - Tune **Model Settings** (`Context Length`, `Response Length`, `Temperature`, `Top P`, `Top K`, `Repetition / Presence / Frequency Penalty`) and **Memory & Output** (`Auto Summarization`, `Memory Bank`, `Raw Model Output`, `Follow latest text`, `Enable Gemma Thinking Mode`).
  - Changes inside `AI Settings` **auto-save immediately** to the active story *and* persist globally to `settings.json` for all future adventures.

### 4. Switching Models & Providers (Local or Cloud)

Click **`🔌 Model`** in the **top-right of the Home page** (or click the status dot anytime) to switch between any local or OpenAI-compatible remote endpoint without restarting:

- **Base URI**: e.g., `http://127.0.0.1:8080` (`llama-server`), `http://127.0.0.1:11434/v1` (Ollama), `http://127.0.0.1:1234/v1` (LM Studio), `https://openrouter.ai/api/v1`, or `https://api.openai.com/v1`
- **API Key**: Optional (`Authorization: Bearer ...` header); masked on read and saved locally in `settings.json`
- **Model Name**: Automatically populated if the server offers 1 model, or selectable via `↻ Fetch` when multiple models are available

---

## Configuration (Environment Variables)

| Variable | Default | Description |
|---|---|---|
| `PORT` | `7860` | Web UI HTTP port |
| `HOST` | `127.0.0.1` | Bind host (`0.0.0.0` for LAN, or pass `--tailscale`) |
| `LLM_URL` | `http://127.0.0.1:8080` | Default Base URI of your OpenAI-compatible LLM server |
| `LLM_API_KEY` | *(optional)* | Default Bearer API key for remote OpenAI-compatible providers |
| `LLM_MODEL` | *(auto)* | Default model name override |
| `LLM_PORT` | `8080` | Port checked by `start.sh` when using default `LLM_URL` |
| `LLAMA_SERVE_SCRIPT` | *(optional)* | Path to a local bash script launched when clicking `Start LLM` or running `start.sh` while LLM is offline |
| `TAILSCALE` | `0` | Set to `1` to bind Tailscale IP automatically |

---

## Running Tests

No live LLM server is required; the suite uses local mock HTTP servers in isolated temporary directories:

```bash
./start.sh test
# or directly:
python3 -m unittest -v test_harness.py
```

---

## Project Structure

```text
.
├── server.py                # Stdlib HTTP/SSE server & OpenAI-compatible LLM proxy
├── harness.py               # Data models, scenario/choice inheritance, context planner, memory & dedup
├── script_runner.py         # Sandboxed Node.js modifier runner (input / context / output hooks)
├── aidungeon_importer.mjs   # Optional Playwright scraper for play.aidungeon.com scenarios
├── start.sh                 # Launcher, Tailscale binding, background control, status & test runner
├── test_harness.py          # Automated unit & API test suite
├── package.json             # Optional Playwright dependency manifest
└── static/
    ├── index.html           # Single-page app shell & modals
    ├── style.css            # Responsive desktop & mobile styling
    └── app.js               # Client state, SSE streaming, swipe carousel & editors
```

---

## License

[MIT](LICENSE)
