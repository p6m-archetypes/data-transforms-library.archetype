from {{ project_prefix }}.ybor.engine.spark_engine import SparkEngine



# Import other engines as needed


class Driver:
    def __init__(self, config):
        self.config = config
        self.engine = self._load_engine(config.get("processing_engine", "spark"))

    def _load_engine(self, engine_name):
        if engine_name == "spark":
            return SparkEngine(self.config)
        # Add other engines here
        else:
            raise ValueError(f"Unsupported processing engine: {engine_name}")

    def run(self):
        # Load data
        dfs = self.engine.load_data()

        transformed_df = self.engine.apply_transformations(dfs)

        # Data quality checks
        self.engine.perform_data_quality_checks(transformed_df)
        # Save output
        self.engine.save_output(transformed_df)
        self.engine.shutdown()
