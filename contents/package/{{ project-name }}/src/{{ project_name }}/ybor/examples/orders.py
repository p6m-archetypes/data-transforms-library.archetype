import json
from {{ project_prefix }}.ybor.driver.driver import Driver


def main():
    with open(
            "orders.json",
            "r",
    ) as file:
        config = json.load(file)

    driver = Driver(config)
    driver.run()


if __name__ == "__main__":
    main()
