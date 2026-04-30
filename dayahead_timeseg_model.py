from __future__ import annotations

import argparse
from pathlib import Path

from dayahead_core import (
    DEFAULT_FORECAST_FILE,
    DEFAULT_HISTORY_DIR,
    DEFAULT_MODEL_ROOT,
    DEFAULT_OUTPUT_FILE,
    TrainConfig,
    load_training_log,
    predict_prices,
    print_metrics,
    rollback_to_previous,
    train_and_register,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="日前电价预测模型（相似法基线 + XGBoost 残差修正版）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_parser = subparsers.add_parser("train", help="训练模型")
    add_train_args(train_parser)

    predict_parser = subparsers.add_parser("predict", help="执行预测")
    predict_parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), help="历史 Excel 目录")
    predict_parser.add_argument("--forecast-file", default=str(DEFAULT_FORECAST_FILE), help="预测文件路径")
    predict_parser.add_argument("--model-root", default=str(DEFAULT_MODEL_ROOT), help="模型根目录")
    predict_parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE), help="预测结果输出文件")
    predict_parser.add_argument("--holiday-file", help="节假日文件")
    predict_parser.add_argument("--reference-days", type=int, default=1, help="相似法参考最近天数")

    train_predict_parser = subparsers.add_parser("train_predict", help="先训练后预测")
    add_train_args(train_predict_parser)
    train_predict_parser.add_argument("--forecast-file", default=str(DEFAULT_FORECAST_FILE), help="预测文件路径")
    train_predict_parser.add_argument("--output-file", default=str(DEFAULT_OUTPUT_FILE), help="预测结果输出文件")
    train_predict_parser.add_argument("--reference-days", type=int, default=1, help="相似法参考最近天数")

    rollback_parser = subparsers.add_parser("rollback", help="回退到上一版模型")
    rollback_parser.add_argument("--model-root", default=str(DEFAULT_MODEL_ROOT), help="模型根目录")

    runs_parser = subparsers.add_parser("runs", help="查看训练日志")
    runs_parser.add_argument("--model-root", default=str(DEFAULT_MODEL_ROOT), help="模型根目录")

    return parser.parse_args()


def add_train_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--history-dir", default=str(DEFAULT_HISTORY_DIR), help="历史 Excel 目录")
    parser.add_argument("--model-root", default=str(DEFAULT_MODEL_ROOT), help="模型根目录")
    parser.add_argument("--holiday-file", help="节假日文件")
    parser.add_argument("--valid-days", type=int, default=14, help="验证集天数")
    parser.add_argument("--num-boost-round", type=int, default=400, help="XGBoost 训练轮数")
    parser.add_argument("--start-date", help="训练起始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", help="训练结束日期，格式 YYYY-MM-DD")


def build_train_config(args: argparse.Namespace) -> TrainConfig:
    return TrainConfig(
        history_dir=Path(args.history_dir),
        model_root=Path(args.model_root),
        holiday_file=Path(args.holiday_file) if args.holiday_file else None,
        valid_days=args.valid_days,
        num_boost_round=args.num_boost_round,
        start_date=args.start_date,
        end_date=args.end_date,
    )


def main() -> None:
    args = parse_args()

    if args.command == "train":
        result = train_and_register(build_train_config(args))
        print_metrics(result.metrics)
        print(f"当前模型目录: {result.current_model_dir}")
        print(f"训练日期范围: {result.train_dates[0]} ~ {result.train_dates[-1]}")
        if result.valid_dates:
            print(f"验证日期范围: {result.valid_dates[0]} ~ {result.valid_dates[-1]}")
        return

    if args.command == "predict":
        result = predict_prices(
            history_dir=args.history_dir,
            forecast_file=args.forecast_file,
            model_root=args.model_root,
            output_file=args.output_file,
            holiday_file=args.holiday_file,
            reference_days=args.reference_days,
        )
        print(f"预测完成，预测日: {result.forecast_date}")
        print(f"结果文件: {result.output_file}")
        print(f"已回填模板: {result.template_updated}")
        print(f"参考日: {', '.join(result.reference_dates)}")
        return

    if args.command == "train_predict":
        train_result = train_and_register(build_train_config(args))
        print_metrics(train_result.metrics)
        predict_result = predict_prices(
            history_dir=args.history_dir,
            forecast_file=args.forecast_file,
            model_root=args.model_root,
            output_file=args.output_file,
            holiday_file=args.holiday_file,
            reference_days=args.reference_days,
        )
        print(f"预测完成，预测日: {predict_result.forecast_date}")
        print(f"结果文件: {predict_result.output_file}")
        print(f"已回填模板: {predict_result.template_updated}")
        print(f"参考日: {', '.join(predict_result.reference_dates)}")
        return

    if args.command == "rollback":
        current_dir = rollback_to_previous(Path(args.model_root))
        print(f"已回退到上一版模型: {current_dir}")
        return

    if args.command == "runs":
        log_df = load_training_log(Path(args.model_root))
        if log_df.empty:
            print("暂无训练日志")
            return
        print(log_df[["run_id", "created_at", "train_start_date", "train_end_date", "sample_rows"]].to_string(index=False))


if __name__ == "__main__":
    main()
