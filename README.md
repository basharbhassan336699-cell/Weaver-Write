# Weaver Write

Automated Arabic/English academic research system — writes research, reports,
assignments, projects, and presentations with real citations, humanized text,
and correct RTL/LTR formatting.

Runs on a **single AI API key**. Works on Termux (Android), Windows
(PowerShell/Terminal), macOS, and Linux.

---

## Quick install

### Termux (Android) / Linux / macOS
```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USERNAME/weaver-write/main/install.sh | bash
```
or manually:
```bash
git clone https://github.com/YOUR_USERNAME/weaver-write.git
cd weaver-write
bash install.sh
```

### Windows (PowerShell)
```powershell
irm https://raw.githubusercontent.com/YOUR_USERNAME/weaver-write/main/install.ps1 | iex
```
or manually:
```powershell
git clone https://github.com/YOUR_USERNAME/weaver-write.git
cd weaver-write
.\install.ps1
```

---

## Commands

| Command | What it does |
|---------|--------------|
| `weaver install` | Quick setup, or restore a previous account |
| `weaver install-deps` *(or `bash install-deps.sh`)* | Install/repair all tool libraries |
| `weaver keys add` | Add your AI API key |
| `weaver keys change` | Change the API key |
| `weaver keys show` | Show stored keys (masked) |
| `weaver keys remove` | Remove a key |
| `weaver serve` | Start the local web UI |
| `weaver restore` | Restore state after the device was shut down |
| `weaver doctor` | Diagnose problems and suggest fixes |
| `weaver version` | Show version |

### Gateway (always-on service)
```bash
bash gateway.sh start      # start the web UI service
bash gateway.sh stop
bash gateway.sh restart
bash gateway.sh status
```

---

## API key

Weaver Write runs the whole system on **one** AI key (Anthropic / OpenAI /
DeepSeek / custom). Academic search (PaperQA) uses local multilingual
embeddings, so **no second key is required**.

```bash
weaver keys add       # add a key
weaver keys change    # change it
```

Keys are stored privately in `~/.weaver-write/keys.json` (chmod 600).

---

## Optional services (free, no key)

- **SearXNG** (web search): set `WEAVER_SEARXNG_URL` to your instance.
- **Tesseract** (OCR for scanned files): installed automatically where possible.
- **Node.js** (html2pptx): installed automatically where possible.

---

## Web interface

After setup, the CLI prints your local web URL:

```
http://127.0.0.1:8848
```

Start it any time with `weaver serve` (or `gateway.sh start`).

---

## Providers & key sync

Weaver Write supports 17 providers (Anthropic, OpenAI, DeepSeek, Groq,
OpenRouter, NVIDIA, xAI, Perplexity, Google, Together, Fireworks, Cerebras…)
with automatic platform detection from your key's prefix.

The API key is kept in `config/.env` as the single source of truth, so it
stays in sync between the terminal and the web UI:
- Change it in the terminal (`weaver keys change`) → the web UI shows the new key.
- Change it in the web UI → the terminal picks it up (`weaver restore` or next start).

Add a custom provider by editing `config/providers.json` (copy from
`config/providers.json.example`).

### Connect a provider outside the list
Both the terminal and the web UI let you connect ANY OpenAI-compatible
platform by entering its base URL and API key. Weaver Write auto-detects the
platform's available models so you can pick one:

Terminal:
```
weaver keys add   →  choose "Other / custom"  →  enter URL + key  →  pick a model
```
The choice is written to config/.env, so it's instantly shared with the web UI
(and vice-versa).

---

## Web interface

The web UI (`web/index.html`) is served by `web/server.py` and shares the same
`config/.env` as the terminal, so the API key/provider/model stay in sync both
ways. It supports English/Arabic with RTL, a chat view, and settings panels
(account, capabilities, memory, plugins).

```bash
weaver serve            # start at http://127.0.0.1:8848
# or
bash gateway.sh start
```

API endpoints (all local, 127.0.0.1 only):
`GET /api/settings`, `POST /api/settings`, `GET /api/status`,
`GET /api/providers`, `POST /api/providers/models`,
`POST /api/providers/custom`.
