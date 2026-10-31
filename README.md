# Leadgen pipeline

A local tool with five sequential pages: Client, Documents, Target profiles, Lead hunt, Conversations. Each page unlocks when the one before it is complete. It never sends a message. You approve each message, send it yourself, then log the result.

## Run

```
python ui/server.py
```

Open http://127.0.0.1:8765. The server uses only the Python standard library and accepts local connections only.

Opening `ui/index.html` directly also works, but saves to that browser only and has no file, site-reading or Drive features.

## Storage

`agents/storage_agent.py` zips a client's workspace and files, tests the zip, and copies it to Google Drive with a hash check. Retrieving copies the zip back, extracts it to `data/retrieved/`, checks every file and removes the temporary zip.

Drive is reached through a folder synced by Google Drive for Desktop. The default is `G:\My Drive\Leadgen`. Set `GDRIVE_FOLDER` in the environment to use another path. If the folder is missing, zips wait in `data/outbox/` and move on the next store.

```
python agents/storage_agent.py status
python -m unittest discover tests
```

## Keys

Copy `.env.example` to `.env`. `FIRECRAWL_API_KEY` enables Read site and web search. Everything else works without it.

## What stays out of git

`docs/`, `data/` and all spreadsheets, CSVs and zips are ignored, because this repo is public. Client scoring weights and message rules live in each client's workspace, not in code.
