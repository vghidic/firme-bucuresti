import argparse
import hashlib
import logging
import re
from collections import defaultdict
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_DIR / "dataset" / "data.gov.ro"
YEAR_PATTERN = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def years_in_name(path: Path) -> set[int]:
    return {int(value) for value in YEAR_PATTERN.findall(path.name)}


def keeper_score(path: Path, filename_years: set[int]) -> tuple[int, str]:
    folder_years = {
        int(value)
        for part in path.parent.parts
        for value in YEAR_PATTERN.findall(part)
    }
    matching_year = bool(filename_years & folder_years)
    return (0 if matching_year else 1, str(path).lower())


def find_duplicate_groups(root: Path) -> list[list[Path]]:
    by_name: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if path.is_file():
            by_name[path.name.lower()].append(path)

    duplicates = []
    for paths in by_name.values():
        by_content: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            by_content[file_hash(path)].append(path)
        duplicates.extend(group for group in by_content.values() if len(group) > 1)
    return duplicates


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Elimina fisierele duplicate dintr-un director data.gov.ro."
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Afiseaza fisierele care ar fi sterse fara sa le stearga.",
    )
    args = parser.parse_args()

    if not args.root.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {args.root}")

    removed = 0
    for duplicate_group in find_duplicate_groups(args.root):
        filename_years = years_in_name(duplicate_group[0])
        ordered = sorted(
            duplicate_group,
            key=lambda path: keeper_score(path, filename_years),
        )
        keeper, *redundant = ordered
        logging.info("Keeping %s", keeper)
        for path in redundant:
            if args.dry_run:
                logging.info("Would remove %s", path)
            else:
                path.unlink()
                logging.info("Removed %s", path)
            removed += 1

    logging.info(
        "%s %d duplicate file(s)",
        "Would remove" if args.dry_run else "Removed",
        removed,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
