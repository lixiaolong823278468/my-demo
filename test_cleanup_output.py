from __future__ import annotations

import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class CleanupOutputTests(unittest.TestCase):
    def test_cleanup_keeps_business_output_and_removes_only_known_junk(self) -> None:
        import api_server

        base = Path(__file__).resolve().parent / f"cleanup_case_{time.time_ns()}"
        output_root = base / "output"
        output_file = output_root / "dayahead_price_prediction.xlsx"
        archive_root = output_root / "prediction_archive"
        quality_report_root = output_root / "data_quality_reports"
        unknown_output_dir = output_root / "manual_export"
        optimization_dir = output_root / "window_optimization"
        try:
            archive_root.mkdir(parents=True)
            quality_report_root.mkdir(parents=True)
            unknown_output_dir.mkdir(parents=True)
            optimization_dir.mkdir(parents=True)
            output_file.write_text("prediction", encoding="utf-8")
            (archive_root / "index.json").write_text('{"records":[]}', encoding="utf-8")
            (quality_report_root / "old_report.json").write_text('{"report_id":"old"}', encoding="utf-8")
            (unknown_output_dir / "keep.txt").write_text("business data", encoding="utf-8")
            (optimization_dir / "tmp.txt").write_text("junk", encoding="utf-8")

            with (
                patch.object(api_server, "OUTPUT_ROOT", output_root),
                patch.object(api_server, "OUTPUT_FILE", output_file),
                patch.object(api_server, "PREDICTION_ARCHIVE_ROOT", archive_root),
                patch.object(api_server.STATE, "status", return_value={"running": False}),
            ):
                result = api_server.cleanup_output_junk()

            self.assertTrue(archive_root.exists())
            self.assertTrue((archive_root / "index.json").exists())
            self.assertTrue(quality_report_root.exists())
            self.assertTrue((quality_report_root / "old_report.json").exists())
            self.assertTrue(unknown_output_dir.exists())
            self.assertTrue((unknown_output_dir / "keep.txt").exists())
            self.assertFalse(optimization_dir.exists())
            self.assertIn(str(quality_report_root.resolve()), result["kept"])
            self.assertIn(str(archive_root.resolve()), result["kept"])
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
