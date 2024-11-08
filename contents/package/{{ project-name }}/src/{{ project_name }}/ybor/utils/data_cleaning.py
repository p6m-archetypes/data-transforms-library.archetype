from pyspark.sql import functions as F


class DataCleaning:
    def clean(self, data, cleaning_config):
        if cleaning_config["standardize_column_names"]:
            data = self._standardize_column_names(data)
        data = self._cast_columns(data, cleaning_config.get("cast_columns", {}))
        data = self._replace_default_values(
            data, cleaning_config.get("replace_default_values", {})
        )
        data = self._apply_udfs(data, cleaning_config.get("user_defined_functions", []))
        return data

    def _standardize_column_names(self, data):
        for column in data.columns:
            data = data.withColumnRenamed(column, column.lower())
        return data

    def _cast_columns(self, data, columns_to_cast):
        for column, dtype in columns_to_cast.items():
            data = data.withColumn(column, data[column].cast(dtype))
        return data

    def _replace_default_values(self, data, default_values):
        for column, value in default_values.items():
            data = data.withColumn(
                column, F.when(data[column].isNull(), value).otherwise(data[column])
            )
        return data

    def _apply_udfs(self, data, udfs):
        for udf in udfs:
            module = __import__(udf["module"])
            function = getattr(module, udf["function"])
            data = data.withColumn(udf["name"], function(data[udf["name"]]))
        return data
