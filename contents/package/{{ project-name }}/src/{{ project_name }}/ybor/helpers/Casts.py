import pyspark.sql.types as T


class Casts:
    """
    Cast functions take a spark column type and return a spark column type.
    """

    @staticmethod
    def to_date(input_column):
        return input_column.cast(T.DateType())

    @staticmethod
    def to_decimal(input_column):
        return input_column.cast(T.DecimalType())

    @staticmethod
    def to_integer(input_column):
        return input_column.cast(T.IntegerType())

    @staticmethod
    def to_long(input_column):
        return input_column.cast(T.LongType())

    @staticmethod
    def to_string(input_column):
        return input_column.cast(T.StringType())

    @staticmethod
    def to_double(input_column):
        return input_column.cast(T.DoubleType())

    @staticmethod
    def to_float(input_column):
        return input_column.cast(T.FloatType())
