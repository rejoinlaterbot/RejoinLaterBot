"""Console entry point."""

import asyncio

from rejoinlater.app import run


def main() -> None:
    """Run the async application."""

    asyncio.run(run())


if __name__ == "__main__":
    main()
