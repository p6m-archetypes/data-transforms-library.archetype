class DataLoader:
    def __init__(self, spark, datasets):
        self.spark = spark
        self.datasets = datasets

    def load_data(self):
        dfs = {}
        for dataset in self.datasets:
            if dataset["type"] == "file":
                dfs[dataset["name"]] = (
                    self.spark.read.format(dataset["format"])
                    .options(**dataset.get("options", {}))
                    .load(dataset["path"])
                )
            elif dataset["type"] == "table":
                dfs[dataset["name"]] = self.spark.table(
                    f"{dataset['table']}"
                )
        return dfs
