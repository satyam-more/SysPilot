# SysPilot

**Your computer's health, in plain language.**

SysPilot is a system health assistant for everyday users. Ask about your computer
in normal words and it inspects your machine — CPU, memory, battery, drivers,
startup apps, network, temperatures, disk health, and more — then explains what's
going on like a helpful friend, not a manual. When a fix would change your system,
nothing happens without your explicit approval.

Built on a self-hosted **Model Context Protocol (MCP)** server exposing 39 diagnostic
tools, SysPilot is designed to connect to **Alexa+** — Alexa+ handles the speech,
SysPilot does the diagnosing.

## Features

- **Plain-language diagnosis** — "Why is my computer slow?" returns a simple,
  jargon-free explanation of what's using your resources.
- **Safe-to-close guidance** — separates harmless background apps from system
  services you shouldn't touch.
- **Approval-gated fixes** — state-changing actions never run silently. SysPilot
  shows the exact command and waits for an Allow / Not now button. Commands that
  need admin rights are handed to you as copy-and-run text.
- **ChatGPT-style interface** — saved conversations, a conversation sidebar, and
  persistent chat history.
- **MCP server** — 39 read-only diagnostic tools plus approval-gated action tools,
  served over Streamable HTTP.

## Requirements

- Linux (tested on Ubuntu)
- Python 3.12+
- Node.js 18+ (to build the frontend)
- A free [Groq](https://console.groq.com) API key (for the tool-calling LLM)

## Setup

```bash
git clone https://github.com/satyam-more/SysPilot.git
cd SysPilot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Build the frontend:

```bash
cd frontend
npm install
npm run build
cd ..
```

For development/testing dependencies:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## Run

**Desktop app (recommended):**

```bash
.venv/bin/python desktop.py
```

**Or run the backend and open the UI in a browser:**

```bash
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
# then open http://127.0.0.1:8000
```

Add your Groq API key on the app's **Settings** page, then ask questions like
"Is my computer healthy?" or "Which apps can I safely close?"

## Tests

```bash
.venv/bin/python -m pytest -q
```

## Architecture

```
Alexa+ (speech)  ─┐
                  ├─▶  MCP server (/mcp, Streamable HTTP)  ─▶  39 diagnostic tools  ─▶  your system
Desktop app (UI) ─┘                                          └─▶  approval-gated actions
```

- **Backend:** Python, FastAPI, MCP Python SDK, uvicorn
- **Agent:** tool-calling LLM via the Groq API — every factual claim comes from a
  real tool call
- **Frontend:** React + TypeScript (Vite), packaged as a desktop app with pywebview
- **Storage:** SQLite, under `~/.config/syspilot/`

## Configuration

The app creates `~/.config/syspilot/` at runtime for local storage. This directory
lives outside the repository and is never tracked by Git.

## Team

- Satyam More
- Omkar Bodhgire
- Srushti Mali

## License

[MIT](LICENSE)
