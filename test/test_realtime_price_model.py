from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class RealtimePriceModelTests(unittest.TestCase):
    def test_model_target_context_defaults_to_dayahead(self) -> None:
        from dayahead_core import model_target_context

        context = model_target_context(None)

        self.assertEqual(context["target"], "dayahead")
        self.assertEqual(context["data_mode"], "dayahead")
        self.assertEqual(context["model_root"].name, "models")
        self.assertTrue(context["trains_capacity"])

    def test_model_target_context_resolves_realtime_root(self) -> None:
        from dayahead_core import model_target_context

        context = model_target_context("realtime")

        self.assertEqual(context["target"], "realtime")
        self.assertEqual(context["data_mode"], "realtime")
        self.assertEqual(context["model_root"].name, "realtime_price")
        self.assertFalse(context["trains_capacity"])

    def test_realtime_preferences_copy_dayahead_once_then_stay_independent(self) -> None:
        from api_server import load_target_training_preferences, save_target_training_preferences
        from dayahead_core import save_training_preferences

        with tempfile.TemporaryDirectory() as tmp:
            model_root = Path(tmp) / "models"
            save_training_preferences(
                model_root,
                {"high_price_weighting": {"enabled": True, "quantile": 0.81, "multiplier": 2.5}},
            )

            realtime_first = load_target_training_preferences("realtime", model_root=model_root)

            self.assertTrue(realtime_first["high_price_weighting"]["enabled"])
            self.assertEqual(realtime_first["high_price_weighting"]["multiplier"], 2.5)

            save_target_training_preferences(
                "realtime",
                {"high_price_weighting": {"enabled": True, "quantile": 0.9, "multiplier": 3.0}},
                model_root=model_root,
            )
            save_training_preferences(
                model_root,
                {"high_price_weighting": {"enabled": False, "quantile": 0.7, "multiplier": 1.5}},
            )

            realtime_second = load_target_training_preferences("realtime", model_root=model_root)

            self.assertTrue(realtime_second["high_price_weighting"]["enabled"])
            self.assertEqual(realtime_second["high_price_weighting"]["quantile"], 0.9)
            self.assertEqual(realtime_second["high_price_weighting"]["multiplier"], 3.0)

    def test_build_train_worker_uses_realtime_data_mode_and_skips_capacity(self) -> None:
        import api_server
        import tempfile

        class FakeState:
            def append_log(self, *_args, **_kwargs) -> None:
                return None

            def raise_if_cancelled(self, _job_id: str) -> None:
                return None

        captured = {}

        def fake_train_and_register(config, progress_callback=None):
            captured["data_mode"] = config.data_mode
            captured["model_root"] = config.model_root
            captured["train_thermal_capacity_model"] = config.train_thermal_capacity_model
            return object()

        with tempfile.TemporaryDirectory() as tmp:
            model_root = Path(tmp) / "models"
            with (
                patch.object(api_server, "STATE", FakeState()),
                patch.object(api_server, "train_and_register", fake_train_and_register),
                patch.object(api_server, "validate_training_result_or_restore", lambda *_args, **_kwargs: None),
                patch.object(api_server, "summarize_train_result", lambda _result: {"ok": True}),
            ):
                worker = api_server.build_train_worker({"target": "realtime", "model_root": str(model_root)})
                result = worker("job_rt")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(captured["data_mode"], "realtime")
        self.assertEqual(captured["model_root"].name, "realtime_price")
        self.assertFalse(captured["train_thermal_capacity_model"])

    def test_build_train_worker_skips_unchanged_non_forced_training(self) -> None:
        import api_server

        class FakeState:
            def append_log(self, *_args, **_kwargs) -> None:
                return None

            def raise_if_cancelled(self, _job_id: str) -> None:
                return None

        with (
            patch.object(api_server, "STATE", FakeState()),
            patch.object(api_server, "load_current_metadata", return_value={"training_run_fingerprint": "same"}),
            patch.object(api_server, "training_history_signature", return_value={"cache_key": "same-history"}),
            patch.object(api_server, "training_run_fingerprint", return_value="same"),
            patch.object(api_server, "train_and_register", side_effect=AssertionError("unchanged training should be skipped")),
        ):
            result = api_server.build_train_worker({"force": False})("job_skip")

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "training_input_unchanged")

    def test_predict_worker_passes_realtime_version_key(self) -> None:
        import api_server
        import tempfile

        class FakeState:
            def append_log(self, *_args, **_kwargs) -> None:
                return None

            def raise_if_cancelled(self, _job_id: str) -> None:
                return None

        captured = {}

        def fake_predict_prices_compare(**kwargs):
            captured.update(kwargs)
            return object()

        with tempfile.TemporaryDirectory() as tmp:
            model_root = Path(tmp) / "models"
            with (
                patch.object(api_server, "STATE", FakeState()),
                patch.object(api_server, "selected_prediction_model_root", lambda _payload, _job_id: (model_root, None, "run_day")),
                patch.object(api_server, "selected_realtime_prediction_model_root", lambda _payload, _job_id: (model_root / "realtime_price", None, "run_rt")),
                patch.object(api_server, "predict_prices_compare", fake_predict_prices_compare),
                patch.object(api_server, "summarize_predict_result", lambda _result: {"prediction": {}}),
                patch.object(api_server, "load_current_metadata", lambda _root: {"run_id": "run_day"}),
                patch.object(api_server, "archive_prediction_bundle", lambda *_args, **_kwargs: {"saved": []}),
            ):
                worker = api_server.build_predict_worker(
                    {
                        "model_version_key": "run_day",
                        "realtime_model_version_key": "run_rt",
                        "model_root": str(model_root),
                    }
                )
                worker("job_predict")

        self.assertEqual(captured["realtime_model_version_key"], "run_rt")
        self.assertEqual(captured["realtime_model_root_override"].name, "realtime_price")

    def test_realtime_history_sheet_uses_actual_operation_fields(self) -> None:
        from dayahead_core import TARGET_COLUMN, DayAheadDataBuilder

        raw = pd.DataFrame(
            {
                "总加电力值(MW)": [9000.0] * 96,
                "电力值(MW)": [1000.0] * 96,
                "日前出清价格(元/MWh)": [111.0] * 96,
                "日前-出清概况": ["火电开机容量 5000 MW"] * 96,
                "用电负荷(MW)": [1000.0 + i for i in range(96)],
                "新能源总计划(MW)": [100.0 + i for i in range(96)],
                "火电总计划(MW)": [777.0 + i for i in range(96)],
                "实时出清价格(元/MWh)": [300.0 + i for i in range(96)],
            }
        )

        result = DayAheadDataBuilder().prepare_single_sheet(
            raw,
            Path("history.xlsx"),
            "2026-05-01",
            pd.Timestamp("2026-05-01"),
            require_target=True,
            data_mode="realtime",
        )

        self.assertEqual(float(result.loc[0, "total_load"]), 1000.0)
        self.assertEqual(float(result.loc[0, "renewable_power"]), 100.0)
        self.assertEqual(float(result.loc[0, "net_load"]), 777.0)
        self.assertAlmostEqual(float(result.loc[0, "thermal_space_load_ratio"]), 0.777)
        self.assertEqual(float(result.loc[0, TARGET_COLUMN]), 300.0)

    def test_merge_realtime_prediction_appends_columns_without_replacing_dayahead_prediction(self) -> None:
        from dayahead_core import merge_realtime_prediction_columns

        base = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-02", "2026-05-02"]),
                "period": [1, 2],
                "predicted_price": [210.0, 220.0],
                "model_variant": ["dayahead_a", "dayahead_b"],
            }
        )
        realtime = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-02", "2026-05-02"]),
                "period": [1, 2],
                "predicted_price": [310.0, 320.0],
                "model_variant": ["realtime_a", "realtime_b"],
            }
        )

        result = merge_realtime_prediction_columns(base, realtime)

        self.assertEqual(result["predicted_price"].tolist(), [210.0, 220.0])
        self.assertEqual(result["model_variant"].tolist(), ["dayahead_a", "dayahead_b"])
        self.assertEqual(result["realtime_predicted_price"].tolist(), [310.0, 320.0])
        self.assertEqual(result["realtime_model_variant"].tolist(), ["realtime_a", "realtime_b"])
        self.assertEqual(result["price_spread_realtime_minus_dayahead"].tolist(), [100.0, 100.0])

    def test_export_prediction_includes_dual_model_status_columns(self) -> None:
        from dayahead_core import export_prediction

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "prediction.xlsx"
            frame = pd.DataFrame(
                {
                    "date": ["2026-05-26"],
                    "period": [1],
                    "predicted_price": [300.0],
                    "realtime_predicted_price": [310.0],
                    "price_spread_realtime_minus_dayahead": [10.0],
                    "model_variant": ["day_model"],
                    "realtime_model_variant": ["rt_model"],
                    "dayahead_model_version": ["run_day"],
                    "realtime_model_version": ["run_rt"],
                    "realtime_prediction_status": ["ok"],
                    "realtime_prediction_error": [None],
                }
            )

            export_prediction(frame, output)
            exported = pd.read_excel(output)

        self.assertIn("realtime_prediction_status", exported.columns)
        self.assertIn("price_spread_realtime_minus_dayahead", exported.columns)
        self.assertIn("dayahead_model_version", exported.columns)
        self.assertIn("realtime_model_version", exported.columns)

    def test_append_realtime_prediction_returns_base_when_realtime_model_is_missing(self) -> None:
        from dayahead_core import append_realtime_prediction_if_available

        base = pd.DataFrame(
            {
                "date": pd.to_datetime(["2026-05-02"]),
                "period": [1],
                "predicted_price": [210.0],
            }
        )

        result = append_realtime_prediction_if_available(
            base,
            history_dir=Path("history"),
            model_root=Path("missing-model-root"),
            holiday_file=None,
            forecast_df=base,
            template_reference_df=None,
            holiday_dates=set(),
            reference_days=1,
            reference_strategy="recent_n_days",
        )

        self.assertEqual(result["predicted_price"].tolist(), [210.0])
        self.assertNotIn("realtime_predicted_price", result.columns)


if __name__ == "__main__":
    unittest.main()
