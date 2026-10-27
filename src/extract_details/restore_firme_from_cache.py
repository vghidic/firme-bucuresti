import argparse
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from extract_details_for_cui import FIRME_FIELDS, flatten_company, normalize_cui


def cache_timestamp(record):
    value = record.get("colectat_la", "")
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def restore(cache_dir):
    companies = {}
    json_files = sorted(Path(cache_dir).glob("*.json"))

    for cache_file in json_files:
        try:
            record = json.loads(cache_file.read_text(encoding="utf-8"))
            items = record["data"]["found"]
            if not isinstance(items, list):
                raise ValueError("Campul data.found nu este o lista")
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logging.warning("Cache ignorat %s: %s", cache_file.name, exc)
            continue

        for item in items:
            try:
                company = item["date_generale"]
                cui = normalize_cui(company["cui"])
            except (KeyError, TypeError, ValueError) as exc:
                logging.warning(
                    "Firma ignorata in %s: %s", cache_file.name, exc
                )
                continue

            candidate = {
                "cui": cui,
                "data_interogare": company.get("data"),
                "colectat_la": record.get("colectat_la"),
                "status_extragere": "gasit",
            }
            candidate.update(flatten_company(item))

            previous = companies.get(cui)
            if previous is None or cache_timestamp(record) >= cache_timestamp(
                previous
            ):
                companies[cui] = {
                    **candidate,
                    "_cache_timestamp": record.get("colectat_la"),
                }

    return companies


def main():
    parser = argparse.ArgumentParser(
        description="Restaureaza firme.csv din cache-ul ANAF"
    )
    parser.add_argument(
        "--cache-dir",
        default=".cache_anaf",
        help="Directorul cu fisierele JSON cache",
    )
    parser.add_argument(
        "--output",
        default="firme.csv",
        help="Fisierul CSV rezultat",
    )
    args = parser.parse_args()

    companies = restore(args.cache_dir)
    with open(args.output, "w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output, fieldnames=FIRME_FIELDS, extrasaction="ignore"
        )
        writer.writeheader()
        for cui in sorted(companies, key=int):
            writer.writerow(companies[cui])

    logging.info(
        "Restaurate %s firme din %s fisiere cache in %s",
        len(companies),
        args.cache_dir,
        args.output,
    )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    main()
