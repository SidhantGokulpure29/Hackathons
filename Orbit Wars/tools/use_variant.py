import argparse
import shutil
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Copy an agent variant into main.py.")
    parser.add_argument("variant", help="Path to variant, e.g. agents/v21_global_planner.py")
    args = parser.parse_args()

    source = Path(args.variant)
    if not source.exists():
        raise FileNotFoundError(source)
    if source.name == "main.py":
        raise ValueError("Refusing to copy main.py over itself.")

    shutil.copy2(source, "main.py")
    print(f"main.py <- {source}")


if __name__ == "__main__":
    main()
