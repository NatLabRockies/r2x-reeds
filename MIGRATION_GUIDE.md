# Migration Guide: DataFile Structure Changes

## Overview

The DataFile configuration structure has been refactored to use nested organization for better clarity and maintainability. This guide helps you update your existing file mappings.

## Old Structure vs New Structure

### Old Flat Structure

```json
{
  "name": "pcm_defaults",
  "fpath": "pcm_defaults.json",
  "description": "Generator default parameters",
  "is_input": true,
  "is_optional": false,
  "is_timeseries": false,
  "units": "MW",
  "reader_function": null,
  "reader_kwargs": { "infer_schema_length": 5000 },
  "column_mapping": { "forced_outage_rate": "outage_rate" },
  "key_mapping": { "old_key": "new_key" },
  "drop_columns": ["internal_id"],
  "column_schema": { "capacity": "float" },
  "filter_by": { "status": "active" },
  "index_columns": ["tech"],
  "value_columns": ["capacity"],
  "pivot_on": "year",
  "aggregate_function": "sum",
  "sort_by": { "capacity": "desc" },
  "distinct_on": ["tech"],
  "replace_values": { "null": 0 },
  "fill_null": { "capacity": -1 }
}
```

### New Nested Structure

```json
{
  "name": "pcm_defaults",
  "fpath": "pcm_defaults.json",
  "info": {
    "description": "Generator default parameters",
    "is_input": true,
    "is_optional": false,
    "is_timeseries": false,
    "units": "MW"
  },
  "reader": {
    "kwargs": { "infer_schema_length": 5000 },
    "function": null
  },
  "proc_spec": {
    "column_mapping": { "forced_outage_rate": "outage_rate" },
    "key_mapping": { "old_key": "new_key" },
    "drop_columns": ["internal_id"],
    "column_schema": { "capacity": "float" },
    "filter_by": { "status": "active" },
    "select_columns": ["capacity"],
    "set_index": "tech",
    "pivot_on": "year",
    "aggregate_on": { "capacity": "sum" },
    "sort_by": { "capacity": "desc" },
    "distinct_on": ["tech"],
    "replace_values": { "null": 0 },
    "fill_null": { "capacity": -1 }
  }
}
```

## Migration Steps

### Step 1: Group Metadata Fields into `info`

Move these fields into the `info` object:

- `description`
- `is_input`
- `is_optional`
- `is_timeseries`
- `units`

Before:

```json
{
  "name": "my_file",
  "fpath": "data.csv",
  "description": "My data",
  "is_input": true,
  "is_optional": false
}
```

After:

```json
{
  "name": "my_file",
  "fpath": "data.csv",
  "info": {
    "description": "My data",
    "is_input": true,
    "is_optional": false
  }
}
```

### Step 2: Group Reader Configuration into `reader`

Move these fields into the `reader` object:

- `reader_function` → `function`
- `reader_kwargs` → `kwargs`

Before:

```json
{
  "name": "my_file",
  "fpath": "data.csv",
  "reader_function": null,
  "reader_kwargs": { "infer_schema_length": 1000 }
}
```

After:

```json
{
  "name": "my_file",
  "fpath": "data.csv",
  "reader": {
    "function": null,
    "kwargs": { "infer_schema_length": 1000 }
  }
}
```

### Step 3: Group Transformation Fields into `processing`

Move all transformation fields into the `processing` object. Field names change slightly:

- `index_columns` → `set_index` (string for single index)
- `value_columns` → `select_columns` (list of columns to keep)
- `aggregate_function` → `aggregate_on` (dict mapping columns to functions)

Before:

```json
{
  "name": "my_file",
  "fpath": "data.csv",
  "column_mapping": { "old": "new" },
  "drop_columns": ["unwanted"],
  "filter_by": { "status": "active" },
  "index_columns": ["tech"],
  "value_columns": ["capacity"],
  "aggregate_function": "sum"
}
```

After:

```json
{
  "name": "my_file",
  "fpath": "data.csv",
  "proc_spec": {
    "column_mapping": { "old": "new" },
    "drop_columns": ["unwanted"],
    "filter_by": { "status": "active" },
    "set_index": "tech",
    "select_columns": ["capacity"],
    "aggregate_on": { "capacity": "sum" }
  }
}
```

## Field Name Changes

The following field names have changed:

| Old Name             | New Location | New Name         |
| -------------------- | ------------ | ---------------- |
| `description`        | `info`       | `description`    |
| `is_input`           | `info`       | `is_input`       |
| `is_optional`        | `info`       | `is_optional`    |
| `is_timeseries`      | `info`       | `is_timeseries`  |
| `units`              | `info`       | `units`          |
| `reader_function`    | `reader`     | `function`       |
| `reader_kwargs`      | `reader`     | `kwargs`         |
| `index_columns`      | `processing` | `set_index`      |
| `value_columns`      | `processing` | `select_columns` |
| `aggregate_function` | `processing` | `aggregate_on`   |

All other transformation fields move to `processing` with unchanged names:

- `column_mapping`
- `key_mapping`
- `drop_columns`
- `column_schema`
- `filter_by`
- `pivot_on`
- `unpivot_on`
- `group_by`
- `sort_by`
- `distinct_on`
- `replace_values`
- `fill_null`
- `rename_index`

## Complete Example

### Old Configuration

```json
[
  {
    "name": "generators",
    "fpath": "inputs/generators.csv",
    "description": "Generator fleet data",
    "is_input": true,
    "is_optional": false,
    "is_timeseries": false,
    "units": "MW",
    "reader_kwargs": { "infer_schema_length": 10000 },
    "column_mapping": {
      "tech": "technology",
      "capacity_mw": "capacity"
    },
    "drop_columns": ["temporary_id"],
    "filter_by": { "status": "active" },
    "index_columns": ["technology"],
    "value_columns": ["capacity", "cost"]
  }
]
```

### New Configuration

```json
[
  {
    "name": "generators",
    "fpath": "inputs/generators.csv",
    "info": {
      "description": "Generator fleet data",
      "is_input": true,
      "is_optional": false,
      "is_timeseries": false,
      "units": "MW"
    },
    "reader": {
      "kwargs": { "infer_schema_length": 10000 },
      "function": null
    },
    "proc_spec": {
      "column_mapping": {
        "tech": "technology",
        "capacity_mw": "capacity"
      },
      "drop_columns": ["temporary_id"],
      "filter_by": { "status": "active" },
      "set_index": "technology",
      "select_columns": ["capacity", "cost"]
    }
  }
]
```

## Handling Deprecated Fields

### `index_columns` to `set_index`

Old: `"index_columns": ["tech", "region"]` (list)
New: `"set_index": "tech"` (string for primary index)

If you need multiple index columns, you may need to handle this in post-processing or adjust your workflow.

### `value_columns` to `select_columns`

Old: `"value_columns": ["capacity", "cost"]` (columns to keep)
New: `"select_columns": ["capacity", "cost"]` (same list, new name)

### `aggregate_function` to `aggregate_on`

Old: `"aggregate_function": "sum"` (single function for all)
New: `"aggregate_on": {"capacity": "sum", "cost": "mean"}` (specify function per column)

Example migration:

```json
{
  "old": "aggregate_function": "sum",
  "new": "aggregate_on": {"column1": "sum", "column2": "sum"}
}
```

## Processing Type Separation

Processing transformations are now separated by file type:

### For Tabular Files (CSV, TSV, HDF5)

Use all available fields in `processing`. Tabular-specific fields include:

- `select_columns`
- `set_index`
- `reset_index`
- `pivot_on`
- `unpivot_on`
- `group_by`
- `aggregate_on`
- `sort_by`
- `distinct_on`
- `fill_null`

### For JSON Files

Use JSON-appropriate fields in `processing`. JSON-specific fields include:

- `key_mapping` (rename keys instead of columns)

Common fields for both:

- `drop_columns`
- `filter_by`
- `rename_index`
- `replace_values`

Example JSON transformation:

```json
{
  "name": "pcm_defaults",
  "fpath": "pcm_defaults.json",
  "proc_spec": {
    "key_mapping": { "forced_outage_rate": "outage_rate" },
    "drop_columns": ["internal_id"],
    "filter_by": { "status": "active" },
    "replace_values": { "null": 0 },
    "rename_index": "technology"
  }
}
```

## Validation

After updating your file mappings, validate they work with:

```python
from r2x_core import DataStore

# Load with new structure
store = DataStore.from_json("config.json", path="./data")

# Read a file to ensure it works
data = store.read_data("your_file_name")
print(data)
```

## Troubleshooting

### "info is not defined"

You have metadata fields at the top level. Move `description`, `is_input`, `is_optional`, `is_timeseries`, and `units` into an `info` object.

### "reader is not defined"

You have `reader_function` or `reader_kwargs` at the top level. Move them to a `reader` object and rename:

- `reader_function` → `reader.function`
- `reader_kwargs` → `reader.kwargs`

### "processing is not defined"

You have transformation fields at the top level. Move all transformation fields into a `processing` object.

### Unknown field in processing

Check the field name hasn't changed (e.g., `index_columns` → `set_index`, `value_columns` → `select_columns`, `aggregate_function` → `aggregate_on`).

### Type mismatch in processing

Some fields changed types:

- `index_columns` was a list, `set_index` is a string
- `aggregate_function` was a string, `aggregate_on` is a dict

## Questions?

Refer to the main README.md for DataStore and DataFile documentation, or check the test files in `tests/test_data_file_refactor.py` for usage examples.
