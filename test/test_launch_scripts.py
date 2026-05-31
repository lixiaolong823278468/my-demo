from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LaunchScriptTests(unittest.TestCase):
    def script_text(self, name: str) -> str:
        return (PROJECT_ROOT / name).read_text(encoding="utf-8").lower()

    def assert_python_fallbacks(self, text: str) -> None:
        self.assertIn('call :try_python ".venv\\scripts\\python.exe"', text)
        self.assertIn('call :try_python "python"', text)
        self.assertIn('call :try_python "py -3"', text)
        self.assertIn('"--version"', text)
        self.assertIn("if errorlevel 1 exit /b 0", text)

    def test_launch_web_uses_verified_python_fallbacks(self) -> None:
        self.assert_python_fallbacks(self.script_text("launch_web.bat"))

    def test_launch_desktop_uses_verified_python_fallbacks(self) -> None:
        text = self.script_text("launch_desktop.bat")

        self.assert_python_fallbacks(text)
        self.assertNotIn('if exist ".venv\\scripts\\python.exe" (', text)


if __name__ == "__main__":
    unittest.main()
