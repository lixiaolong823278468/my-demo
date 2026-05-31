from __future__ import annotations

import unittest


class DualModelTrainingControlTests(unittest.TestCase):
    def test_dual_control_continues_when_dayahead_fails(self) -> None:
        from api_server import run_dual_window_optimization_sequence

        calls = []

        def runner(target: str) -> dict:
            calls.append(target)
            if target == "dayahead":
                raise RuntimeError("dayahead failed")
            return {"target": target, "run_id": "run_rt"}

        result = run_dual_window_optimization_sequence({}, runner=runner)

        self.assertEqual(calls, ["dayahead", "realtime"])
        self.assertEqual(result["status"], "partial_success")
        self.assertEqual(result["targets"]["dayahead"]["status"], "failed")
        self.assertEqual(result["targets"]["realtime"]["status"], "success")

    def test_dual_control_uses_independent_payload_for_each_target(self) -> None:
        from api_server import dual_window_target_payload

        payload = {
            "force": True,
            "dayahead_payload": {"max_history_days": 90},
            "realtime_payload": {"max_history_days": 120},
        }

        self.assertEqual(dual_window_target_payload(payload, "dayahead")["max_history_days"], 90)
        self.assertEqual(dual_window_target_payload(payload, "realtime")["max_history_days"], 120)
        self.assertTrue(dual_window_target_payload(payload, "realtime")["force"])


if __name__ == "__main__":
    unittest.main()
