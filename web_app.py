from __future__ import annotations

import html
import json
from datetime import date, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from dayahead_core import (
    DEFAULT_FORECAST_FILE,
    DEFAULT_HISTORY_DIR,
    DEFAULT_MODEL_ROOT,
    DEFAULT_OUTPUT_FILE,
    TrainConfig,
    activate_model_version,
    delete_model_versions,
    list_model_versions,
    load_current_metadata,
    load_training_log,
    load_training_preferences,
    normalize_similarity_weights,
    predict_prices,
    rollback_to_previous,
    save_training_preferences,
    train_and_register,
)


st.set_page_config(page_title="日前电价预测平台", page_icon="⚡", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
TEMPLATE_DIR = FRONTEND_DIR / "templates"
ASSET_DIR = FRONTEND_DIR / "assets"

MODEL_ROOT = Path(DEFAULT_MODEL_ROOT)
FORECAST_FILE = Path(DEFAULT_FORECAST_FILE)
HISTORY_DIR = Path(DEFAULT_HISTORY_DIR)
OUTPUT_FILE = Path(DEFAULT_OUTPUT_FILE)


def init_state() -> None:
    st.session_state.setdefault("app_logs", [])
    st.session_state.setdefault("current_status", "系统待命")
    st.session_state.setdefault("last_predict_df", None)
    st.session_state.setdefault("last_predict_date", None)


def add_log(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.app_logs.append(f"[{timestamp}] {message}")
    st.session_state.app_logs = st.session_state.app_logs[-300:]
    st.session_state.current_status = message


def make_progress_callback(progress_bar, status_placeholder):
    def callback(message: str, percent: int | None) -> None:
        add_log(message)
        status_placeholder.markdown(f"**当前状态：** {message}")
        if percent is not None:
            progress_bar.progress(int(percent))

    return callback


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def format_time_text(value: object) -> str:
    if value is None or value == "" or pd.isna(value):
        return "-"
    return str(value).replace("T", " ")


def render_template(template_name: str, **kwargs: str) -> None:
    template = read_text(TEMPLATE_DIR / template_name)
    st.markdown(template.format(**kwargs), unsafe_allow_html=True)


def build_chip_html(items: list[str], class_name: str = "toolbar-chip") -> str:
    return "".join(f'<span class="{class_name}">{html.escape(item)}</span>' for item in items)


def render_card(title: str, value: str, desc: str, card_class: str = "info-card") -> None:
    render_template(
        "card.html",
        card_class=card_class,
        title=html.escape(title),
        value=html.escape(value),
        desc=html.escape(desc),
    )


def render_chip_row(chips: list[str]) -> None:
    render_template("chip_row.html", chips_html=build_chip_html(chips))


def render_toolbar(title: str, desc: str, chips: list[str]) -> None:
    render_template(
        "toolbar.html",
        title=html.escape(title),
        desc=html.escape(desc),
        chips_html=build_chip_html(chips),
    )


def render_path_box(lines: list[str]) -> None:
    render_template("path_box.html", body_html="<br>".join(lines))


def render_range_tip(text: str) -> None:
    render_template("range_tip.html", text=html.escape(text))


def render_css() -> None:
    css_text = read_text(ASSET_DIR / "styles.css")
    st.markdown(f"<style>{css_text}</style>", unsafe_allow_html=True)


def inject_local_frontend_behaviors() -> None:
    js_text = read_text(ASSET_DIR / "behaviors.js")
    components.html(f"<script>{js_text}</script>", height=0, width=0)


def render_header() -> None:
    render_template(
        "header.html",
        badge=html.escape("欢迎使用 · 山西电力现货建模工作台"),
        title=html.escape("⚡ 日前电价预测平台"),
        subtitle=html.escape("相似法基线 + XGBoost 残差修正 ｜ 手动重训 ｜ 版本切换 ｜ 结果回填 ｜ 实时运行日志 ｜ 价格区间约束"),
    )


def format_version_label(row: pd.Series) -> str:
    flags = []
    if bool(row.get("is_default")):
        flags.append("默认模型")
    if bool(row.get("is_previous")):
        flags.append("上一版")
    suffix = f" ｜ {' / '.join(flags)}" if flags else ""
    return f"{row['version_key']} ｜ {format_time_text(row['created_at'])} ｜ {row['train_start_date']} ~ {row['train_end_date']}{suffix}"


def chinese_result_df(result_df: pd.DataFrame) -> pd.DataFrame:
    return result_df.rename(
        columns={
            "date": "日期",
            "period": "时段",
            "segment": "分时段",
            "hour": "小时",
            "net_load": "火电空间",
            "thermal_on_capacity": "火电开机容量(MW)",
            "lag_96": "前一日同点日前价格",
            "similar_price": "相似法基线价格",
            "residual_pred": "模型残差修正值",
            "predicted_price": "最终预测价格",
        }
    )


def render_top_status() -> None:
    metadata = load_current_metadata(MODEL_ROOT) or {}
    forecast_text = st.session_state.last_predict_date or "未执行"
    status_items = [
        f"当前默认模型：{metadata.get('run_id', '-')}",
        f"最近预测日：{forecast_text}",
        f"历史数据目录：{HISTORY_DIR.name}",
        f"运行状态：{st.session_state.current_status}",
    ]
    chips_html = "".join(
        f'<div class="status-chip"><span class="status-dot"></span>{html.escape(item)}</div>'
        for item in status_items
    )
    render_template("top_status.html", chips_html=chips_html)


def render_summary_cards() -> None:
    metadata = load_current_metadata(MODEL_ROOT) or {}
    versions_df = list_model_versions(MODEL_ROOT)
    previous_row = versions_df[versions_df["is_previous"]].iloc[0] if not versions_df.empty and versions_df["is_previous"].any() else None

    col1, col2, col3 = st.columns(3)
    with col1:
        render_card("当前默认模型", metadata.get("run_id", "-"), f"训练区间：{metadata.get('train_start_date', '-')} ~ {metadata.get('train_end_date', '-')}")
    with col2:
        previous_key = previous_row["version_key"] if previous_row is not None else "-"
        previous_range = f"{previous_row['train_start_date']} ~ {previous_row['train_end_date']}" if previous_row is not None else "-"
        render_card("上一版模型", previous_key, f"训练区间：{previous_range}")
    with col3:
        render_card("正式历史模型版本", f"{len(versions_df)} 个", "只展示正式训练版本，不展示回退时生成的内部备份目录。")


def render_log_panel() -> None:
    logs = st.session_state.app_logs[-120:]
    body_html = "<br>".join(html.escape(log) for log in logs) if logs else "暂无运行日志"
    render_template(
        "log_panel.html",
        current_status=html.escape(st.session_state.current_status),
        body_html=body_html,
    )


def render_train_tab() -> None:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header"><div class="section-title">训练中心</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="hint-text">支持使用日期组件选择训练时间范围。每次手动重训都会生成正式模型，并自动保留当前模型、上一版模型、历史训练日志与指标。</div>', unsafe_allow_html=True)
    render_toolbar("训练参数设置", "当前前端资源已拆分到独立 HTML / JS / CSS 文件中，Python 仅负责加载模板和传递数据。", ["模板化前端", "默认启用起止日期", "保留版本与日志"])

    enable_start = st.checkbox("启用训练起始日期", value=True)
    enable_end = st.checkbox("启用训练结束日期", value=True)
    col1, col2, col3, col4 = st.columns(4)
    start_date = col1.date_input("训练起始日期", value=date(2025, 1, 1), disabled=not enable_start)
    end_date = col2.date_input("训练结束日期", value=date(2026, 3, 31), disabled=not enable_end)
    valid_days = col3.number_input("验证集天数", min_value=1, max_value=90, value=14)
    num_boost_round = col4.number_input("训练轮数", min_value=50, max_value=3000, value=400, step=50)
    default_weights = normalize_similarity_weights(load_training_preferences(MODEL_ROOT).get("similarity_weights"))
    st.markdown('<div class="subsection-title">相似法权重</div>', unsafe_allow_html=True)
    weight_col1, weight_col2, weight_col3, weight_col4, weight_col5 = st.columns(5)
    net_load_weight = weight_col1.number_input("火电空间权重", min_value=0.0, value=float(default_weights["thermal_space"]), step=0.01)
    renewable_weight = weight_col2.number_input("新能源权重", min_value=0.0, value=float(default_weights["renewable_power"]), step=0.01)
    thermal_weight = weight_col3.number_input("火电容量权重", min_value=0.0, value=float(default_weights["thermal_on_capacity"]), step=0.01)
    day_type_weight = weight_col4.number_input("日期类型权重", min_value=0.0, value=float(default_weights["day_type"]), step=0.01)
    ratio_weight = weight_col5.number_input("供需比权重", min_value=0.0, value=float(default_weights["thermal_space_load_ratio"]), step=0.01)

    render_path_box(
        [
            f"历史数据目录：<code>{html.escape(str(HISTORY_DIR))}</code>",
            f"模型目录：<code>{html.escape(str(MODEL_ROOT))}</code>",
        ]
    )
    render_range_tip("业务约束：山西省日前电价预测结果统一限制在 0 ~ 1500 元/兆瓦时。该约束已写入核心预测链路，网页端、命令行和导出文件会保持一致。")

    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    callback = make_progress_callback(progress_bar, status_placeholder)

    if st.button("手动重训模型", type="primary", use_container_width=True):
        add_log("收到重训指令")
        similarity_weights = {
            "thermal_space": float(net_load_weight),
            "renewable_power": float(renewable_weight),
            "thermal_on_capacity": float(thermal_weight),
            "day_type": float(day_type_weight),
            "thermal_space_load_ratio": float(ratio_weight),
        }
        save_training_preferences(MODEL_ROOT, {"similarity_weights": similarity_weights})
        result = train_and_register(
            TrainConfig(
                history_dir=HISTORY_DIR,
                model_root=MODEL_ROOT,
                valid_days=int(valid_days),
                num_boost_round=int(num_boost_round),
                start_date=start_date.isoformat() if enable_start else None,
                end_date=end_date.isoformat() if enable_end else None,
                similarity_weights=similarity_weights,
            ),
            progress_callback=callback,
        )
        st.success(f"训练完成，当前默认模型：{result.run_id}")

        metrics_df = pd.DataFrame(result.metrics).T.reset_index().rename(
            columns={
                "index": "分时段",
                "baseline_mae": "相似法MAE",
                "baseline_rmse": "相似法RMSE",
                "final_mae": "融合MAE",
                "final_rmse": "融合RMSE",
                "train_rows": "训练样本数",
                "valid_rows": "验证样本数",
                "best_iteration": "最佳迭代轮次",
            }
        )
        summary_col1, summary_col2, summary_col3 = st.columns(3)
        with summary_col1:
            render_card("训练样本日期", f"{result.train_dates[0]} ~ {result.train_dates[-1]}", "本次用于训练的正式样本日期区间", "metric-card")
        with summary_col2:
            render_card("验证样本日期", f"{result.valid_dates[0]} ~ {result.valid_dates[-1]}", "本次用于验证的样本日期区间", "metric-card")
        with summary_col3:
            render_card("跳过工作表", str(len(result.skipped_sheets)), "字段缺失或格式异常时会记录到训练日志", "metric-card")

        st.markdown('<div class="subsection-title">分时段训练指标</div>', unsafe_allow_html=True)
        st.dataframe(metrics_df, width="stretch", hide_index=True)
        if result.skipped_sheets:
            st.warning("以下工作表因字段缺失或格式异常被跳过：")
            st.write(result.skipped_sheets)
    st.markdown("</div>", unsafe_allow_html=True)


def render_prediction_metrics(display_df: pd.DataFrame) -> None:
    final_price = display_df["最终预测价格"].astype(float)
    baseline_price = display_df["相似法基线价格"].astype(float)
    residual = display_df["模型残差修正值"].astype(float)
    cards = [
        ("预测日期", str(display_df["日期"].iloc[0]), "本次输出的 96 点预测日期"),
        ("平均预测价格", f"{final_price.mean():.2f}", "96 点最终预测价格平均值"),
        ("最高预测价格", f"{final_price.max():.2f}", "96 点预测价格峰值"),
        ("最低预测价格", f"{final_price.min():.2f}", "96 点预测价格谷值"),
        ("相似法均价", f"{baseline_price.mean():.2f}", "相似法基线的平均价格"),
        ("残差修正均值", f"{residual.mean():.2f}", "模型对相似法的平均修正幅度"),
    ]
    cols = st.columns(3)
    for idx, (title, value, desc) in enumerate(cards):
        with cols[idx % 3]:
            render_card(title, value, desc, "metric-card")


def render_prediction_chart(display_df: pd.DataFrame) -> None:
    line_df = display_df[["时段", "最终预测价格", "相似法基线价格"]].copy().melt("时段", var_name="曲线", value_name="价格")
    residual_df = display_df[["时段", "模型残差修正值"]].copy()

    line_chart = (
        alt.Chart(line_df)
        .mark_line(point=True, strokeWidth=2.4)
        .encode(
            x=alt.X("时段:Q", title="时段"),
            y=alt.Y("价格:Q", title="价格（元/MWh）"),
            color=alt.Color("曲线:N", scale=alt.Scale(domain=["最终预测价格", "相似法基线价格"], range=["#1677ff", "#fa8c16"]), legend=alt.Legend(title=None)),
            tooltip=["时段", "曲线", alt.Tooltip("价格:Q", format=".2f")],
        )
    )
    residual_chart = (
        alt.Chart(residual_df)
        .mark_bar(opacity=0.18, color="#52c41a")
        .encode(
            x=alt.X("时段:Q", title="时段"),
            y=alt.Y("模型残差修正值:Q", title="残差修正值"),
            tooltip=["时段", alt.Tooltip("模型残差修正值:Q", format=".2f")],
        )
    )
    chart = (
        alt.layer(residual_chart, line_chart)
        .resolve_scale(y="independent")
        .properties(height=360)
        .configure_view(strokeOpacity=0)
        .configure_axis(labelColor="#4e5969", titleColor="#1d2129", gridColor="rgba(31,35,41,0.08)")
        .configure_legend(labelColor="#4e5969")
    )
    st.altair_chart(chart, width="stretch")


def render_predict_tab() -> None:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header"><div class="section-title">预测中心</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="hint-text">可直接修改预测模板中的数值。点击执行预测后，会显示进度条、步骤状态和运行日志，并自动回填“预测价格”列，同时导出独立结果文件。</div>', unsafe_allow_html=True)
    render_toolbar("预测操作区", "页面下方表格支持直接编辑；保存仅更新模板，执行预测会调用当前默认模型并自动回填。", ["自动回填预测价格", "96 点输出", "价格区间保护"])
    render_range_tip("预测输出增加区间保护：最终预测价格低于 0 时按 0 输出，高于 1500 时按 1500 输出。")

    if not FORECAST_FILE.exists():
        st.error(f"未找到预测文件：{FORECAST_FILE}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    workbook = pd.read_excel(FORECAST_FILE, sheet_name=None)
    non_empty = [(name, df) for name, df in workbook.items() if not df.empty]
    if not non_empty:
        st.warning("预测文件中没有可编辑的工作表。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    sheet_name, sheet_df = non_empty[0]
    info_col1, info_col2, info_col3 = st.columns(3)
    with info_col1:
        render_card("当前预测工作表", sheet_name, "系统默认读取第一个非空工作表", "metric-card")
    with info_col2:
        render_card("模板文件位置", FORECAST_FILE.name, "执行预测时会把结果自动回填到该文件", "metric-card")
    with info_col3:
        render_card("输出结果文件", OUTPUT_FILE.name, "另存一份完整预测结果，方便留档和复盘", "metric-card")

    render_chip_row([f"当前表共 {len(sheet_df)} 行", "可直接在页面编辑", "支持保存后再预测"])
    edited_df = st.data_editor(sheet_df, num_rows="fixed", width="stretch", key="forecast_editor")
    reference_days = st.number_input("参考天数", min_value=1, max_value=30, value=1, step=1)

    progress_bar = st.progress(0)
    status_placeholder = st.empty()
    callback = make_progress_callback(progress_bar, status_placeholder)
    col_save, col_predict = st.columns(2)

    if col_save.button("保存当前预测页", use_container_width=True):
        with pd.ExcelWriter(FORECAST_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            edited_df.to_excel(writer, index=False, sheet_name=sheet_name)
        add_log("预测文件已保存")
        st.success("预测文件已保存")

    if col_predict.button("执行预测", type="primary", use_container_width=True):
        add_log("收到执行预测指令")
        with pd.ExcelWriter(FORECAST_FILE, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            edited_df.to_excel(writer, index=False, sheet_name=sheet_name)
        result = predict_prices(
            history_dir=HISTORY_DIR,
            forecast_file=FORECAST_FILE,
            model_root=MODEL_ROOT,
            output_file=OUTPUT_FILE,
            reference_days=int(reference_days),
            progress_callback=callback,
        )
        st.session_state.last_predict_df = result.result_df.copy()
        st.session_state.last_predict_date = result.forecast_date
        st.success(f"预测完成，预测日：{result.forecast_date}")

    if st.session_state.last_predict_df is not None:
        display_df = chinese_result_df(st.session_state.last_predict_df)
        render_prediction_metrics(display_df)

        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-header"><div class="section-title">预测曲线对比</div></div>', unsafe_allow_html=True)
        render_chip_row(["蓝线：最终预测价格", "橙线：相似法基线价格", "绿色柱：残差修正值"])
        render_prediction_chart(display_df)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-header"><div class="section-title">预测结果明细</div></div>', unsafe_allow_html=True)
        render_chip_row(["已中文化字段", "可横向滚动查看", "适合导出后复盘"])
        st.dataframe(display_df, width="stretch", hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_selected_version_details(selected_row: pd.Series) -> None:
    version_metadata = read_json(Path(selected_row["path"]) / "metadata.json")
    metrics = version_metadata.get("metrics", {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_card("模型编号", selected_row["run_id"], "该版本的唯一训练编号", "metric-card")
    with col2:
        render_card("训练时间", format_time_text(selected_row["created_at"]), "模型正式训练完成时间", "metric-card")
    with col3:
        render_card("训练区间", f"{selected_row['train_start_date']} ~ {selected_row['train_end_date']}", "该版本使用的历史样本时间范围", "metric-card")
    with col4:
        render_card("样本行数", str(selected_row["sample_rows"]), "该版本的总样本行数", "metric-card")

    st.markdown('<div class="subsection-title">所选模型分时段指标</div>', unsafe_allow_html=True)
    if metrics:
        metrics_df = pd.DataFrame(metrics).T.reset_index().rename(
            columns={
                "index": "分时段",
                "baseline_mae": "相似法MAE",
                "baseline_rmse": "相似法RMSE",
                "final_mae": "融合MAE",
                "final_rmse": "融合RMSE",
                "train_rows": "训练样本数",
                "valid_rows": "验证样本数",
                "best_iteration": "最佳迭代轮次",
            }
        )
        st.dataframe(metrics_df, width="stretch", hide_index=True)
    else:
        st.info("该版本暂未找到分时段指标信息。")

    xgb_params = version_metadata.get("xgboost_params", {})
    if xgb_params:
        params_text = "；".join(f"{key}={value}" for key, value in xgb_params.items())
        render_path_box([f"本版本 XGBoost 参数：<code>{html.escape(params_text)}</code>"])


def render_version_tab() -> None:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-header"><div class="section-title">模型版本管理</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="hint-text">这里仅展示正式训练版本，不展示回退时生成的内部备份目录。切换到旧模型时，当前模型会自动保留为“上一版模型”。</div>', unsafe_allow_html=True)
    render_toolbar("版本操作区", "你可以设置默认模型、回退到上一版、单独删除或批量删除历史模型。默认模型不能直接删除。", ["正式版本列表", "支持回退", "支持批量删除"])

    versions_df = list_model_versions(MODEL_ROOT)
    if versions_df.empty:
        st.info("暂无历史模型版本。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    versions_df["显示名称"] = versions_df.apply(format_version_label, axis=1)
    selected_label = st.selectbox("选择一个历史模型版本", options=versions_df["显示名称"].tolist())
    selected_row = versions_df[versions_df["显示名称"] == selected_label].iloc[0]

    action_col1, action_col2 = st.columns(2)
    if action_col1.button("设为默认模型", type="primary", use_container_width=True):
        current_dir = activate_model_version(MODEL_ROOT, selected_row["version_key"])
        add_log(f"已切换默认模型为：{selected_row['version_key']}")
        st.success(f"已设为默认模型：{selected_row['version_key']} ({current_dir})")
        st.rerun()

    if action_col2.button("回退到上一版模型", use_container_width=True):
        current_dir = rollback_to_previous(MODEL_ROOT)
        add_log("已执行回退到上一版模型")
        st.success(f"已回退到上一版模型：{current_dir}")
        st.rerun()

    render_selected_version_details(selected_row)

    delete_targets = st.multiselect(
        "选择要删除的历史模型版本（可多选）",
        options=versions_df["显示名称"].tolist(),
        placeholder="可选择一个或多个历史模型版本",
    )
    if st.button("删除选中模型版本", use_container_width=True):
        selected_rows = versions_df[versions_df["显示名称"].isin(delete_targets)].copy()
        protected = selected_rows[selected_rows["is_default"]]
        if not protected.empty:
            st.error("默认模型不能直接删除，请先切换默认模型后再删除。")
        else:
            version_keys = selected_rows["version_key"].tolist()
            deleted = delete_model_versions(MODEL_ROOT, version_keys)
            add_log(f"已删除模型版本：{', '.join(deleted) if deleted else '无可删除项'}")
            st.success(f"已删除：{', '.join(deleted)}" if deleted else "未删除任何模型")
            st.rerun()

    display_df = versions_df.rename(
        columns={
            "version_key": "版本目录",
            "run_id": "模型编号",
            "created_at": "训练时间",
            "train_start_date": "训练起始日期",
            "train_end_date": "训练结束日期",
            "sample_rows": "样本行数",
            "is_default": "是否默认",
            "is_previous": "是否上一版",
        }
    )
    st.markdown('<div class="subsection-title">正式模型版本列表</div>', unsafe_allow_html=True)
    st.dataframe(
        display_df[["版本目录", "模型编号", "训练时间", "训练起始日期", "训练结束日期", "样本行数", "是否默认", "是否上一版"]],
        width="stretch",
        hide_index=True,
    )

    logs_df = load_training_log(MODEL_ROOT)
    if not logs_df.empty:
        logs_df = logs_df.sort_values("created_at", ascending=False).rename(
            columns={
                "run_id": "模型编号",
                "created_at": "训练时间",
                "train_start_date": "训练起始日期",
                "train_end_date": "训练结束日期",
                "sample_rows": "样本行数",
            }
        )
        st.markdown('<div class="subsection-title">训练日志</div>', unsafe_allow_html=True)
        show_cols = [col for col in ["模型编号", "训练时间", "训练起始日期", "训练结束日期", "样本行数"] if col in logs_df.columns]
        st.dataframe(logs_df[show_cols], width="stretch", hide_index=True)
    st.markdown("</div>", unsafe_allow_html=True)


init_state()
render_css()
inject_local_frontend_behaviors()
render_header()
render_top_status()
render_summary_cards()

tab_train, tab_predict, tab_versions = st.tabs(["训练中心", "预测中心", "模型版本"])

with tab_train:
    render_train_tab()

with tab_predict:
    render_predict_tab()

with tab_versions:
    render_version_tab()

render_log_panel()
