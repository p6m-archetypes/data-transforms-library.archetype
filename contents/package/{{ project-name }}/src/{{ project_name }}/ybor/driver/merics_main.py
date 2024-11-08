import json
from driver import Driver


def main():
    with open(
            "../resources/metrics.json",
            "r",
    ) as file:
        config = json.load(file)

    driver = Driver(config)
    driver.run()


if __name__ == "__main__":
    main()
