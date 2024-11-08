import configparser
import logging
import os
import random
import traceback

import requests
import sys
from pyspark.sql import functions as F
from pyspark.sql.types import ArrayType

from {{ project_prefix }}.ybor.helpers import Casts, Conversions


class TransformationsUtil:
    # custom method for testing inference data
    @staticmethod
    def random_interests_selection():
        # List of topics
        selected_int = []
        interests = ["Sports", "Music", "Finance", "Entertainment", "Technology"]

        for _ in range(3):
            selected_int.append(random.choice(interests))

        return F.lit(selected_int)

    @staticmethod
    def sample():
        response = requests.get(
            "https://data.wa.gov/api/views/f6w7-q2d2/rows.json?accessType=DOWNLOAD"
        )
        data = response.json()
        print("Metadata:", data["meta"])

    @staticmethod
    def clean_df(dataframe_input, columns_config):
        """
        Clean a PySpark DataFrame based on a column configuration.

        :param dataframe_input: The input DataFrame to be cleaned.
        :param columns_config: A dictionary defining the cleaning rules for each column.
        :return: The cleaned DataFrame.

        The column config dictionary supports different rules following are some of the major functionalities
        - output (mandatory) : This represents the target column name for a respective source column name
        - cast (optional) : This is an optional config, if included the column type will be casted to mentioned types
        - conversion (optional) : This is an optional config, this is used to define standard conversion functions for data cleansing.
                                  Example for this is converting source data format into target date format from "yyyy/MM/dd" to "yyyy-MM-dd"
        - function (Optional): This is an optional config, this is used when user wants to supply a custom function

        Example config:
            col_config = {
                "product_id": {"output": "EncryptedProductID", "function": md5_encrypt},
                "store_id": {"output": "StoreId"},
                "date": {"output": "TransactionDate", "conversion": {"method": "date_from_string", "args": {"target_format": "yyyy/MM/dd"}}},
                "sales": {"output": "SalesAmount", "cast": "float"},
                "stock": {"output": "NoOfItems", "cast": "integer"}
            }
        """
        logging.info(f"Running transformation module...")
        current_df = dataframe_input
        # dict from column to output_column_name
        columns_to_select = {}
        missing_columns = {}
        source_meta_json = None

        add_meta = TransformationsUtil.str_to_bool(
            columns_config.get("custom").get("add_meta", "False")
        )
        project_all = TransformationsUtil.str_to_bool(
            columns_config.get("custom").get("project_all", "False")
        )
        generate_etl_cols = TransformationsUtil.str_to_bool(
            columns_config.get("custom").get("generate_etl_cols", "True")
        )
        column_mapping = columns_config["standard"]

        try:
            if project_all:
                columns_to_select = {col: F.col(col) for col in dataframe_input.columns}
            if add_meta:
                # adding meta_data object other than the body column
                columns_to_exclude = ["body"]
                columns_to_include = [
                    col
                    for col in dataframe_input.columns
                    if col not in columns_to_exclude
                ]
                source_meta_json = F.struct(
                    [F.col(col_name) for col_name in columns_to_include]
                ).alias("source_meta")
                current_df = current_df.withColumn("source_meta", source_meta_json)

            if generate_etl_cols:
                current_df = current_df.withColumn(
                    "etl_processed_date", F.current_timestamp()
                )
                columns_to_select["etl_processed_date"] = F.col("etl_processed_date")

            for input_column_name, column_config in column_mapping.items():
                if "index" in column_config:
                    if isinstance(current_df.schema[input_column_name].dataType, ArrayType):
                        new_column = F.col(input_column_name).getItem(column_config["index"]-1)
                    else:
                        raise Exception(
                            f"Column {input_column_name} is not an ArrayType column"
                        )
                else:
                    new_column = F.col(input_column_name)

                if input_column_name not in current_df.columns:
                    if "default" in column_config:
                        missing_columns[column_config["output"]] = column_config["cast"]

                output_column_name = input_column_name

                # Rename the column if 'output' is specified in the configuration
                if "output" in column_config:
                    output_column_name = column_config["output"]

                if output_column_name in columns_to_select:
                    raise Exception(
                        f"Duplicate output column name {output_column_name} discovered for input {input_column_name}"
                    )

                # Cast the column to the specified data type, if 'cast' is specified
                if "cast" in column_config:
                    output_type = column_config["cast"]
                    new_column = getattr(Casts, f"to_{output_type}")(new_column)

                # Apply a custom conversion function, if 'conversion' is specified
                if "conversion" in column_config:
                    if "method" not in column_config["conversion"]:
                        raise Exception(
                            "method key is missing in the 'conversion' dictionary"
                        )
                    method_name = column_config["conversion"]["method"]
                    # Convert 'args' to keyword arguments
                    args = column_config["conversion"].get("args", {})
                    new_column = getattr(Conversions, method_name)(new_column, **args)

                # Apply a custom function, if 'function' is specified
                if "function" in column_config:
                    # new_column = column_config["function"](new_column)
                    function = column_config["function"]

                    # explicitly define the functions used in the manifest file
                    if function == "random_interests_selection":
                        current_df = current_df.withColumn(
                            input_column_name,
                            TransformationsUtil.random_interests_selection(),
                        )
                        # current_df = current_df.withColumn(input_column_name, function())

                columns_to_select[output_column_name] = new_column
                # Remove the column if it's already selected with renamed values
                if input_column_name in columns_to_select:
                    columns_to_select.pop(input_column_name)

            # Select the cleaned columns and alias them with the specified output column names
            initial_set_of_columns_to_keep = [
                column.alias(output_column_name)
                for output_column_name, column in columns_to_select.items()
            ]
            if source_meta_json:
                initial_set_of_columns_to_keep += [source_meta_json]

            if len(missing_columns) > 0:
                for cols in missing_columns:
                    initial_set_of_columns_to_keep = [
                        column.alias(output_column_name)
                        for output_column_name, column in columns_to_select.items()
                        if output_column_name != cols
                    ]
                    if source_meta_json:
                        initial_set_of_columns_to_keep += [source_meta_json]
                    current_df = current_df.select(*initial_set_of_columns_to_keep)
                    current_df = current_df.withColumn(
                        cols, F.lit(None).cast(missing_columns[cols])
                    )
            else:
                current_df = current_df.select(*initial_set_of_columns_to_keep)

            return current_df
        except Exception as e:
            logging.info(f"Found exception as: \n{e}\n{traceback.format_exc()}")

    @staticmethod
    def md5_encrypt(column):
        return F.md5(column)

    @staticmethod
    def clean_up(output_dir):
        """
        The default spark writer creates temporary files with .crc extension.
        This method is used as a clean up operation to delete those files for clean consumption.
        Delete .csv.crc files from the output directory
        :param output_dir:
        :return: None
        """
        for root, _, files in os.walk(output_dir):
            for file in files:
                if file.endswith(".crc"):
                    file_path = os.path.join(root, file)
                    os.remove(file_path)

    @staticmethod
    def read_aws_credentials(file_path="config.ini"):
        """
        Reads AWS credentials from a properties file.

        Args:
            file_path (str): Path to the properties file. Default is 'config.ini'.

        Returns:
            Tuple[str, str, str]: AWS access key ID, AWS secret access key, AWS region.
        """
        logging.info(
            "__________________________________________________________________"
        )
        logging.info(f">>> Reading AWS credentials...")
        # Check if the provided file_path is an absolute path
        if not os.path.isabs(file_path):
            # If it's a relative path, join it with the current working directory
            file_path = os.path.join(os.getcwd(), file_path)

        config = configparser.ConfigParser()
        config.read(file_path)

        access_key_id = config["AWS"]["ACCESS_KEY_ID"]
        secret_access_key = config["AWS"]["SECRET_ACCESS_KEY"]
        region = config["AWS"].get(
            "REGION", "us-east-1"
        )  # Default region if not specified

        return access_key_id, secret_access_key, region

    @staticmethod
    def generate_agg_expers(metrics):
        agg_exprs = []
        for metric in metrics:
            column = metric["column"]
            function = metric["function"]
            if function == "sum":
                agg_exprs.append(F.sum(F.col(column)).alias(f"{column}_sum"))
            elif function == "count":
                agg_exprs.append(F.count(F.col(column)).alias(f"{column}_count"))
            elif function == "count_non_null":
                agg_exprs.append(
                    F.count(F.when(F.col(column).isNotNull(), F.col(column))).alias(
                        f"{column}_count_non_null"
                    )
                )
            elif function == "percent_non_null":
                agg_exprs.append(
                    (
                        F.count(F.when(F.col(column).isNotNull(), F.col(column)))
                        / F.count(F.lit(1))
                        * 100
                    ).alias(f"{column}_percent_non_null")
                )
            elif function == "percent_null":
                agg_exprs.append(
                    (
                        F.count(F.when(F.col(column).isNull(), F.col(column)))
                        / F.count(F.lit(1))
                        * 100
                    ).alias(f"{column}_percent_null")
                )
            elif function == "distinct_count":
                agg_exprs.append(
                    F.countDistinct(F.col(column)).alias(f"{column}_distinct_count")
                )
        return agg_exprs

    @staticmethod
    def str_to_bool(str_val):
        # Convert the string to lowercase for case-insensitive comparison
        val = str_val.lower()

        # Check if the string is 'true' or 'false'
        if val == "true":
            return True
        elif val == "false":
            return False
        else:
            # If the string is neither 'true' nor 'false', raise a ValueError
            raise ValueError(f"Invalid string value: {str_val}")
