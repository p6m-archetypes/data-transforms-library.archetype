import os

from pyspark.sql import SparkSession, Window
from .base import BaseEngine
from {{ project_prefix }}.ybor.utils.data_loader import DataLoader
from {{ project_prefix }}.ybor.utils.data_quality import DataQualityChecker
from {{ project_prefix }}.ybor.utils.data_transformer import DataTransformer
from {{ project_prefix }}.ybor.utils.config_util import ConfigurationsUtil
from pyspark.sql import Catalog
from pyspark.sql import functions as F
import logging

logger = logging.getLogger(__name__)


class SparkEngine(BaseEngine):
    def __init__(self, config):
        super().__init__(config)
        self.spark = self._create_spark_session(config["spark_config"])

    def _create_spark_session(self, spark_config):
        builder = SparkSession.builder.appName(spark_config["appName"])

        if "master" in spark_config:
            builder = builder.master(spark_config["master"])

        for key, value in spark_config["config"].items():
            builder = builder.config(key, value)

        if "input_source" in spark_config and spark_config["input_source"] == "s3":
            # Get AWS resources from environment variable
            (
                aws_access_key_id,
                aws_secret_access_key,
                aws_region,
                session_token,
            ) = ConfigurationsUtil.load_aws_creds(profile_name=spark_config.get("profile_name", None))
            if aws_access_key_id:
                builder = builder.config(
                    "spark.hadoop.fs.s3a.access.key", aws_access_key_id
                )

            # Get aws_secret_access_key from environment variable
            if aws_secret_access_key:
                builder = builder.config(
                    "spark.hadoop.fs.s3a.secret.key", aws_secret_access_key
                )

            if aws_region:
                builder = builder.config("spark.hadoop.fs.s3a.region", aws_region)

            if session_token:
                builder = builder.config(
                    "spark.hadoop.fs.s3a.session.token", session_token
                )

        return builder.getOrCreate()

    def load_data(self):
        data_loader = DataLoader(self.spark, self.config["input_datasets"])
        return data_loader.load_data()

    def apply_transformations(self, df):
        transformer = DataTransformer(df, self.config["transformations"])
        return transformer.apply_transformations()

    def save_output(self, df):
        """
        Save the output DataFrame to the specified output location. The output location can be a table or a file.
        For a table following considerations are done
        Based on the output_dataset configuration, the table is created if it does not exist with partitions
        If primary_key and sort_by are specified, the table is de-duplicated based on the primary key and sorted by columns.
        If there are duplicate records with same primary key, the record with the latest value in the sort_by column is retained.
        :param df:
        """
        output = self.config["output_dataset"]
        partition_by = output.get("partition_by", [])
        primary_key = output.get("primary_key", None)
        sorted_by = output.get("sort_by", None)
        mode = output.get("options", {}).get("mode", "overwrite")
        output_options = output.get("options", {})
        if output["type"] == "table":
            if "catalog" in output and "database" in output:
                table_name = f"{output['database']}.{output['table']}"
                table_exists = Catalog(self.spark).tableExists(table_name)
                if primary_key and sorted_by:
                    window = Window.partitionBy(*primary_key).orderBy(*[F.desc(col) for col in sorted_by])
                    df = df.withColumn("row_num", F.row_number().over(window)).filter(F.col("row_num") == 1).drop(
                        "row_num")
                writer = df.writeTo(table_name).options(**output["options"])
                if partition_by:
                    writer.partitionedBy(*partition_by)

                if not table_exists:
                    logger.info(
                        f"Creating table {output['table']} in database {output['database']}."
                    )
                    writer.createOrReplace()
                else:
                    logger.info(
                        f"Table {output['table']} already exists in database {output['database']}."
                    )
                    if mode == "overwrite":
                        logger.info(
                            f"Overwriting table {output['table']} in database {output['database']}."
                        )
                        if partition_by:
                            writer.overwritePartitions()
                        else:
                            writer.replace()
                    elif mode == "append":
                        logger.info(
                            f"Appending to table {output['table']} in database {output['database']}."
                        )
                        if primary_key:
                            logger.info(
                                f"Table {output['table']} already exists in database {output['database']}. Updating records."
                            )
                            df.createOrReplaceTempView("source")
                            merge_condition = " AND ".join([f"target.{pk} = source.{pk}" for pk in primary_key])
                            self.spark.sql(
                                f"""
                                MERGE INTO {table_name} as target
                                USING source
                                ON ({merge_condition}) 
                                WHEN MATCHED THEN
                                    UPDATE SET *
                                WHEN NOT MATCHED THEN
                                    INSERT * """
                            )
                        else:
                            logger.info(f"Table {output['table']} already exists in database {output['database']}. Appending records.")
                            writer.append()
            else:
                raise ValueError(
                    "Catalog and Database must be specified for table output."
                )
        elif output["type"] == "file":
            df.write.mode(mode).options(**output_options).partitionBy(
                *partition_by
            ).format(output.get("format", "parquet")).save(output["path"])

    def perform_data_quality_checks(self, df):
        if "data_quality_checks" in self.config:
            dq_checks = DataQualityChecker(df, self.config["data_quality_checks"])
            dq_checks.perform_checks()
        else:
            logger.info("No data quality checks specified in the configuration.")

    def shutdown(self):
        self.spark.stop()
        logger.info("Spark session stopped.")
