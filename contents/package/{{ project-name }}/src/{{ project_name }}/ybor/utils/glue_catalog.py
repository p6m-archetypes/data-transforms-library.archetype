import boto3
import logging


class GlueCatalog:
    @staticmethod
    def get_client(aws_access_key_id, aws_secret_access_key, region="us-east-1"):
        """
        Creates a Glue client

        Args:
            aws_access_key_id (str): AWS access key ID.
            aws_secret_access_key (str): AWS secret access key.
            region (str): AWS region. Default is 'us-west-2'.
        """
        logging.info(f">>> Initializing Glue Client...")
        boto_glue_client = boto3.client(
            "glue",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region,
        )
        return boto_glue_client

    @staticmethod
    def create_glue_database(glueclient, database_name):
        """
        Creates a Glue database.

        Args:
            glue_client : Boto3 client to interact with glue
            database_name (str): Name of the Glue database.
            :param glueclient: Glue client
        """
        logging.info(f">>> Creating Glue database: {database_name}")
        response = glueclient.create_database(
            DatabaseInput={
                "Name": database_name,
                "Description": f"Glue Database - {database_name}",
            }
        )

        logging.info(f"Database '{database_name}' created successfully.")
        return response

    @staticmethod
    def create_glue_table(glue_client, database_name, table_input):
        """
        Creates a Glue table.

        Args:
            glue_client : Boto3 client to interact with glue
            table_name (str): Name of the Glue table.
            database_name (str): Name of the Glue database.
        """

        response = glue_client.create_table(
            DatabaseName=database_name, TableInput=table_input
        )

        return response

    @staticmethod
    def delete_glue_table(glue_client, database_name, table_name):
        """
        Deletes a Glue table.
        :param glue_client: Boto3 client to interact with glue
        :param database_name: Name of the Glue database
        :param table_name: Name of the Glue table
        :return:
        """

        response = glue_client.delete_table(DatabaseName=database_name, Name=table_name)

        return response
