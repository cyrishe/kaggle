"""Construct a shared-factor solution for scored_0810 from its original inputs."""

import argparse
import csv
import json
from pathlib import Path

from first_solver import validate
from prune_program import prune


ROOT = Path(__file__).resolve().parent.parent
PUZZLE_ID = "scored_0810"

# Each triple references values that must already be in registers.
# The first two branches share 2650 and 151050.
RECIPES = (
    ("/", 4, 4),          # 1
    ("*", 13, 4),         # 52
    ("+", 52, 1),         # 53
    ("+", 1, 1),          # 2
    ("*", 10, 10),        # 100
    ("/", 100, 2),        # 50
    ("*", 53, 50),        # 2650
    ("*", 2650, 53),      # 140450
    ("+", 53, 4),         # 57
    ("*", 2650, 57),      # 151050
    ("+", 13, 4),         # 17
    ("-", 151050, 17),    # 151033
    ("+", 151033, 1),     # 151034
    ("+", 151033, 7),     # 151040
    ("+", 151050, 2),     # 151052
    ("+", 7, 7),          # 14
    ("*", 14, 10),        # 140
    ("+", 151052, 140),   # 151192
    ("+", 53, 13),        # 66
    ("*", 66, 4),         # 264
    ("-", 151040, 264),   # 150776
    ("+", 264, 2),        # 266
    ("*", 2650, 266),    # 704900
    ("*", 140450, 17),   # 2387650
    ("*", 151050, 264),  # 39877200
    ("+", 264, 264),      # 528
    ("*", 140450, 528),  # 74157600
    ("*", 17, 17),        # 289
    ("+", 289, 289),      # 578
    ("*", 151050, 578),  # 87306900
    ("*", 289, 10),       # 2890
    ("+", 2890, 264),     # 3154
    ("+", 53, 50),        # 103
    ("*", 3154, 103),    # 324862
)


def compile_recipes(puzzle, recipes):
    starts = json.loads(puzzle["starting_values"])
    limit = int(puzzle["value_limit"])
    registers = {value: index for index, value in enumerate(starts)}
    operations = []
    for op, a, b in recipes:
        if op == "+":
            value = a + b
        elif op == "-":
            value = a - b
        elif op == "*":
            value = a * b
        elif op == "/" and a % b == 0:
            value = a // b
        else:
            raise ValueError(f"Illegal operation: {a} {op} {b}")
        if value in registers:
            continue
        destination = len(starts) + len(operations)
        if not 1 <= value <= limit or destination >= int(puzzle["registers"]):
            raise ValueError(f"Value or register out of bounds: {value}, r{destination}")
        operations.append([op, registers[a], registers[b], destination])
        registers[value] = destination
    validate(puzzle, operations)
    return operations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "experiments" / f"{PUZZLE_ID}_shared_factor_program.json",
    )
    args = parser.parse_args()
    with (ROOT / "data" / "puzzles.csv").open(newline="") as stream:
        puzzle = next(row for row in csv.DictReader(stream) if row["id"] == PUZZLE_ID)
    program = prune(puzzle, compile_recipes(puzzle, RECIPES))
    args.output.write_text(json.dumps(program, separators=(",", ":")) + "\n")
    count, size, coverage = validate(puzzle, json.loads(args.output.read_text()))
    print(f"{PUZZLE_ID}: {count} steps, {coverage} targets, {size} bytes")


if __name__ == "__main__":
    main()
