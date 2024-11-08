from abc import ABC, abstractmethod


class BaseEngine(ABC):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def load_data(self):
        pass

    @abstractmethod
    def apply_transformations(self, df):
        pass

    @abstractmethod
    def save_output(self, df):
        pass

    @abstractmethod
    def perform_data_quality_checks(self, df):
        pass
