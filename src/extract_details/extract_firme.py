import argparse
import csv
import logging
from datetime import date
from pathlib import Path

import requests

from extract_details_for_cui import (
    FIRME_FIELDS,
    Client,
    TVA_URL,
    flatten_company,
    normalize_cui,
    read_cuis,
)


def main():
    parser = argparse.ArgumentParser(
        description="Construieste firme.csv din datele ANAF"
    )
    parser.add_argument("input", help="CSV cu o singura coloana de CUI-uri")
    parser.add_argument("--out-dir", default="rezultate")
    parser.add_argument("--cache-dir", default=".cache_anaf")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--error-file", default="erori.csv")
    args = parser.parse_args()

    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size trebuie sa fie intre 1 si 100")
    if args.delay < 0.2:
        parser.error("--delay trebuie sa fie de minimum 0.2 secunde")
    if args.start_index < 0:
        parser.error("--start-index nu poate fi negativ")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit trebuie sa fie pozitiv")

    output = Path(args.out_dir)
    output.mkdir(parents=True, exist_ok=True)
    client = Client(args.cache_dir, args.delay)

    with (
        open(output / "firme.csv", "w", encoding="utf-8-sig", newline="") as ff,
        open(output / args.error_file, "w", encoding="utf-8-sig", newline="") as fe,
    ):
        firms = csv.DictWriter(ff, fieldnames=FIRME_FIELDS)
        errors = csv.DictWriter(
            fe, fieldnames=["cui", "etapa", "an", "eroare"]
        )
        firms.writeheader()
        errors.writeheader()

        cuis = []
        valid_index = 0
        for cui, original, error in read_cuis(args.input):
            if error:
                errors.writerow({
                    "cui": original, "etapa": "input", "eroare": error
                })
                continue
            if valid_index < args.start_index:
                valid_index += 1
                continue
            cuis.append(cui)
            valid_index += 1
            if args.limit and len(cuis) >= args.limit:
                break

        for start in range(0, len(cuis), args.batch_size):
            batch = cuis[start:start + args.batch_size]
            found = {}
            collected = ""
            batch_error = None
            try:
                payload = [
                    {"cui": int(cui), "data": args.date}
                    for cui in batch
                ]
                record = client.get_json("POST", TVA_URL, payload=payload)
                collected = record["colectat_la"]
                for item in record["data"]["found"]:
                    key = normalize_cui(item["date_generale"]["cui"])
                    found[key] = item
            except (requests.RequestException, ValueError, KeyError) as exc:
                batch_error = str(exc)
                logging.error("Lot esuat: %s", exc)

            for cui in batch:
                row = {
                    "cui": cui,
                    "data_interogare": args.date,
                    "colectat_la": collected,
                }
                if batch_error:
                    row["status_extragere"] = "eroare"
                    errors.writerow({
                        "cui": cui, "etapa": "date_generale",
                        "eroare": batch_error,
                    })
                elif cui not in found:
                    row["status_extragere"] = "negasit"
                    errors.writerow({
                        "cui": cui, "etapa": "date_generale",
                        "eroare": "CUI absent din lista found",
                    })
                else:
                    row["status_extragere"] = "gasit"
                    row.update(flatten_company(found[cui]))
                firms.writerow(row)

            ff.flush()
            fe.flush()
            logging.info(
                "Date generale: %s/%s",
                min(start + len(batch), len(cuis)),
                len(cuis),
            )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    main()
