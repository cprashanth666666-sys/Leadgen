"""Local server for the pipeline interface. Binds to 127.0.0.1 only.

Run: python ui/server.py   then open http://127.0.0.1:8765
Workspaces live in data/<client>/workspace.json. Files live in docs/<client>/.
Nothing here sends a message to a lead.
"""
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "agents"))
import storage_agent as agent  # noqa: E402

PORT = 8765
DATA = ROOT / "data"
DOCS = ROOT / "docs"
MAX_BODY = 30 * 1024 * 1024
SLUG = re.compile(r"^[a-z0-9-]{1,60}$")


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status, self.message = status, message


def load_env():
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#") and value.strip():
                os.environ.setdefault(key.strip(), value.strip())


def slug(value):
    if not SLUG.match(value or ""):
        raise ApiError(400, "Invalid client name")
    return value


def workspace_path(client):
    return DATA / slug(client) / "workspace.json"


def client_files(client):
    folder = DOCS / slug(client)
    if not folder.is_dir():
        return []
    return [
        {"path": path.relative_to(folder).as_posix(), "bytes": path.stat().st_size}
        for path in sorted(folder.rglob("*")) if path.is_file()
    ]


def firecrawl(path, payload):
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise ApiError(424, "FIRECRAWL_API_KEY is not set in .env")
    request = urllib.request.Request(
        "https://api.firecrawl.dev/v1/" + path,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ApiError(502, f"Firecrawl returned {error.code}") from error
    except urllib.error.URLError as error:
        raise ApiError(502, f"Could not reach Firecrawl: {error.reason}") from error


def ingest(url):
    if not re.match(r"^https?://", url or ""):
        raise ApiError(400, "Enter a full URL starting with https://")
    data = firecrawl("scrape", {"url": url, "formats": ["markdown"], "onlyMainContent": True}).get("data") or {}
    meta = data.get("metadata") or {}
    facts = [
        {"key": label, "value": meta[field], "source": url, "tag": "sourced"}
        for label, field in (("Page title", "title"), ("Description", "description"))
        if meta.get(field)
    ]
    return {"facts": facts, "excerpt": (data.get("markdown") or "")[:4000]}


def hunt(query):
    if not (query or "").strip():
        raise ApiError(400, "Enter a search")
    rows = firecrawl("search", {"query": query, "limit": 10}).get("data") or []
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "description": r.get("description", "")} for r in rows]


def store(client):
    paths = [p for p in (workspace_path(client), DOCS / client) if p.exists()]
    if not paths:
        raise ApiError(404, "This client has nothing to store yet")
    return agent.store(client, paths)


def retrieved_folder(name):
    if not agent.NAME_RE.match(name or ""):
        raise ApiError(400, "Invalid archive name")
    return DATA / "retrieved" / name[:-4]


def retrieve(name):
    folder = retrieved_folder(name)
    if folder.exists():
        files = sum(1 for path in folder.rglob("*") if path.is_file())
        return {"files": files, "location": str(folder), "already_extracted": True}
    return agent.retrieve(name, folder)


def restore(name, client):
    """Load a workspace from an extracted archive, keeping the current one as a backup."""
    source = retrieved_folder(name) / "data" / slug(client) / "workspace.json"
    if not source.is_file():
        raise ApiError(404, "Retrieve this archive first. It must contain this client's workspace.")
    workspace = json.loads(source.read_text(encoding="utf-8"))
    target = workspace_path(client)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists():
        backup = target.with_name("workspace.before-restore.json")
        shutil.copyfile(target, backup)
    write_json(target, workspace)
    return {"workspace": workspace, "backup": str(backup) if backup else None}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(part, path)


class Handler(BaseHTTPRequestHandler):
    server_version = "Leadgen"

    def log_message(self, *_):
        pass

    def _send(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, value, status=200):
        self._send(status, json.dumps(value, ensure_ascii=False).encode())

    def _raw_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ApiError(413, "File is larger than the 30 MB limit")
        return self.rfile.read(length)

    def _body(self):
        try:
            return json.loads(self._raw_body() or b"{}")
        except ValueError as error:
            raise ApiError(400, "Body is not valid JSON") from error

    def _guard(self, mutating):
        # Blocks other websites from driving this server through the browser.
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            raise ApiError(403, "Local access only")
        if mutating and self.headers.get("X-Leadgen") != "1":
            raise ApiError(403, "Missing request header")

    def _dispatch(self, handler, mutating):
        try:
            self._guard(mutating)
            handler()
        except ApiError as error:
            self._json({"error": error.message}, error.status)
        except agent.StorageError as error:
            self._json({"error": str(error)}, 409)
        except OSError as error:
            self._json({"error": f"File error: {error.strerror or error}"}, 500)

    def do_GET(self):
        self._dispatch(self._get, False)

    def do_POST(self):
        self._dispatch(self._post, True)

    def do_PUT(self):
        self._dispatch(self._put, True)

    def _get(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/":
            self._send(200, (ROOT / "ui" / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/status":
            self._json({"drive": agent.status(), "firecrawl": bool(os.environ.get("FIRECRAWL_API_KEY"))})
        elif url.path == "/api/clients":
            names = sorted(p.parent.name for p in DATA.glob("*/workspace.json")) if DATA.is_dir() else []
            self._json(names)
        elif url.path == "/api/workspace":
            path = workspace_path(query.get("client"))
            if not path.is_file():
                raise ApiError(404, "No such client")
            self._send(200, path.read_bytes())
        elif url.path == "/api/files":
            self._json(client_files(query.get("client")))
        elif url.path == "/api/archives":
            self._json(agent.list_archives(slug(query["client"]) if query.get("client") else None))
        else:
            raise ApiError(404, "Not found")

    def _post(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path == "/api/upload":
            name = Path(query.get("name") or "").name
            if not name or name.startswith("."):
                raise ApiError(400, "Invalid file name")
            target = DOCS / slug(query.get("client")) / "uploads" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self._raw_body())
            self._json({"path": "uploads/" + name})
            return
        body = self._body()
        if url.path == "/api/store":
            self._json(store(slug(body.get("client"))))
        elif url.path == "/api/retrieve":
            self._json(retrieve(body.get("name")))
        elif url.path == "/api/restore":
            self._json(restore(body.get("name"), body.get("client")))
        elif url.path == "/api/ingest":
            self._json(ingest(body.get("url")))
        elif url.path == "/api/hunt":
            self._json(hunt(body.get("query")))
        else:
            raise ApiError(404, "Not found")

    def _put(self):
        url = urllib.parse.urlparse(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        if url.path != "/api/workspace":
            raise ApiError(404, "Not found")
        write_json(workspace_path(query.get("client")), self._body())
        self._json({"saved": True})


if __name__ == "__main__":
    load_env()
    print(f"Leadgen pipeline: http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
