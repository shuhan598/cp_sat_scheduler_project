# JSON Input Design

## Scope

Replace the order input workbook `input_orders.xlsx` with a JSON request file named `input_orders.json`.

The scheduling model, insert-order flow, power outage input, previous plan reader, and Excel result export stay unchanged. Power outage records continue to use `停电计划.xlsx` in this change.

## Input Contract

The JSON root object has two fields:

- `orders`: required array of base orders.
- `insert_orders`: optional array of inserted orders. Missing or empty means normal scheduling.

Base order object:

```json
{
  "order": "意诚",
  "quantity": 5700000,
  "earliest_start": "2026-05-01",
  "latest_finish": "2026-05-07"
}
```

Inserted order object:

```json
{
  "order": "宥阳",
  "quantity": 2000000,
  "insert_date": "2026-05-10",
  "earliest_start": "2026-05-10",
  "latest_finish": "2026-05-20"
}
```

Dates use `YYYY-MM-DD`. Quantities must be integers or strings that can be converted to integers. Empty order names are ignored, matching the previous Excel loader behavior.

## Architecture

Add JSON parsing functions to `scheduler_io/data_loader.py` that return the same `raw_orders` dictionaries currently produced by Excel parsing. This keeps `main.py`, `scheduler_workflow/normal_schedule_flow.py`, and `scheduler_workflow/insert_schedule_flow.py` connected to the same internal data shape.

Update `main.py` to read `INPUT_JSON_FILE` from `config.py` and call `load_raw_orders_for_insert_from_json()`. Keep Excel-oriented helper functions in place for compatibility, but the main application no longer uses them.

## Error Handling

The loader validates:

- root JSON must be an object;
- `orders` must exist and be an array;
- each base order must include `order`, `quantity`, `earliest_start`, and `latest_finish`;
- each inserted order must include `order`, `quantity`, `insert_date`, `earliest_start`, and `latest_finish`;
- quantity must convert to integer;
- dates must parse successfully;
- earliest start cannot be later than latest finish;
- insert date cannot be later than latest finish.

Error messages should mention JSON and the offending field or row index so the caller can fix the request file.

## Documentation

Create `docs/input_json_api.md` as the demand interface document. It should include the JSON schema by example, field table, validation rules, normal scheduling example, insert scheduling example, and runtime behavior.

Update `README.md` so it no longer describes Excel as the order input. Keep Excel result export documentation.

## Testing

Add focused pytest tests for the JSON loader:

- normal orders parse into existing raw order shape;
- inserted orders enable insert mode and compute the earliest insert date;
- missing `insert_orders` is treated as no insert;
- missing required fields raise `ValueError`;
- invalid date ranges raise `ValueError`.

Run the new test file first and confirm it fails before production implementation, then run it again after implementation and confirm it passes.
