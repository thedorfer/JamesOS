from __future__ import annotations

import unittest
from pathlib import Path


class JadeVisibleModesTests(unittest.TestCase):
    def test_visible_modes_are_only_chat_work_private(self) -> None:
        source = Path("apps/jade_app/lib/screens/chat_screen.dart").read_text(encoding="utf-8")
        self.assertIn("const visibleModes = [AppMode.chat, AppMode.work, AppMode.private];", source)
        self.assertNotIn("items: AppMode.values", source)

    def test_private_mode_exists(self) -> None:
        source = Path("apps/jade_app/lib/models/app_mode.dart").read_text(encoding="utf-8")
        self.assertIn("private", source)
        self.assertIn("AppMode.private => 'private'", source)

    def test_private_mode_does_not_persist_backend_memory(self) -> None:
        api_source = Path("jamesos/core/api.py").read_text(encoding="utf-8")
        reasoner_source = Path("jamesos/services/jade_reasoner.py").read_text(encoding="utf-8")
        self.assertIn('if req.mode != "private":', api_source)
        self.assertIn('if mode == "private":', reasoner_source)


if __name__ == "__main__":
    unittest.main()
