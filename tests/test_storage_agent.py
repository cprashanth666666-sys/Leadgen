import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import storage_agent as agent


class StorageAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "src"
        (self.source / "docs").mkdir(parents=True)
        (self.source / "docs" / "a.txt").write_text("hello " * 500, encoding="utf-8")
        (self.source / "b.bin").write_bytes(bytes(range(256)) * 10)
        self.drive = self.root / "drive" / "Leadgen"
        self.drive.parent.mkdir()
        patches = [
            mock.patch.object(agent, "OUTBOX", self.root / "outbox"),
            mock.patch.dict(os.environ, {"GDRIVE_FOLDER": str(self.drive)}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_round_trip_restores_identical_files(self):
        result = agent.store("acme-co", [self.source], base=self.source)
        self.assertEqual(result["state"], "stored")
        self.assertEqual(result["files"], 2)
        self.assertLess(result["zip_bytes"], result["original_bytes"])
        stored = self.drive / result["name"]
        self.assertTrue(zipfile.is_zipfile(stored))
        self.assertEqual(list((self.root / "outbox").glob("*.zip")), [])
        out = self.root / "out"
        agent.retrieve(result["name"], out)
        self.assertEqual((out / "docs" / "a.txt").read_bytes(), (self.source / "docs" / "a.txt").read_bytes())
        self.assertEqual((out / "b.bin").read_bytes(), (self.source / "b.bin").read_bytes())
        self.assertFalse((out / agent.MANIFEST).exists())
        self.assertEqual(list(self.root.glob("*.incoming.zip")), [])

    def test_queues_when_drive_is_missing_then_flushes(self):
        with mock.patch.dict(os.environ, {"GDRIVE_FOLDER": str(self.root / "gone" / "x" / "Leadgen")}):
            result = agent.store("acme-co", [self.source], base=self.source)
            self.assertEqual(result["state"], "queued")
        (self.source / "c.txt").write_text("more", encoding="utf-8")
        second = agent.store("acme-co", [self.source], base=self.source)
        self.assertEqual(second["state"], "stored")
        self.assertIn(result["name"], second["flushed"])
        self.assertTrue((self.drive / result["name"]).is_file())

    def test_refuses_path_traversal(self):
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("../escape.txt", "x")
        with self.assertRaises(agent.StorageError):
            agent.extract(bad, self.root / "dest")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_detects_tampered_contents(self):
        bad = self.root / "tampered.zip"
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("a.txt", "changed")
            archive.writestr(agent.MANIFEST, '{"a.txt": "0000"}')
        with self.assertRaises(agent.StorageError):
            agent.extract(bad, self.root / "dest")

    def test_refuses_non_empty_destination(self):
        result = agent.store("acme-co", [self.source], base=self.source)
        out = self.root / "out"
        out.mkdir()
        (out / "keep.txt").write_text("mine", encoding="utf-8")
        with self.assertRaises(agent.StorageError):
            agent.retrieve(result["name"], out)
        self.assertEqual((out / "keep.txt").read_text(encoding="utf-8"), "mine")

    def test_rejects_bad_names(self):
        with self.assertRaises(agent.StorageError):
            agent.retrieve("../../secret.zip", self.root / "out")
        with self.assertRaises(agent.StorageError):
            agent.store("../evil", [self.source], base=self.source)


if __name__ == "__main__":
    unittest.main()
