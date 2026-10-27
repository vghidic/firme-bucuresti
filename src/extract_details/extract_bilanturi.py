import argparse
import csv
import logging
from datetime import date
from pathlib import Path

import requests

from extract_details_for_cui import (
    BILANT_FIELDS,
    BILANT_INDICATOR_FIELDS,
    BILANT_URL,
    Client,
    normalize_indicator_name,
)


def registered_before_year(value, year):
    try:
        registered = date.fromisoformat((value or "").strip())
    except ValueError:
        return False
    return registered.year < year


def read_eligible_cuis(path, year):
    with open(path, encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            cui = (row.get("cui") or "").strip()
            if (
                cui
                and registered_before_year(
                    row.get("data_inregistrare_anaf"), year
                )
            ):
                yield cui


def main():
    parser = argparse.ArgumentParser(
        description="Construieste fisierele bilanturi_<an>.csv"
    )
    parser.add_argument(
        "--firms-file",
        default=r"..\..\dataset\firme.csv",
        help="Fisierul firme.csv sursa",
    )
    parser.add_argument("--out-dir", default=r"..\..\dataset")
    parser.add_argument("--cache-dir", default=".cache_anaf_bilant")
    parser.add_argument("--years", nargs="+", required=True, type=int)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--error-file", default="erori_bilant.csv")
    args = parser.parse_args()

    if args.delay < 0.2:
        parser.error("--delay trebuie sa fie de minimum 0.2 secunde")
    if args.start_index < 0:
        parser.error("--start-index nu poate fi negativ")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit trebuie sa fie pozitiv")

    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    years = list(dict.fromkeys(args.years))
    logging.info("Fisier firme: %s", args.firms_file)
    logging.info("Ani solicitatI: %s", ", ".join(map(str, years)))
    logging.info("Director output: %s", output)

    with open(
        output / args.error_file, "w", encoding="utf-8-sig", newline=""
    ) as error_file:
        errors = csv.DictWriter(
            error_file, fieldnames=["cui", "etapa", "an", "eroare"]
        )
        errors.writeheader()
        clients = {
            year: Client(f"{args.cache_dir}_{year}", args.delay)
            for year in years
        }

        for year in years:
            logging.info(
                "An %s: citesc CUI-urile eligibile streaming dupa "
                "start-index=%s si limit=%s",
                year,
                args.start_index,
                args.limit if args.limit is not None else "fara limita",
            )
            output_file = output / f"bilanturi_{year}.csv"
            logging.info(
                "An %s: output=%s cache=%s",
                year,
                output_file,
                clients[year].cache_dir,
            )

            with open(
                output_file, "w", encoding="utf-8-sig", newline=""
            ) as balance_file:
                financials = csv.DictWriter(
                    balance_file,
                    fieldnames=BILANT_FIELDS,
                    extrasaction="ignore",
                )
                financials.writeheader()
                indicator_fields = {
                    normalize_indicator_name(name): name
                    for name in BILANT_INDICATOR_FIELDS
                }

                processed = 0
                eligible_count = 0
                for cui in read_eligible_cuis(args.firms_file, year):
                    if eligible_count < args.start_index:
                        eligible_count += 1
                        continue
                    if args.limit is not None and processed >= args.limit:
                        break
                    eligible_count += 1
                    processed += 1
                    try:
                        record = clients[year].get_json(
                            "GET",
                            BILANT_URL,
                            params={"an": year, "cui": int(cui)},
                        )
                        data = record["data"]
                        indicators = data["i"]
                        row = {
                            "cui": cui,
                            "an": year,
                            "colectat_la": record["colectat_la"],
                            "denumire": data.get("deni"),
                            "cod_caen": data.get("caen"),
                        }
                        for indicator in indicators:
                            name = indicator_fields.get(
                                normalize_indicator_name(
                                    indicator.get("val_den_indicator")
                                )
                            )
                            if name:
                                row[name] = indicator.get("val_indicator")
                        financials.writerow(row)
                    except (requests.RequestException, ValueError, KeyError) as exc:
                        logging.error(
                            "An %s, CUI %s: %s", year, cui, exc
                        )
                        errors.writerow({
                            "cui": cui,
                            "etapa": "bilant",
                            "an": year,
                            "eroare": str(exc),
                        })
                    if processed % 100 == 0:
                        balance_file.flush()
                        error_file.flush()
                        logging.info(
                            "An %s: %s CUI-uri procesate",
                            year,
                            processed,
                        )
                logging.info(
                    "An %s finalizat: %s CUI-uri procesate din %s eligibile; "
                    "fisier=%s",
                    year,
                    processed,
                    eligible_count,
                    output_file,
                )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    main()
