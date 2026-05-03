# Multi-Condition Similarity Design

## Goal

Use a new multi-condition similarity baseline for training and prediction while keeping the old net-load-only similarity curve as a prediction reference.

## Scope

- Training residuals use the new baseline: `actual_price - multi_condition_similar_price`.
- Prediction output keeps both `similar_price` (new baseline) and `net_load_only_similar_price` (old reference).
- Reference days support values from 1 to 100 in the UI and API accepts hand-entered positive integers.
- Holiday calendar is local-file based and supports `holiday` and `workday` overrides.

## Similarity Rules

- Candidate history points must have the same `period` as the target point.
- Candidate dates must be before the target date.
- Candidate dates are limited to the latest N prior dates.
- Similarity score uses normalized differences:
  - net load: 50%
  - renewable power: 20%
  - thermal-on capacity: 20%
  - day type: 10%
- Day type is `holiday`, `weekend`, or `workday`.

## Local Calendar

- File format: `date,type,name`.
- `holiday` makes that date a holiday.
- `workday` makes that date a workday even if it is Saturday or Sunday.
- Missing dates fall back to weekday/weekend logic.

## Verification

- Unit tests cover weighted same-period matching, old net-load reference output, and holiday/workday overrides.
- Existing history-cache and data-quality tests should continue to pass.
