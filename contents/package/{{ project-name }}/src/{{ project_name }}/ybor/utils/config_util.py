import json
import logging
import os
import random
import string
from pyspark.sql import Catalog
from pyspark.sql import SparkSession
import boto3

from {{ project_prefix }}.ybor.utils.glue_catalog import GlueCatalog


class ConfigurationsUtil:
    @staticmethod
    def load_spark_config(config_map, input_source="local", env="dev"):
        """
        Loading the spark configuration from the manifest file
        :param config_map: contains configuration settings
        :param aws_access_id: aws s3 access id
        :param aws_secret_key: aws s3 secret key
        :return:
        """
        logging.info(f">>> Loading Spark Config...")
        spark_builder = SparkSession.builder.appName(
            config_map["spark_config"]["appName"]
        )
        # Iterate through the spark_config and set configurations dynamically
        for key, value in config_map["spark_config"].items():
            spark_builder.config(key, value)

        if input_source == "s3":
            # Get AWS resources from environment variable
            (
                aws_access_key_id,
                aws_secret_access_key,
                aws_region,
                session_token,
            ) = ConfigurationsUtil.load_aws_creds()
            if aws_access_key_id:
                spark_builder = spark_builder.config(
                    "spark.hadoop.fs.s3a.access.key", aws_access_key_id
                )

            # Get aws_secret_access_key from environment variable
            if aws_secret_access_key:
                spark_builder = spark_builder.config(
                    "spark.hadoop.fs.s3a.secret.key", aws_secret_access_key
                )

            if aws_region:
                spark_builder = spark_builder.config(
                    "spark.hadoop.fs.s3a.region", aws_region
                )

            if session_token:
                spark_builder = spark_builder.config(
                    "spark.hadoop.fs.s3a.session.token", session_token
                )

        spark_session = spark_builder.getOrCreate()
        return spark_session

    @staticmethod
    def validate_config(config_map):
        """
        Validating the configuration settings
        :param config_map: contains configuration settings
        """
        logging.info("Validating config settings")

        # Validate appName presence in spark_config
        if "appName" not in config_map["infra_mapping"]["spark_config"]:
            config_map["infra_mapping"]["spark_config"]["appName"] = "app-" + "".join(
                random.choices(string.ascii_letters + string.digits, k=7)
            )

        # Define required fields and their expected types
        required_fields = {
            "input_map": dict,
            "output_map": dict,
            "column_mapping": dict,
            "infra_mapping": dict,
        }
        # Validate required fields and data types
        for field, expected_type in required_fields.items():
            if field not in config_map:
                raise ValueError(f"Missing required field: {field}")
            if not isinstance(config_map[field], expected_type):
                raise ValueError(
                    f"Invalid type for field '{field}'. Expected type: {expected_type.__name__}"
                )

        # Validate static block has key-value pairs filled
        static_block = config_map.get("column_mapping", {}).get("static", {})
        if static_block or not all(static_block.values()):
            raise ValueError("Static block must have all key-value pairs filled")

        # Validate input data format (case-insensitive)
        input_format = config_map.get("input_map", {}).get("source_format", "").lower()
        if input_format not in ["csv", "json", "avro", "orc", "parquet"]:
            raise ValueError(
                "Input data format must be one of: CSV, JSON, AVRO, ORC, PARQUET"
            )

        # Validate output data format
        target_format = config_map.get("output_map").get("target_format", "").lower()
        if target_format not in ["csv", "json", "avro", "orc", "parquet"]:
            raise Exception(
                f"Output data format must be one of: CSV, JSON, AVRO, ORC, PARQUET"
            )

        # Validate catalog (case-insensitive)
        catalog = config_map["output_map"].get("catalog_type", "").lower()
        if catalog not in ["hive", "iceberg"]:
            raise ValueError("Catalog must be either Hive or Iceberg")

        # Check for duplicate keys
        keys_set = set()
        for key in config_map:
            if key in keys_set:
                raise ValueError(f"Duplicate key found: {key}")
            keys_set.add(key)

        logging.info("Validation successfully completed")

    @staticmethod
    def get_table_schema(df):
        """
        Generating the output schema for Hive registration
        :param df:
        :return:
        """
        logging.info(">>> Generating Schema for External table creation.. ")
        schema_list = []
        for column, data_type in df.dtypes:
            comment = "generated from code"
            column_val = {"Name": column, "Type": data_type, "Comment": comment}
            # add the new column to the list:
            schema_list.append(column_val)

        return schema_list

    @staticmethod
    def get_hive_table_params(s3_location, table_name, df, dest_format):
        """
        Constructring the table input parameters for Hive registration
        :param s3_location: location of the s3 files
        :param table_name: table name being worked on
        :param df: input dataframe to generate the schema
        :param dest_format: target format to write the output files
        """
        s3_location = s3_location.replace("s3a", "s3")
        column_mapping = ConfigurationsUtil.get_table_schema(df)
        input_format_map = {
            "parquet": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
        }

        serde_map = {
            "parquet": {
                "Name": "ParquetHiveSerDe",
                "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
            }
        }

        return {
            "Name": table_name,
            "Description": "External Table created via cli",
            "StorageDescriptor": {
                "Columns": column_mapping,
                "Location": s3_location,
                "InputFormat": input_format_map[dest_format],
                "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                "Compressed": False,
                "SerdeInfo": serde_map[dest_format],
            },
            "TableType": "EXTERNAL_TABLE",
        }

    @staticmethod
    def save_register_catalog(spark, df, output_map, column_mapping):
        """
        Save and Register s3 data to Metastore
        :param spark:  spark session
        :param df: input dataframe to work with
        :param table_type: can be registered to hive or iceberg catalog
        :param output: output location to write data
        :param column_mapping: column_mapping key supplied from the manifest file
        """
        logging.info(f">>> Data save and Registration is progress... ")
        source_name = column_mapping["static"]["source_name"]
        venture_name = column_mapping["static"]["venture_name"]
        catalog_type = output_map["catalog_type"].lower()
        dest_format = output_map["target_format"]

        (
            aws_access_key_id,
            aws_secret_access_key,
            aws_region,
            session_token,
        ) = ConfigurationsUtil.load_aws_creds()

        # Hive table registration
        if catalog_type == "hive":
            s3_location = (
                output_map["output_location"] + "/" + source_name + "/" + venture_name
            )
            table_name = output_map["output_table"]
            output_db = output_map["output_database"]

            logging.info(f">>> Saving to s3 location for Hive Catalog registration..")
            # Write DataFrame to Hive table
            df.write.mode("overwrite").format(dest_format).save(s3_location)
            logging.info(
                f">>> Data saved successfully to {s3_location} using {dest_format} format"
            )

            # Registering the data with hive metastore
            logging.info(
                f">>> Creating External Tables for Hive Metastore on s3 location: {s3_location}..."
            )
            # Get glue client
            glue_client = GlueCatalog.get_client(
                aws_access_key_id, aws_secret_access_key, aws_region
            )

            try:
                GlueCatalog.create_glue_database(glue_client, database_name=output_db)
            except Exception as e:
                logging.info(f"Glue Database creation exception: {e}")

            try:
                table_params_input = ConfigurationsUtil.get_hive_table_params(
                    s3_location, table_name, df, dest_format
                )
                GlueCatalog.create_glue_table(
                    glue_client,
                    database_name=output_db,
                    table_input=table_params_input,
                )
                logging.info(
                    f">>> Created External Table successfully for Glue Catalog on db: {output_db}, "
                    f"table: {table_name}"
                )
            except glue_client.exceptions.AlreadyExistsException as e:
                logging.info(f">>> Found Glue Table creation exception: {e}")

                # Delete table if it already exists
                logging.info(f"Deleting existing table: {table_name}")
                GlueCatalog.delete_glue_table(
                    glue_client, database_name=output_db, table_name=table_name
                )

                # Re-creating table for supplied inputs
                logging.info("[Re]Creating external table for Glue Catalog.. ")
                table_params_input = ConfigurationsUtil.get_hive_table_params(
                    s3_location, table_name, df, dest_format
                )
                GlueCatalog.create_glue_table(
                    glue_client,
                    database_name=output_db,
                    table_input=table_params_input,
                )
                logging.info(
                    f">>> Completed re-creating External Table successfully for Glue Catalog on db: {output_db}, "
                    f"table: {table_name}"
                )

        # Iceberg table registration
        elif catalog_type == "iceberg":
            iceberg_table = output_map["output_table"]
            logging.info(f">>> Saving to Iceberg Catalog table: {iceberg_table}...")
            # Check of current table already exists append if it already exists or create a new one if it doesn't exist
            if Catalog(spark).tableExists(iceberg_table):
                logging.info(
                    f">>> Table {iceberg_table} already exists, appending the data"
                )
                # Write DataFrame to Iceberg table
                df.writeTo(iceberg_table).append()
            else:
                df.writeTo(iceberg_table).createOrReplace()

            logging.info(
                f">>> Data saved successfully to {iceberg_table} using {dest_format} format"
            )

    @staticmethod
    def load_input_df(spark, config_map):
        input_format = config_map["input_map"]["source_format"]
        options = config_map["input_map"].get("source_options", {})
        option_settings = options[input_format]
        if option_settings:
            df = (
                spark.read.format(config_map["input_map"]["source_format"])
                .options(**option_settings)
                .load(config_map["input_map"]["input_location"])
            )
        else:
            df = spark.read.format(config_map["input_map"]["source_format"]).load(
                config_map["input_map"]["input_location"]
            )

        return df

    @staticmethod
    def load_aws_creds(env="prod", profile_name=None):
        """
        Reading AWS credentials from environment variables of current execution environment
        :return: aws_access_key_id, aws_secret_access_key, aws_region
        """
        if env == "prod":
            try:
                boto3_session = boto3.Session(profile_name=profile_name) if profile_name else boto3.Session()
                credentials = boto3_session.get_credentials()
                access_key = credentials.access_key
                os.environ["AWS_ACCESS_KEY_ID"] = access_key
                secret_key = credentials.secret_key
                os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
                session_token = credentials.token
                os.environ["AWS_SESSION_TOKEN"] = session_token
                region = boto3_session.region_name
                os.environ["AWS_REGION"] = region
            except Exception as e:
                logging.error(f"Error reading AWS credentials: {e}")
        # Read AWS credentials from environment variables
        aws_access_key_id = os.environ.get("aws_access_key_id") or os.environ.get(
            "AWS_ACCESS_KEY_ID"
        )
        if aws_access_key_id:
            logging.info("aws_access_key_id found in the environment variables")
        else:
            raise ValueError(
                "Neither aws_access_key_id nor AWS_ACCESS_KEY_ID environment variables found. please check"
            )

        aws_secret_access_key = os.environ.get(
            "aws_secret_access_key"
        ) or os.environ.get("AWS_SECRET_ACCESS_KEY")
        if aws_secret_access_key:
            logging.info("aws_secret_access_key found in the environment variables")
        else:
            raise ValueError(
                "Neither aws_secret_access_key nor AWS_SECRET_ACCESS_KEY environment variables found. please check"
            )

        aws_region = os.environ.get("aws_region") or os.environ.get("AWS_REGION")
        if aws_region:
            logging.info("aws_region found in the environment variables")
        else:
            aws_region = "us-west-2"
            logging.info(
                f"Missing aws_region value from env, setting the default value as: {aws_region}"
            )

        session_token = os.environ.get("aws_session_token") or os.environ.get(
            "AWS_SESSION_TOKEN"
        )
        if session_token:
            logging.info("aws_session_token found in the environment variables")
        else:
            logging.info(f"Missing aws_session_token value from env")

        return aws_access_key_id, aws_secret_access_key, aws_region, session_token

    @staticmethod
    def read_config(file_path):
        try:
            spec_file_name = file_path
            with open(spec_file_name, "r") as jsonfile:
                config_data = json.load(jsonfile)
                # ConfigurationsUtil.validate_config(config_data)
            print("Manifest config data read successful")
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise Exception(
                "An unexpected error occurred while reading the manifest file:", e
            )
        return config_data

    @staticmethod
    def write_to_postgres(df, table_name, jdbc_url, jdbc_properties, mode):
        """
        Write DataFrame to PostgreSQL table.
        Args:
            df (DataFrame): Input DataFrame to write.
            table_name (str): Name of the table to write to.
            jdbc_url (str): JDBC URL for connecting to the database.
            jdbc_properties (dict): Dictionary containing JDBC properties like user and password.
            :param mode: write mode
        """
        # dropping the source meta column
        df_flat = df.drop("source_meta")
        logging.info(
            "<<<<<<<__________________Output Schema for Postgres table_________________________>>>>>"
        )
        df_flat.printSchema()
        df_flat.write.jdbc(
            url=jdbc_url, table=table_name, mode=mode, properties=jdbc_properties
        )
