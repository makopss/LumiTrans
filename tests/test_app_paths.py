import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import src.app_paths as app_paths


class LegacyDataMigration(unittest.TestCase):
    """이전 이름(WiseEinstein) 데이터 폴더를 새 이름(LumiTrans)으로 옮겨 설정을 보존한다."""

    def setUp(self):
        app_paths._migrated.clear()

    def test_legacy_folder_is_renamed_with_contents(self):
        with tempfile.TemporaryDirectory() as base:
            legacy = os.path.join(base, "WiseEinstein")
            os.makedirs(os.path.join(legacy, "cuda"))
            with open(os.path.join(legacy, "config.json"), "w", encoding="utf-8") as f:
                f.write('{"font_size": 30}')
            with patch.dict(os.environ, {"APPDATA": base}):
                path = app_paths.roaming_data_dir()
            self.assertEqual(path, os.path.join(base, "LumiTrans"))
            self.assertFalse(os.path.exists(legacy))
            with open(os.path.join(path, "config.json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), '{"font_size": 30}')
            self.assertTrue(os.path.isdir(os.path.join(path, "cuda")))

    def test_existing_new_folder_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as base:
            os.makedirs(os.path.join(base, "WiseEinstein"))
            new = os.path.join(base, "LumiTrans")
            os.makedirs(new)
            with open(os.path.join(new, "config.json"), "w", encoding="utf-8") as f:
                f.write("new")
            with patch.dict(os.environ, {"LOCALAPPDATA": base}):
                path = app_paths.local_data_dir()
            with open(os.path.join(path, "config.json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "new")
            self.assertTrue(os.path.isdir(os.path.join(base, "WiseEinstein")))

    def test_fresh_install_creates_new_folder(self):
        with tempfile.TemporaryDirectory() as base:
            with patch.dict(os.environ, {"APPDATA": base}):
                path = app_paths.roaming_data_dir()
            self.assertTrue(os.path.isdir(path))
            self.assertEqual(os.path.basename(path), "LumiTrans")

    def test_falls_back_to_copy_when_rename_fails(self):
        with tempfile.TemporaryDirectory() as base:
            legacy = os.path.join(base, "WiseEinstein")
            os.makedirs(legacy)
            with open(os.path.join(legacy, "config.json"), "w", encoding="utf-8") as f:
                f.write("kept")
            with patch.dict(os.environ, {"APPDATA": base}), \
                 patch.object(app_paths.os, "rename", side_effect=PermissionError("locked")):
                path = app_paths.roaming_data_dir()
            with open(os.path.join(path, "config.json"), encoding="utf-8") as f:
                self.assertEqual(f.read(), "kept")


if __name__ == "__main__":
    unittest.main()
