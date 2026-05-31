# Multi-Day Price Prediction Design

## Goal

Add an independent "预测多天价格" page that predicts multiple future days from `预测文件/预测文件-N天.xlsx`, while reusing the existing single-day prediction model, similarity, KNN, weighted KNN, and price interval logic.

## Confirmed Behavior

- The left sidebar gains a new tab named `预测多天价格`.
- The page is separate from the current `预测中心` page.
- The page mirrors the current `执行预测` controls, but removes all same-type-day controls and same-type-day charts.
- The input file is `预测文件/预测文件-N天.xlsx`.
- The input sheet has one header row and 96 data rows.
- Baseline-day columns contain renewable power, total load, net load, actual day-ahead clearing price, and thermal online capacity.
- Future-day columns are dynamic pairs of renewable power and total load, one pair per forecast date.
- Future-day net load is calculated as total load minus renewable power.
- Future-day thermal online capacity uses the baseline-day capacity.
- Future-day lag/base price uses the baseline-day actual day-ahead clearing price.
- Future days do not recursively use the prior future day's predicted price.
- Each forecast day is predicted independently by the current model.
- The result displays one chart card per forecast day.
- Each day shows model predicted price, net-load similarity price, KNN similarity price, weighted KNN regression price, and price interval information.
- Export creates one workbook with one sheet per forecast day.
- In each export sheet, row 1 contains method names with the date; rows 2-97 contain the 96 period values.

## Architecture

The feature adds a multi-day adapter around the existing prediction pipeline. The adapter parses the multi-day Excel file into per-day forecast frames that match the single-day predictor's expected shape, runs the existing predictor once per future day using the `recent_n_days` reference strategy, and returns a bundle of day-level prediction results.

The frontend gets a new tab, a new file preview table, a multi-day run progress card, one ECharts instance per forecast day, and an export button that downloads the server-produced workbook.

## Backend Design

Create focused helpers in `dayahead_core.py`:

- `parse_multi_day_forecast_workbook(path)` reads `预测文件-N天.xlsx`, detects the baseline date and dynamic future dates from headers, and returns normalized rows.
- `build_multi_day_forecast_frame(...)` converts one future date into the same column layout as the current single-day forecast loader.
- `predict_multi_day_prices(...)` loops through detected forecast days and reuses the existing prediction function with `reference_strategy="recent_n_days"`.
- `export_multi_day_prediction_workbook(...)` writes one workbook with one sheet per forecast day.

Add API endpoints in `api_server.py`:

- `GET /api/forecast/multi-day-template` returns preview rows and detected days.
- `POST /api/forecast/multi-day-template/save` saves edited preview data back to `预测文件-N天.xlsx`.
- `POST /api/predict-multi-day` starts a background job and stores the last multi-day prediction.
- `GET /api/predict-multi-day/export` downloads the generated workbook.

## Frontend Design

Update `frontend_app/index.html`:

- Add a sidebar tab button for `预测多天价格`.
- Add a `tab-predict-multi-day` panel.
- Reuse the existing prediction control visual language.
- Include model version selection, recent-day reference count, KNN controls, weighted KNN controls, template reload/save, run, stop, and export.
- Include a preview table for `预测文件-N天.xlsx`.
- Include a result region that renders one chart card per forecast date.

Update `frontend_app/assets/app.js`:

- Add multi-day state fields.
- Add loader/saver for the multi-day workbook.
- Add runner for `/api/predict-multi-day`.
- Render each forecast date with the same chart series used by the recent-N-days single-day chart.
- Add export handling for `/api/predict-multi-day/export`.

Update `frontend_app/assets/app.css` only if existing prediction card styles need small layout support for multiple day cards.

## Error Handling

- If no future-day pairs are detected, show a clear error.
- If a future day has fewer than 96 usable rows, fail the job with the date and row count.
- If baseline actual price or thermal online capacity is missing, fail before running predictions.
- If the export is requested before a successful multi-day prediction, return a clear API error.

## Verification

- Unit tests cover parsing dynamic future-day columns, baseline capacity propagation, baseline price reuse, and export workbook shape.
- API tests cover preview and export paths.
- Frontend static tests cover the new sidebar tab, absence of same-type-day controls on the new page, and presence of multi-day export UI.
