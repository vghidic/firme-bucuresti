import argparse
import csv
import logging
from pathlib import Path
from urllib.parse import urlparse


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CUI_FILE = PROJECT_DIR / "cui.csv"


def dataset_id_from_url(dataset_url: str) -> str:
    parts = [part for part in urlparse(dataset_url).path.split("/") if part]
    if len(parts) != 2 or parts[0] != "dataset" or not parts[1]:
        raise ValueError(
            "Dataset URL must have the form https://data.gov.ro/dataset/<id>"
        )
    return parts[1]


def normalize_cui(value: str) -> str:
    return value.lstrip("\ufeff").strip()


def read_cuis(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "cui" not in {
            field.strip().lower() for field in reader.fieldnames
        }:
            raise ValueError(f"{path} must contain a 'cui' column")

        cui_column = next(
            field for field in reader.fieldnames if field.strip().lower() == "cui"
        )
        cuis = {
            normalize_cui(row[cui_column])
            for row in reader
            if normalize_cui(row[cui_column])
        }

    if not cuis:
        raise ValueError(f"No CUI values found in {path}")
    return cuis


def filter_file(input_path: Path, output_path: Path, cuis: set[str]) -> int:
    with input_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        try:
            header = next(reader)
        except StopIteration as error:
            raise ValueError(f"{input_path} is empty") from error

        cui_indexes = [
            index
            for index, value in enumerate(header)
            if normalize_cui(value).lower() == "cui"
        ]
        if len(cui_indexes) != 1:
            raise ValueError(
                f"{input_path} must contain exactly one 'cui' column"
            )
        cui_index = cui_indexes[0]

        with output_path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(header)
            retained = 0
            for row in reader:
                if len(row) > cui_index and normalize_cui(row[cui_index]) in cuis:
                    writer.writerow(row)
                    retained += 1

    return retained


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filtreaza un dataset data.gov.ro dupa CUI."
    )
    parser.add_argument("--dataset-url", required=True)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--cui-file", type=Path, default=DEFAULT_CUI_FILE)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    dataset_id = dataset_id_from_url(args.dataset_url)
    dataset_root = PROJECT_DIR / "dataset" / "data.gov.ro"
    if args.input_dir is None:
        args.input_dir = dataset_root / f"{dataset_id}_combined"
    if args.output_dir is None:
        args.output_dir = dataset_root / f"{dataset_id}_filtered_cui"
    input_files = sorted(args.input_dir.glob("*.csv"))
    if not input_files:
        raise FileNotFoundError(f"No CSV files found in {args.input_dir}")

    cuis = read_cuis(args.cui_file)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.info("Loaded %d CUI values from %s", len(cuis), args.cui_file)

    for input_path in input_files:
        output_path = args.output_dir / input_path.name
        retained = filter_file(input_path, output_path, cuis)
        logging.info(
            "Filtered %s -> %s (%d rows retained)",
            input_path.name,
            output_path.name,
            retained,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
