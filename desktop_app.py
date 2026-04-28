from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from dayahead_core import (
    DEFAULT_FORECAST_FILE,
    DEFAULT_HISTORY_DIR,
    DEFAULT_MODEL_ROOT,
    DEFAULT_OUTPUT_FILE,
    TrainConfig,
    load_current_metadata,
    load_training_log,
    predict_prices,
    rollback_to_previous,
    train_and_register,
)


class PredictorDesktopApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("日前电价预测系统")
        self.root.geometry("980x700")

        self.history_dir_var = tk.StringVar(value=str(DEFAULT_HISTORY_DIR))
        self.model_root_var = tk.StringVar(value=str(DEFAULT_MODEL_ROOT))
        self.forecast_file_var = tk.StringVar(value=str(DEFAULT_FORECAST_FILE))
        self.output_file_var = tk.StringVar(value=str(DEFAULT_OUTPUT_FILE))
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.valid_days_var = tk.StringVar(value="14")
        self.num_boost_round_var = tk.StringVar(value="400")

        self._build_ui()
        self.refresh_run_log()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.train_frame = ttk.Frame(notebook)
        self.predict_frame = ttk.Frame(notebook)
        self.run_frame = ttk.Frame(notebook)
        notebook.add(self.train_frame, text="训练")
        notebook.add(self.predict_frame, text="预测")
        notebook.add(self.run_frame, text="版本日志")

        self._build_train_tab()
        self._build_predict_tab()
        self._build_runs_tab()

        self.log_box = tk.Text(self.root, height=10)
        self.log_box.pack(fill="x", padx=10, pady=(0, 10))

    def _build_train_tab(self) -> None:
        entries = [
            ("历史数据目录", self.history_dir_var, self.train_frame, True),
            ("模型根目录", self.model_root_var, self.train_frame, True),
            ("训练起始日期", self.start_date_var, self.train_frame, False),
            ("训练结束日期", self.end_date_var, self.train_frame, False),
            ("验证集天数", self.valid_days_var, self.train_frame, False),
            ("训练轮数", self.num_boost_round_var, self.train_frame, False),
        ]
        for row, (label, variable, parent, browse) in enumerate(entries):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=8)
            ttk.Entry(parent, textvariable=variable, width=60).grid(row=row, column=1, sticky="ew", padx=8, pady=8)
            if browse:
                ttk.Button(parent, text="选择", command=lambda var=variable: self.choose_directory(var)).grid(row=row, column=2, padx=8, pady=8)
        self.train_frame.columnconfigure(1, weight=1)

        ttk.Button(self.train_frame, text="手动重训", command=self.start_train).grid(row=len(entries), column=1, sticky="w", padx=8, pady=10)
        ttk.Button(self.train_frame, text="回退到上一版", command=self.rollback_model).grid(row=len(entries), column=1, sticky="e", padx=8, pady=10)

    def _build_predict_tab(self) -> None:
        items = [
            ("预测文件", self.forecast_file_var, True, self.choose_file),
            ("输出文件", self.output_file_var, False, self.save_file),
        ]
        for row, (label, variable, _, handler) in enumerate(items):
            ttk.Label(self.predict_frame, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=8)
            ttk.Entry(self.predict_frame, textvariable=variable, width=60).grid(row=row, column=1, sticky="ew", padx=8, pady=8)
            ttk.Button(self.predict_frame, text="选择", command=lambda var=variable, fn=handler: fn(var)).grid(row=row, column=2, padx=8, pady=8)
        self.predict_frame.columnconfigure(1, weight=1)
        ttk.Button(self.predict_frame, text="执行预测", command=self.start_predict).grid(row=3, column=1, sticky="w", padx=8, pady=10)

    def _build_runs_tab(self) -> None:
        self.run_info = tk.Text(self.run_frame)
        self.run_info.pack(fill="both", expand=True, padx=8, pady=8)
        ttk.Button(self.run_frame, text="刷新", command=self.refresh_run_log).pack(anchor="w", padx=8, pady=8)

    def choose_directory(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory()
        if path:
            variable.set(path)

    def choose_file(self, variable: tk.StringVar) -> None:
        path = filedialog.askopenfilename(filetypes=[("Excel", "*.xlsx *.xls")])
        if path:
            variable.set(path)

    def save_file(self, variable: tk.StringVar) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")])
        if path:
            variable.set(path)

    def append_log(self, text: str) -> None:
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")

    def run_in_thread(self, target) -> None:
        threading.Thread(target=target, daemon=True).start()

    def start_train(self) -> None:
        self.run_in_thread(self._train)

    def _train(self) -> None:
        try:
            result = train_and_register(
                TrainConfig(
                    history_dir=Path(self.history_dir_var.get()),
                    model_root=Path(self.model_root_var.get()),
                    valid_days=int(self.valid_days_var.get()),
                    num_boost_round=int(self.num_boost_round_var.get()),
                    start_date=self.start_date_var.get() or None,
                    end_date=self.end_date_var.get() or None,
                )
            )
            self.append_log(f"训练完成：{result.run_id}")
            self.refresh_run_log()
        except Exception as exc:
            messagebox.showerror("训练失败", str(exc))

    def rollback_model(self) -> None:
        try:
            current_dir = rollback_to_previous(Path(self.model_root_var.get()))
            self.append_log(f"已回退到上一版：{current_dir}")
            self.refresh_run_log()
        except Exception as exc:
            messagebox.showerror("回退失败", str(exc))

    def start_predict(self) -> None:
        self.run_in_thread(self._predict)

    def _predict(self) -> None:
        try:
            result = predict_prices(
                history_dir=self.history_dir_var.get(),
                forecast_file=self.forecast_file_var.get(),
                model_root=self.model_root_var.get(),
                output_file=self.output_file_var.get(),
            )
            self.append_log(f"预测完成：{result.forecast_date} -> {result.output_file}")
        except Exception as exc:
            messagebox.showerror("预测失败", str(exc))

    def refresh_run_log(self) -> None:
        log_df = load_training_log(Path(self.model_root_var.get()))
        metadata = load_current_metadata(Path(self.model_root_var.get()))
        self.run_info.delete("1.0", "end")
        if metadata:
            self.run_info.insert("end", f"当前模型: {metadata.get('run_id')}\n")
            self.run_info.insert("end", f"训练区间: {metadata.get('train_start_date')} ~ {metadata.get('train_end_date')}\n\n")
        if log_df.empty:
            self.run_info.insert("end", "暂无训练日志")
            return
        self.run_info.insert("end", log_df.to_string(index=False))

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    PredictorDesktopApp().run()
