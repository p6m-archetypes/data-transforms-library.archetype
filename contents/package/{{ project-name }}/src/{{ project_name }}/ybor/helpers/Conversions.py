import pyspark.sql.functions as F
from pyspark.sql.types import LongType, TimestampType, StringType


class Conversions:
    """
    Conversion functions take a spark column type and return a spark column type.
    """

    @staticmethod
    def char_to_boolean(input_column):
        return F.when(F.lower(input_column).isin('y', 'yes'), F.lit(True)) \
            .when(F.lower(input_column).isin('n', 'no'), F.lit(False)) \
            .otherwise(None)

    @staticmethod
    def int_to_boolean(input_column):
        return F.when(input_column == F.lit(1), F.lit(True)) \
            .when(input_column == F.lit(0), F.lit(False)) \
            .otherwise(None)

    @staticmethod
    def lower(input_column):
        return F.lower(Conversions.nullify(input_column))

    @staticmethod
    def normalize_gender(input_column):
        return F.when(F.lower(input_column) == F.lit("female"), F.lit("F")) \
            .when(F.lower(input_column) == F.lit("male"), F.lit("M")) \
            .otherwise(None)

    @staticmethod
    def nullify(input_column):
        null_values = [
            'NA',
            'N/A',
            'n/a'
            'na',
            'Na',
            '',
            'Not Applicable',
            'Unknown',
        ]
        return F.when(F.trim(input_column).isin(null_values), None) \
            .otherwise(F.trim(input_column))

    @staticmethod
    def clean_date_range(input_col):
        return F.when(((input_col > F.lit('1970-01-01').cast('date')) & (input_col <= F.lit(F.current_date()))),
                      input_col) \
            .otherwise(None)

    @staticmethod
    def nullify_future_dates(col):
        return F.when(col > F.current_timestamp(), F.lit(None)) \
            .otherwise(col)

    @staticmethod
    def round_decimal(input_column, scale=4):
        return F.bround(input_column, scale=scale)

    @staticmethod
    def date_from_string(input_column, source_format="yyyy-MM-dd", target_format="yyyy-MM-dd"):
        return F.date_format(F.to_date(input_column, source_format), target_format)

    @staticmethod
    def epoch_to_timestamp(input_column):
        """
        Intelligently converts epoch timestamps to timestamps, handling:
        - Both string and long input types
        - Seconds, milliseconds, and nanoseconds precision
        - Invalid/null values

        Args:
            input_column: Spark Column containing epoch values
        Returns:
            Spark Column with converted timestamp
        """
        # First cast string to long if needed
        numeric_col = F.when(input_column.cast(LongType()).isNotNull(),
                             input_column.cast(LongType())) \
            .otherwise(None)

        # Helper function to convert based on timestamp length
        def convert_by_length(col):
            # Get number of digits to determine if seconds, millis, or nanos
            length = F.length((F.abs(col).cast(StringType())))

            return F.when(length <= 10,
                          # Seconds (standard epoch)
                          F.from_unixtime(col).cast(TimestampType())) \
                .when(length <= 13,
                      # Milliseconds
                      F.from_unixtime(col / 1000).cast(TimestampType())) \
                .when(length <= 19,
                      # Nanoseconds
                      F.from_unixtime(col / 1000000000).cast(TimestampType())) \
                .otherwise(None)

        return F.when(numeric_col.isNotNull(),
                      convert_by_length(numeric_col)) \
            .otherwise(None)

