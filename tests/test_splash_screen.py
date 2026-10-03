import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

app = QApplication.instance()
if not app:
    app = QApplication([])

from src.splash_screen import LumiSplashScreen


class TestSplashScreen(unittest.TestCase):
    def test_set_message_updates_status_and_progress(self):
        splash = LumiSplashScreen()
        splash.set_message("STT 모델 로드 중 (small.en)...", 58)
        self.assertEqual(splash.lbl_status.text(), "STT 모델 로드 중 (small.en)...")
        self.assertEqual(splash.progress_bar.value(), 58)
        splash.close()

    def test_finish_closes_immediately_without_delay(self):
        splash = LumiSplashScreen()
        splash.show()
        target = QWidget()
        target.show()
        splash.finish(target)
        self.assertTrue(splash.isHidden() or not splash.isVisible())
        target.close()


if __name__ == "__main__":
    unittest.main()
