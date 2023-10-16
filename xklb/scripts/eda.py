import argparse
from typing import Dict

from xklb import usage
from xklb.utils import nums
from xklb.utils.consts import DEFAULT_FILE_ROWS_READ_LIMIT
from xklb.utils.file_utils import read_file_to_dataframes
from xklb.utils.printing import print_df


def parse_args():
    parser = argparse.ArgumentParser(description="Perform EDA on one or more files", usage=usage.eda)
    parser.add_argument("--table-name", "--table", "-t")
    parser.add_argument("--table-index", type=int)
    parser.add_argument("--start-row", "--skiprows", type=int, default=None)
    parser.add_argument("--end-row", "--nrows", "--limit", "-L", default=str(DEFAULT_FILE_ROWS_READ_LIMIT))
    parser.add_argument("--sort", "-u", default="random()")
    parser.add_argument("--repl", "-r", action="store_true")
    parser.add_argument("--verbose", "-v", action="count", default=0)

    parser.add_argument(
        "paths",
        metavar="path",
        nargs="+",
        help="path to one or more files",
    )
    args = parser.parse_args()

    if args.end_row.lower() in ("inf", "none", "all"):
        args.end_row = None
    else:
        args.end_row = int(args.end_row)

    return args


def print_series(s):
    if len(s) > 0:
        print()
        print("\n".join([f"- {col}" for col in s]))
        print()


def df_column_values(df, column_name) -> Dict:
    total = len(df)

    null = df[column_name].isnull().sum()
    zero = (df[column_name] == 0).sum()
    empty = (df[column_name] == "").sum()
    values = total - empty - zero - null

    return {
        "values_count": values,
        "null_count": null,
        "zero_count": zero,
        "empty_string_count": empty,
        "column": column_name,
        "null": f"{null} ({nums.percent(null, total):.1f}%)",
        "zero": f"{zero} ({nums.percent(zero, total):.1f}%)",
        "empty_string": f"{empty} ({nums.percent(empty, total):.1f}%)",
        "values": f"{values} ({nums.percent(values, total):.1f}%)",
    }


def print_info(args, df):
    import pandas as pd

    if df.shape == (0, 0):
        print(f"Table [{df.name}] empty")
        return

    if args.end_row is None:
        partial_dataset_msg = ""
    elif args.end_row == DEFAULT_FILE_ROWS_READ_LIMIT:
        partial_dataset_msg = f"(limited by default --end-row {args.end_row})"
    else:
        partial_dataset_msg = f"(limited by --end-row {args.end_row})"
    if args.end_row is not None and args.end_row not in df.shape:
        partial_dataset_msg = ""
    print("### Shape")
    print()
    print(df.shape, partial_dataset_msg)
    print()

    print("### Sample of rows")
    print()
    if len(df) > 6:
        print_df(pd.concat([df.head(3), df.tail(3)]))
    else:
        print_df(df.head(6))
    print()

    print("### Summary statistics")
    print()
    print_df(df.describe())
    print()

    converted = df.convert_dtypes()
    same_dtypes = []
    diff_dtypes = []
    for col in df.columns:
        if df.dtypes[col] == converted.dtypes[col]:
            same_dtypes.append((col, df.dtypes[col]))
        else:
            diff_dtypes.append((col, df.dtypes[col], converted.dtypes[col]))
    if len(same_dtypes) > 0:
        print("### Pandas columns with 'original' dtypes")
        print()
        same_dtypes = pd.DataFrame(same_dtypes, columns=["column", "dtype"])
        print_df(same_dtypes.set_index("column"))
        print()
    if len(diff_dtypes) > 0:
        print("### Pandas columns with 'converted' dtypes")
        print()
        diff_dtypes = pd.DataFrame(diff_dtypes, columns=["column", "original_dtype", "converted_dtype"])
        print_df(diff_dtypes.set_index("column"))
        print()

    categorical_columns = [s for s in df.columns if pd.api.types.is_categorical_dtype(df[s])]
    if categorical_columns:
        print("### Categorical columns")
        print()
        for col in categorical_columns:
            print(col)
            print("#### values")
            print_df(df[col].value_counts(normalize=True))
            print("#### groupby")
            print_df(df.groupby(col).describe())
            print()

    numeric_columns = df.select_dtypes("number").columns.to_list()
    if numeric_columns and len(df) > 15:
        print("### Numerical columns")
        print()
        print("#### Bins")
        print()
        for col in numeric_columns:
            bins = pd.cut(df[col], bins=6)
            print_df(bins.value_counts().sort_index())
            print()

    print("### Missing values")
    print()
    nan_col_sums = df.isna().sum()
    print(
        f"{nan_col_sums.sum():,} nulls/NaNs",
        f"({(nan_col_sums.sum() / (df.shape[0] * df.shape[1])):.1%} dataset values missing)",
    )
    print()

    if nan_col_sums.sum():
        no_nas = df.columns[df.notnull().all()]
        if len(no_nas) > 0:
            print(f"#### {len(no_nas)} columns with no missing values")
            print_series(no_nas)

        all_nas = df.columns[df.isnull().all()]
        if len(all_nas) > 0:
            print(f"#### {len(all_nas)} columns with all missing values")
            print_series(all_nas)

        print("#### Value stats")
        column_report = pd.DataFrame(df_column_values(df, col) for col in df.columns).set_index("column")
        column_report = column_report.sort_values(["empty_string_count", "zero_count", "null_count"])
        print_df(column_report[["values", "null", "zero", "empty_string"]])
        print()


def file_eda(args, path):
    dfs = read_file_to_dataframes(
        path,
        table_name=args.table_name,
        table_index=args.table_index,
        start_row=args.start_row,
        end_row=args.end_row,
        order_by=args.sort,
    )
    if getattr(args, "repl", False):
        breakpoint()

    for df in dfs:
        print(f"## {path}:{df.name}")
        print_info(args, df)


def eda():
    args = parse_args()
    for path in args.paths:
        file_eda(args, path)


if __name__ == "__main__":
    eda()
