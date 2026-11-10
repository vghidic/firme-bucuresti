import argparse
import csv
import difflib
import logging
import re
from pathlib import Path
from urllib.parse import urlparse


ENCODINGS = ("utf-8-sig", "cp1250", "cp1252", "latin-1")


def dataset_id_from_url(dataset_url: str) -> str:
    parts = [part for part in urlparse(dataset_url).path.split("/") if part]
    if len(parts) != 2 or parts[0] != "dataset" or not parts[1]:
        raise ValueError(
            "Dataset URL must have the form https://data.gov.ro/dataset/<id>"
        )
    return parts[1]


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding).lstrip("\ufeff")
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Could not decode {path}")


def read_specification(path: Path) -> dict[str, str]:
    text = read_text(path)
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        delimiter = ";"

    mapping: dict[str, str] = {}
    for row in csv.reader(text.splitlines(), delimiter=delimiter):
        if not any(value.strip() for value in row):
            continue
        if len(row) < 2:
            raise ValueError(f"Invalid specification row in {path}: {row!r}")
        label, code = (value.strip() for value in row[:2])
        if not code:
            raise ValueError(f"Empty column code in {path}: {row!r}")
        mapping[code.lower()] = label or code
    return mapping


def normalized_name(path: Path) -> str:
    name = path.stem.lower().replace("_an", "_")
    return re.sub(r"_?20\d{2}", "", name).strip("_")


def find_specification(data_path: Path, specifications: list[Path]) -> Path:
    name_matches = [
        path
        for path in specifications
        if normalized_name(path) == normalized_name(data_path)
    ]
    if len(name_matches) == 1:
        return name_matches[0]

    with data_path.open(encoding="utf-8", newline="") as source:
        codes = [
            code.lstrip("\ufeff").strip().lower()
            for code in next(csv.reader(source))
        ]

    code_matches = [
        path
        for path in specifications
        if list(read_specification(path)) == codes
    ]
    candidates = [
        path for path in specifications if len(read_specification(path)) == len(codes)
    ]
    if not candidates:
        candidates = code_matches
    scores = {
        path: (
            2
            * difflib.SequenceMatcher(
                None,
                normalized_name(data_path),
                normalized_name(path),
            ).ratio()
            + len(set(codes) & set(read_specification(path)))
            / len(codes)
        )
        for path in candidates
    }
    best_score = max(scores.values(), default=0)
    matches = [path for path, score in scores.items() if score == best_score]
    if best_score < 2.4:
        matches = []
    if len(matches) != 1:
        names = ", ".join(path.name for path in matches) or "none"
        raise ValueError(
            f"Expected one specification for {data_path.name}, found {names}"
        )
    return matches[0]


def unique_headers(headers: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    result = []
    for header in headers:
        header = header.replace(",  ,", "_")
        counts[header] = counts.get(header, 0) + 1
        result.append(
            header if counts[header] == 1 else f"{header}_{counts[header]}"
        )
    return result


ENUMERATION_COMMA = re.compile(r",[ \t]*(?=[^\W\d_])", re.UNICODE)


def normalize_row_text(row_text: str) -> str:
    def remove_enumeration_comma(match: re.Match[str]) -> str:
        next_character = row_text[match.end()]
        if next_character.islower():
            return match.group(0)[1:]
        return match.group(0)

    return ENUMERATION_COMMA.sub(remove_enumeration_comma, row_text)


def combine_file(data_path: Path, specification_path: Path, output_path: Path) -> None:
    mapping = read_specification(specification_path)
    with data_path.open(encoding="utf-8", newline="") as source:
        reader = csv.reader(source)
        source_codes = [
            code.lstrip("\ufeff").strip().lower() for code in next(reader)
        ]
        headers = unique_headers(
            [mapping.get(code, code) for code in source_codes]
        )

        with output_path.open("w", encoding="utf-8-sig", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(headers)
            for row in csv.reader(
                (normalize_row_text(line) for line in source)
            ):
                writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combina fisierele .txt si specificatiile .csv data.gov.ro."
    )
    parser.add_argument("--dataset-url", required=True)
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    dataset_id = dataset_id_from_url(args.dataset_url)
    dataset_root = (
        Path(__file__).resolve().parents[2] / "dataset" / "data.gov.ro"
    )
    if args.input_dir is None:
        args.input_dir = dataset_root / dataset_id
    if args.output_dir is None:
        args.output_dir = dataset_root / f"{dataset_id}_combined"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    specifications = sorted(args.input_dir.glob("*.csv"))
    data_files = sorted(args.input_dir.glob("*.txt"))
    if not specifications or not data_files:
        raise FileNotFoundError("Input directory must contain .txt and .csv files")

    for data_path in data_files:
        try:
            specification_path = find_specification(data_path, specifications)
        except ValueError as error:
            logging.warning("Skipping %s: %s", data_path.name, error)
            continue
        output_path = args.output_dir / f"{data_path.stem}.csv"
        logging.info(
            "Combining %s with %s -> %s",
            data_path.name,
            specification_path.name,
            output_path.name,
        )
        combine_file(data_path, specification_path, output_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
