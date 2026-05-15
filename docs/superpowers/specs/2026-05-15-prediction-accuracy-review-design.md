# Prediction Accuracy Review Design

## Goal

Build a prediction archive and accuracy review feature. Every prediction button click should preserve the actual generated 96-point prediction result unless it is a duplicate of an existing record for the same date, strategy, model setup, and rounded prediction curve. Later, when actual day-ahead prices are available in historical Excel files, the prediction page can compare the saved prediction curve against actual prices.

## Confirmed Requirements

- Save only the prediction result actually produced by the current prediction run.
- Do not iterate through weaker model combinations or old segment-count model versions.
- If the same date is predicted multiple times and the model setup plus rounded 96-point final prediction curve are unchanged, do not save a duplicate record.
- Duplicate comparison rounds final prediction prices to 2 decimals.
- If model version, segment model selection, strategy, reference days, or rounded 96-point prediction changes, save a new record.
- Actual prices are matched only from historical Excel data.
- If no actual price exists, show a friendly “暂无实际价格数据” message.
- Default review chart curves:
  - 最终预测价格
  - 实际日前价格
  - 仅净负荷相似基线
- Additional model and prediction metadata is shown in a default-collapsed details panel.
- The UI should be compact, clean, and visually polished.

## Data Storage

Use local JSON files under:

```text
output/prediction_archive/
```

Each saved prediction record is a JSON file. A lightweight `index.json` tracks records by date for quick listing.

The archive record stores:

- archive id
- forecast date
- created time
- model run id
- model type
- segment count and segment configuration
- selected segment price models
- prediction strategy
- reference strategy label
- reference days
- reference dates
- similarity weights
- price interval model metadata
- forecast file and output file path
- rows for 96 points, including predicted price, multi-condition baseline, net-load-only baseline, and interval fields
- duplicate fingerprint

## Actual Price Matching

When reviewing a saved prediction:

1. Load historical Excel data through existing history parsing functions.
2. Find rows matching the forecast date.
3. Extract period and actual day-ahead clearing price.
4. Join actual prices with archived prediction rows by period.
5. Compute metrics when actual prices are complete or partially available.

## Backend API

Add endpoints:

```text
GET /api/prediction-archive?date=YYYY-MM-DD
GET /api/prediction-archive/{archive_id}
```

The list endpoint returns saved records for a date.

The detail endpoint returns:

- archive record
- matched actual price rows if found
- comparison rows
- metrics
- message when no actual price data is available

## Frontend UI

Add a compact card on the prediction page:

- title: 预测准确率回查
- date input
- refresh/search button
- record dropdown
- metric chips
- chart panel
- default collapsed detail panel

Chart defaults:

- 最终预测价格
- 实际日前价格
- 仅净负荷相似基线

If actual prices are unavailable, the chart shows prediction and net-load-only baseline, while a small hint says actual price is not available yet.

