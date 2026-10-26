# VeriAgent

Multi-agent research and fact-verification system that investigates claims, verifies citations deterministically against stored page snapshots, checks source independence, and reports calibrated verdicts (`SUPPORTED`, `REFUTED`, `MIXED`, `CONDITIONAL`, `INSUFFICIENT`).

## Quickstart

```bash
cp .env.example .env
cd backend && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd ..
make lint
make test