"""Storage agent: zip before storing on Google Drive, extract on retrieve.

The Drive target is a folder synced by Google Drive for Desktop, set with
GDRIVE_FOLDER (default G:\\My Drive\\Leadgen). If the folder is not reachable,
store() keeps the verified zip in data/outbox and reports it as queued, never
as stored. The next store() moves anything queued.

CLI:
  python agents/storage_agent.py status
  python agents/storage_agent.py store --client client-name path [path ...]
  python agents/storage_agent.py list
  python agents/storage_agent.py retrieve archive.zip --to some/new/folder
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
OUTBOX = ROOT / "data" / "outbox"
DEFAULT_DRIVE = Path(r"G:\My Drive\Leadgen")
MANIFEST = "manifest.json"
MAX_EXTRACTED_BYTES = 2 * 1024**3
NAME_RE = re.compile(r"^[a-z0-9-]{1,60}_\d{8}-\d{6}(-\d+)?\.zip$")


class StorageError(Exception):
    pass


def drive_folder():
    return Path(os.environ.get("GDRIVE_FOLDER") or DEFAULT_DRIVE)


def drive_available():
    folder = drive_folder()
    try:
        return folder.is_dir() or folder.parent.is_dir()
    except OSError:
        return False


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect(paths, base):
    files = []
    for raw in paths:
        path = Path(raw).resolve()
        if path.is_dir():
            files += [p for p in sorted(path.rglob("*")) if p.is_file()]
        elif path.is_file():
            files.append(path)
        else:
            raise StorageError(f"Not found: {raw}")
    if not files:
        raise StorageError("Nothing to store")
    pairs = {}
    for file in files:
        try:
            arcname = file.relative_to(base).as_posix()
        except ValueError:
            arcname = file.name
        pairs[arcname] = file
    return pairs


def compress(paths, zip_path, base=ROOT):
    """Write a zip with a hash manifest, then test it. Returns a summary."""
    pairs = _collect(paths, Path(base).resolve())
    if MANIFEST in pairs:
        raise StorageError(f"{MANIFEST} is a reserved name")
    zip_path = Path(zip_path)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    hashes = {name: _sha256(path) for name, path in pairs.items()}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in pairs.items():
            archive.write(path, name)
        archive.writestr(MANIFEST, json.dumps(hashes, indent=1))
    with zipfile.ZipFile(zip_path) as archive:
        bad = archive.testzip()
    if bad:
        zip_path.unlink()
        raise StorageError(f"Zip failed its check on {bad}")
    return {
        "files": len(pairs),
        "original_bytes": sum(path.stat().st_size for path in pairs.values()),
        "zip_bytes": zip_path.stat().st_size,
    }


def _copy_verified(source, target):
    part = target.with_name(target.name + ".part")
    shutil.copyfile(source, part)
    if _sha256(part) != _sha256(source):
        part.unlink(missing_ok=True)
        raise StorageError(f"Copy of {source.name} did not match the original")
    os.replace(part, target)


def _flush_outbox():
    moved = []
    if not OUTBOX.is_dir() or not drive_available():
        return moved
    folder = drive_folder()
    folder.mkdir(parents=True, exist_ok=True)
    for queued in sorted(OUTBOX.glob("*.zip")):
        _copy_verified(queued, folder / queued.name)
        queued.unlink()
        moved.append(queued.name)
    return moved


def _archive_name(client):
    if not re.fullmatch(r"[a-z0-9-]{1,60}", client):
        raise StorageError("Client must use lowercase letters, numbers and hyphens")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name, counter = f"{client}_{stamp}.zip", 1
    taken = lambda n: (OUTBOX / n).exists() or (drive_folder() / n).exists()
    while taken(name):
        name, counter = f"{client}_{stamp}-{counter}.zip", counter + 1
    return name


def store(client, paths, base=ROOT):
    """Compress, verify, then copy to Drive. Queues locally if Drive is away."""
    name = _archive_name(client)
    queued = OUTBOX / name
    summary = compress(paths, queued, base)
    summary["name"] = name
    summary["flushed"] = _flush_outbox()
    if queued.exists():
        summary["state"] = "queued"
        summary["location"] = str(queued)
    else:
        summary["state"] = "stored"
        summary["location"] = str(drive_folder() / name)
    return summary


def list_archives(client=None):
    rows = []
    sources = [("queued", OUTBOX)]
    if drive_available() and drive_folder().is_dir():
        sources.append(("stored", drive_folder()))
    for state, folder in sources:
        if not folder.is_dir():
            continue
        for path in folder.glob("*.zip"):
            if NAME_RE.match(path.name) and (not client or path.name.startswith(client + "_")):
                stat = path.stat()
                rows.append({"name": path.name, "state": state, "bytes": stat.st_size, "modified": stat.st_mtime})
    return sorted(rows, key=lambda row: row["modified"], reverse=True)


def _find_archive(name):
    if not NAME_RE.match(name):
        raise StorageError("Invalid archive name")
    for folder in (drive_folder(), OUTBOX):
        if (folder / name).is_file():
            return folder / name
    raise StorageError(f"Archive not found: {name}")


def extract(zip_path, destination):
    """Extract into a new folder, refusing unsafe paths, then check every hash."""
    destination = Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise StorageError(f"Destination is not empty: {destination}")
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()
        if sum(member.file_size for member in members) > MAX_EXTRACTED_BYTES:
            raise StorageError("Archive is larger than the extraction limit")
        for member in members:
            pure = PurePosixPath(member.filename.replace("\\", "/"))
            target = (destination / pure).resolve()
            if pure.is_absolute() or ".." in pure.parts or not target.is_relative_to(destination):
                raise StorageError(f"Unsafe path in archive: {member.filename}")
        if archive.testzip():
            raise StorageError("Archive failed its integrity check")
        destination.mkdir(parents=True, exist_ok=True)
        archive.extractall(destination)
    manifest_path = destination / MANIFEST
    if not manifest_path.is_file():
        raise StorageError("Archive has no manifest")
    hashes = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, expected in hashes.items():
        if _sha256(destination / name) != expected:
            raise StorageError(f"Hash mismatch on {name}")
    manifest_path.unlink()
    return {"files": len(hashes), "location": str(destination)}


def retrieve(name, destination):
    """Copy an archive off Drive to a temp zip, extract it, delete the temp zip."""
    source = _find_archive(name)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    local = destination.parent / (destination.name + ".incoming.zip")
    shutil.copyfile(source, local)
    try:
        return extract(local, destination)
    finally:
        local.unlink(missing_ok=True)


def status():
    return {
        "folder": str(drive_folder()),
        "available": drive_available(),
        "queued": len(list(OUTBOX.glob("*.zip"))) if OUTBOX.is_dir() else 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("list").add_argument("--client")
    store_cmd = commands.add_parser("store")
    store_cmd.add_argument("--client", required=True)
    store_cmd.add_argument("paths", nargs="+")
    retrieve_cmd = commands.add_parser("retrieve")
    retrieve_cmd.add_argument("name")
    retrieve_cmd.add_argument("--to", required=True)
    args = parser.parse_args()
    try:
        if args.command == "status":
            result = status()
        elif args.command == "list":
            result = list_archives(args.client)
        elif args.command == "store":
            result = store(args.client, args.paths)
        else:
            result = retrieve(args.name, args.to)
    except StorageError as error:
        sys.exit(f"Error: {error}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
