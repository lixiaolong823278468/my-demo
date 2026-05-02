from __future__ import annotations

import time
import unittest
from pathlib import Path

import pandas as pd


class HistoryCacheTests(unittest.TestCase):
    def test_date_window_selects_only_overlapping_month_files(self) -> None:
        from dayahead_core import list_excel_files_for_date_window

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        marker = time.time_ns()
        selected_names = [
            f"{marker}_2025年12月.xlsx",
            f"{marker}_2026年1月.xlsx",
            f"{marker}_2026年4月.xlsx",
        ]
        excluded_names = [
            f"{marker}_2025年11月.xlsx",
            f"{marker}_2026年5月.xlsx",
        ]
        for name in [*selected_names, *excluded_names]:
            (root / name).write_bytes(b"x")

        files = list_excel_files_for_date_window(root, "2026-01-01", "2026-04-30", leading_days=1)
        result_names = {path.name for path in files if path.name.startswith(str(marker))}

        self.assertEqual(result_names, set(selected_names))

    def test_prediction_history_window_looks_back_enough_for_same_type_days(self) -> None:
        from dayahead_core import prediction_history_window

        start_date, end_date = prediction_history_window(pd.Timestamp("2026-05-02"), 4)

        self.assertEqual(start_date, "2026-03-31")
        self.assertEqual(end_date, "2026-05-01")

    def test_dataframe_cache_round_trip_and_signature_invalidation(self) -> None:
        from dayahead_core import (
            build_history_source_signature,
            load_dataframe_cache,
            save_dataframe_cache,
        )

        root = Path(__file__).resolve().parent / ".test_tmp"
        root.mkdir(exist_ok=True)
        source_file = root / f"history_cache_source_{time.time_ns()}.xlsx"
        source_file.write_bytes(b"first")

        cache_dir = root / "cache"
        cache_name = source_file.stem
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(["2025-01-01"]),
                "period": [1],
                "net_load": [123.45],
            }
        )
        signature = build_history_source_signature(source_file, None, True)

        save_dataframe_cache(cache_dir, cache_name, signature["cache_key"], frame, ["skipped"])
        cached = load_dataframe_cache(cache_dir, cache_name, signature["cache_key"])

        self.assertIsNotNone(cached)
        cached_frame, skipped_sheets = cached
        pd.testing.assert_frame_equal(cached_frame, frame)
        self.assertEqual(skipped_sheets, ["skipped"])

        time.sleep(0.01)
        source_file.write_bytes(b"changed")
        changed_signature = build_history_source_signature(source_file, None, True)

        self.assertNotEqual(signature["cache_key"], changed_signature["cache_key"])
        self.assertIsNone(load_dataframe_cache(cache_dir, cache_name, changed_signature["cache_key"]))


if __name__ == "__main__":
    unittest.main()
