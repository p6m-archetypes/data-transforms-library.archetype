from pyspark.sql import functions as F


class DataQualityChecker:
    def __init__(self, df, checks):
        self.data = df
        self.quality_config = checks

    def perform_checks(self):
        for check in self.quality_config["checks"]:
            if check["check_type"] == "null_check":
                self._null_check(self.data, check["columns"])
            elif check["check_type"] == "range_check":
                self._range_check(
                    self.data, check["column"], check["min"], check["max"]
                )

    def _null_check(self, data, columns):
        for column in columns:
            null_count = data.filter(F.col(column).isNull()).count()
            if null_count > 0:
                print(f"Column {column} has {null_count} null values.")

    def _range_check(self, data, column, min_value, max_value):
        out_of_range_count = data.filter(
            (F.col(column) < min_value) | (F.col(column) > max_value)
        ).count()
        if out_of_range_count > 0:
            print(
                f"Column {column} has {out_of_range_count} values out of the range [{min_value}, {max_value}]."
            )

    def publish_stats(self, data):
        print("Publishing data statistics...")
        data.describe().show()
