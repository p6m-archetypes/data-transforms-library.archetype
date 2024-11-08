from pyspark.sql.functions import (
    col,
    sum,
    count,
    countDistinct,
    when,
    lit,
    split,
    concat_ws,
)
import pyspark.sql.functions as F
from {{ project_prefix }}.ybor.utils.transformation_util import TransformationsUtil


class DataTransformer:
    def __init__(self, dfs, transformations):
        self.dfs = dfs
        self.transformations = transformations

    def apply_transformations(self):
        df = None
        for key, value in self.dfs.items():
            df = self.dfs[key]
            print(f"Applying transformations on DataFrame: {key}, total records: {df.count()}")

        if "aggregation" in self.transformations:
            aggregation = self.transformations["aggregation"]
            type = aggregation["type"]
            group_by = aggregation.get("group_by", [])
            metrics = aggregation.get("metrics", [])
            agg_exprs = self._generate_agg_exprs(metrics)
            if type == "groupby":
                df = df.groupBy(*[col(g) for g in group_by]).agg(*agg_exprs)
            elif type == "cube":
                df = df.cube(*[col(g) for g in group_by]).agg(*agg_exprs)
            elif type == "rollup":
                df = df.rollup(*[col(g) for g in group_by]).agg(*agg_exprs)

        if "cleaning" in self.transformations:
            df = self._apply_cleaning(df)

        return df

    def _generate_agg_exprs(self, metrics):
        agg_exprs = []
        for metric in metrics:
            column = metric["column"]
            function = metric["function"]
            if function == "sum":
                agg_exprs.append(sum(col(column)).alias(f"{column}_sum"))
            elif function == "count":
                agg_exprs.append(count(col(column)).alias(f"{column}_count"))
            elif function == "count_non_null":
                agg_exprs.append(
                    count(when(col(column).isNotNull(), col(column))).alias(
                        f"{column}_count_non_null"
                    )
                )
            elif function == "percent_non_null":
                agg_exprs.append(
                    (
                        count(when(col(column).isNotNull(), col(column)))
                        / count(lit(1))
                        * 100
                    ).alias(f"{column}_percent_non_null")
                )
            elif function == "percent_null":
                agg_exprs.append(
                    (
                        count(when(col(column).isNull(), col(column)))
                        / count(lit(1))
                        * 100
                    ).alias(f"{column}_percent_null")
                )
            elif function == "distinct_count":
                agg_exprs.append(
                    countDistinct(col(column)).alias(f"{column}_distinct_count")
                )
            # Add more metric functions as needed
        return agg_exprs

    def _apply_derived_columns(self, df, derived_columns):
        for output_column, derived in derived_columns.items():
            new_column = output_column
            operation = derived["operation"]
            params = derived["params"]

            if operation == "split":
                delimiter = params["delimiter"]
                index = params["index"]
                input_column = params["input_column"]
                df = df.withColumn(
                    new_column, split(col(input_column), delimiter).getItem(index)
                )
            elif operation == "concat":
                separator = params["separator"]
                columns = params["input_columns"]
                df = df.withColumn(
                    new_column, concat_ws(separator, *[col(c) for c in columns])
                )
            elif operation == "concat_hash":
                separator = params.get("separator", "-")
                columns = params["input_columns"]
                hash_type = params.get("hash_type", "md5")
                if hash_type == "md5":
                    df = df.withColumn(
                        new_column,
                        F.md5(concat_ws(separator, *[col(c) for c in columns])),
                    )
                elif hash_type == "sha1":
                    df = df.withColumn(
                        new_column,
                        F.sha1(concat_ws(separator, *[col(c) for c in columns])),
                    )
                elif hash_type == "sha256":
                    df = df.withColumn(
                        new_column,
                        F.sha2(concat_ws(separator, *[col(c) for c in columns]), 256),
                    )
                elif hash_type == "xxhash64":
                    df = df.withColumn(
                        new_column,
                        F.xxhash64(concat_ws(separator, *[col(c) for c in columns])),
                    )
            # Add more operations as needed

        return df

    def _apply_cleaning(self, df):
        cleaning = self.transformations["cleaning"]
        df = TransformationsUtil.clean_df(df, cleaning)
        if "add_static_columns" in cleaning:
            static_mapping = cleaning["add_static_columns"]
            for key, val in static_mapping.items():
                if val.startswith("F."):
                    # Evaluate the string value as a PySpark function expression
                    evaluated_value = eval(val)
                    df = df.withColumn(key, evaluated_value)
                else:
                    # Use the literal value directly
                    df = df.withColumn(key, lit(val))
        if "derived_columns" in cleaning:
            derived_columns = cleaning["derived_columns"]
            df = self._apply_derived_columns(df, derived_columns)
        if "drop_columns" in cleaning:
            df = df.drop(*cleaning["drop_columns"])
        return df
