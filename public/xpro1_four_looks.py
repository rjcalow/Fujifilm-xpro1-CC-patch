"""Build the experimental four-look 3.93 updater for the original X-Pro1."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "re" / "tools"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path, help="official 3.82 FPUPDATE.DAT")
    parser.add_argument("output", type=Path, help="new file in an existing directory")
    args = parser.parse_args()
    if args.output.exists():
        parser.exit(1, "Output already exists. Choose a new file.\n")
    try:
        import four_looks
    except ModuleNotFoundError as exc:
        if exc.name != "keystone":
            raise
        parser.exit(
            1,
            "Install the ARM assembler with: python -m pip install keystone-engine==0.9.2\n",
        )
    try:
        data = four_looks.build(args.stock.read_bytes())
        with args.output.open("xb") as dst:
            try:
                dst.write(data)
                dst.flush()
            except BaseException:
                dst.close()
                args.output.unlink()
                raise
    except (OSError, ValueError, AssertionError) as exc:
        parser.exit(1, f"Build failed: {exc}\n")
    print(
        f"X-Pro1 3.93: {args.output} ({len(data)} bytes)\nSHA-256 {four_looks.RESULT_SHA256}"
    )


if __name__ == "__main__":
    main()
