# TrailBack

A local AI memory assistant that tracks your activity across files, terminal, and documents, then answers questions about what you were working on.

## Requirements

- Ubuntu 22.04+
- Python 3.12+
- [Ollama](https://ollama.com) with `qwen2.5:3b` pulled

## Setup

```bash
git clone https://github.com/satyam-more/TrailBack.git
cd TrailBack
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For development:
```bash
pip install -r requirements.txt -r requirements-dev.txt
```

## Run

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload
```

## Configuration

The app creates `~/.config/trailback/` at runtime. This directory is outside the repository and is never tracked by Git.
