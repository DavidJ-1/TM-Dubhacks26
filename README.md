# TM DubHacks 2026

Starter for DubHacks 2026. The idea and the stack will change. This is just enough structure to start adding code.

## Layout

```
.
├── .env.example    # variable names only, no real secrets
├── .gitignore
├── README.md
└── src/            # application code goes here
```

## Setup

```bash
cp .env.example .env
```

Put real values in `.env` on your machine. Git ignores that file, so it stays off GitHub.

## Secrets

API keys belong in `.env`. Commit `.env.example` with the names and blank values so other people know what to set. Never paste a real key into a file that gets committed, a README, or a chat log.

If a key does end up in git history, delete it from the provider and issue a new one. Rewriting the commit does not un-leak a key that was already pushed.

## Status

More to come.
