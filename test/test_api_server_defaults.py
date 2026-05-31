from __future__ import annotations

import shutil
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path


class ApiServerDefaultsTests(unittest.TestCase):
    def test_default_training_window_uses_last_optimized_best_days(self) -> None:
        from api_server import resolve_default_training_window_days

        state = {
            "last_attempt_status": "success",
            "best_window_days": 45,
        }

        self.assertEqual(resolve_default_training_window_days(state), 45)

    def test_default_training_window_falls_back_without_optimization_result(self) -> None:
        from api_server import resolve_default_training_window_days

        self.assertEqual(resolve_default_training_window_days({}), 60)
        self.assertEqual(resolve_default_training_window_days({"best_window_days": 0}), 60)

    def test_prediction_reference_preferences_are_saved_and_normalized(self) -> None:
        from dayahead_core import load_training_preferences, save_training_preferences

        with TemporaryDirectory() as temp_dir:
            saved = save_training_preferences(
                temp_dir,
                {
                    "prediction_reference": {
                        "recent_reference_days": 8,
                        "same_type_reference_days": 4,
                        "knn_similarity": {
                            "knn_k": 7,
                            "knn_max_distance": 2.5,
                            "weighted_knn_k": 6,
                            "weighted_knn_max_distance": 1.8,
                        },
                    }
                },
            )
            loaded = load_training_preferences(temp_dir)

        self.assertEqual(saved["prediction_reference"]["recent_reference_days"], 8)
        self.assertEqual(loaded["prediction_reference"]["same_type_reference_days"], 4)
        self.assertEqual(loaded["prediction_reference"]["knn_similarity"]["knn_k"], 7)
        self.assertEqual(loaded["prediction_reference"]["knn_similarity"]["weighted_knn_max_distance"], 1.8)

    def test_remove_tree_with_retry_handles_transient_directory_not_empty(self) -> None:
        import api_server

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "prediction_model_selection" / "job" / "current" / "interval_xgboost"
            root.mkdir(parents=True)
            (root / "segment_1.json").write_text("{}", encoding="utf-8")
            target = root.parents[2]
            original_rmtree = api_server.shutil.rmtree
            calls = {"count": 0}

            def flaky_rmtree(path: Path, *args: object, **kwargs: object) -> None:
                calls["count"] += 1
                if calls["count"] == 1:
                    raise OSError(145, "目录不是空的", str(root))
                original_rmtree(path, *args, **kwargs)

            try:
                api_server.shutil.rmtree = flaky_rmtree
                api_server.remove_tree_with_retry(target)
            finally:
                api_server.shutil.rmtree = original_rmtree
                shutil.rmtree(target, ignore_errors=True)

            self.assertFalse(target.exists())
            self.assertGreaterEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
