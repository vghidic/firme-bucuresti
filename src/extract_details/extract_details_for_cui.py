import argparse
import csv
import hashlib
import json
import logging
import re
import time
from contextlib import ExitStack
from datetime import date, datetime, timezone
from pathlib import Path

import requests


TVA_URL = "https://webservicesp.anaf.ro/api/PlatitorTvaRest/v9/tva"
BILANT_URL = "https://webservicesp.anaf.ro/bilant"

FIRME_FIELDS = [
    "cui", "data_interogare", "colectat_la", "status_extragere",
    "denumire", "nr_reg_com", "cod_caen", "forma_juridica",
    "forma_organizare", "stare_inregistrare_anaf",
    "data_inregistrare_anaf", "platitor_tva", "tva_incasare",
    "inactiv_fiscal", "data_inactivare", "data_reactivare",
    "adresa", "judet", "localitate", "strada", "numar",
    "cod_postal", "detalii_adresa",
]

BILANT_INDICATOR_FIELDS = [
    "ACTIVE IMOBILIZATE - TOTAL",
    "ACTIVE CIRCULANTE - TOTAL, din care:",
    "Stocuri",
    "Creante",
    "Casa şi conturi la bănci",
    "CHELTUIELI IN AVANS",
    "DATORII",
    "VENITURI IN AVANS",
    "PROVIZIOANE",
    "CAPITALURI - TOTAL, din care:",
    "Capital subscris varsat",
    "Patrimoniul regiei",
    "Cifra de afaceri neta",
    "VENITURI TOTALE",
    "CHELTUIELI TOTALE",
    "Profit brut",
    "Pierdere bruta",
    "Profit net",
    "Pierdere neta",
    "Numar mediu de salariati",
]

BILANT_FIELDS = [
    "cui", "an", "colectat_la", "denumire", "cod_caen",
    *BILANT_INDICATOR_FIELDS,
]


def normalize_indicator_name(value):
    return " ".join(str(value or "").split())


def normalize_cui(value):
    value = str(value).strip().upper()
    if value.startswith("RO"):
        value = value[2:].strip()
    if not re.fullmatch(r"[0-9]{2,10}", value):
        raise ValueError("Format CUI invalid")
    number = int(value)
    if number <= 0:
        raise ValueError("CUI trebuie sa fie pozitiv")
    return str(number)


def read_cuis(path):
    seen = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        for line, row in enumerate(csv.reader(f), start=1):
            if not row or not any(x.strip() for x in row):
                continue
            if (
                line == 1
                and row[0].strip().lower() in {
                    "cui", "cif", "cod_fiscal", "cod fiscal"
                }
                and all(not value.strip() for value in row[1:])
            ):
                continue
            if len(row) != 1:
                raise ValueError(
                    f"Linia {line}: CSV-ul trebuie sa aiba o singura coloana"
                )
            value = row[0].strip()
            if line == 1 and value.lower() in {
                "cui", "cif", "cod_fiscal", "cod fiscal"
            }:
                continue
            try:
                cui = normalize_cui(value)
            except ValueError as exc:
                yield None, value, f"Linia {line}: {exc}"
                continue
            if cui not in seen:
                seen.add(cui)
                yield cui, value, None


class Client:
    def __init__(self, cache_dir, delay):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "ResearchCompanyDataset/1.0"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.last_request = 0.0

    def get_json(self, method, url, *, payload=None, params=None):
        identity = json.dumps(
            [method, url, payload, params],
            sort_keys=True, ensure_ascii=False
        )
        key = hashlib.sha256(identity.encode()).hexdigest()
        cache_file = self.cache_dir / f"{key}.json"

        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        for attempt in range(6):
            wait = self.delay - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
            self.last_request = time.monotonic()

            try:
                if method == "GET":
                    response = self.session.get(
                        url,
                        params=params,
                        timeout=(15, 60),
                    )
                else:
                    response = self.session.post(
                        url,
                        json=payload,
                        params=params,
                        timeout=(15, 90),
                    )
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Raspunsul JSON nu este un obiect")

                if method == "POST":
                    if not isinstance(data.get("found"), list):
                        raise ValueError("Lipseste lista 'found' din raspuns")
                    if not isinstance(data.get("notFound"), list):
                        raise ValueError("Lipseste lista 'notFound' din raspuns")
                elif (
                    str(data.get("cui")) != str(params["cui"])
                    or str(data.get("an")) != str(params["an"])
                    or not isinstance(data.get("i"), list)
                ):
                    raise ValueError(
                        "Raspuns bilant fara indicatori sau identificatori corecti"
                    )

                record = {
                    "colectat_la": datetime.now(timezone.utc).isoformat(),
                    "data": data,
                }
                temporary = cache_file.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(record, ensure_ascii=False),
                    encoding="utf-8"
                )
                temporary.replace(cache_file)
                return record

            except (requests.RequestException, ValueError) as exc:
                if isinstance(exc, requests.HTTPError):
                    status = exc.response.status_code
                    if status not in {408, 429} and status < 500:
                        raise

                if attempt == 5:
                    raise

                backoff = min(60, 2 ** (attempt + 1))
                if isinstance(exc, requests.HTTPError):
                    retry_after = exc.response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        backoff = max(backoff, int(retry_after))

                logging.warning(
                    "Cerere esuata (%s); reincerc peste %ss", exc, backoff
                )
                time.sleep(backoff)


def flatten_company(item):
    general = item.get("date_generale") or {}
    address = item.get("adresa_sediu_social") or {}
    inactive = item.get("stare_inactiv") or {}

    return {
        "denumire": general.get("denumire"),
        "nr_reg_com": general.get("nrRegCom"),
        "cod_caen": general.get("cod_CAEN"),
        "forma_juridica": general.get("forma_juridica"),
        "forma_organizare": general.get("forma_organizare"),
        "stare_inregistrare_anaf": general.get("stare_inregistrare"),
        "data_inregistrare_anaf": general.get("data_inregistrare"),
        "platitor_tva": (item.get("inregistrare_scop_Tva") or {}).get(
            "scpTVA"
        ),
        "tva_incasare": (item.get("inregistrare_RTVAI") or {}).get(
            "statusTvaIncasare"
        ),
        "inactiv_fiscal": inactive.get("statusInactivi"),
        "data_inactivare": inactive.get("dataInactivare"),
        "data_reactivare": inactive.get("dataReactivare"),
        "adresa": general.get("adresa"),
        "judet": address.get("sdenumire_Judet"),
        "localitate": address.get("sdenumire_Localitate"),
        "strada": address.get("sdenumire_Strada"),
        "numar": address.get("snumar_Strada"),
        "cod_postal": address.get("scod_Postal"),
        "detalii_adresa": address.get("sdetalii_Adresa"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="CSV cu o singura coloana de CUI-uri")
    parser.add_argument("--out-dir", default="rezultate")
    parser.add_argument(
        "--cache-dir",
        help=(
            "Director cache; implicit .cache_anaf pentru informatii generale "
            "si .cache_anaf_bilant pentru bilanturi"
        ),
    )
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--years", nargs="*", type=int, default=[])
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument(
        "--start-index",
        type=int,
        default=0,
        help="Index zero-based al primului CUI valid de procesat",
    )
    parser.add_argument("--limit", type=int, help="Numar maxim de CUI-uri valide")
    parser.add_argument(
        "--only-balance",
        action="store_true",
        help="Extrage doar datele de bilant, fara informatii generale",
    )
    parser.add_argument(
        "--error-file",
        help="Numele fisierului de erori din --out-dir",
    )
    args = parser.parse_args()

    date.fromisoformat(args.date)
    if args.only_balance and not args.years:
        parser.error("--only-balance necesita cel putin un an in --years")
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
    error_file = args.error_file or (
        "erori_bilant.csv" if args.only_balance else "erori.csv"
    )
    years = list(dict.fromkeys(args.years))
    with ExitStack() as stack:
        ff = None
        firms = None
        if not args.only_balance:
            ff = stack.enter_context(
                open(
                    output / "firme.csv",
                    "w",
                    encoding="utf-8-sig",
                    newline="",
                )
            )
            firms = csv.DictWriter(ff, fieldnames=FIRME_FIELDS)
        fe = stack.enter_context(
            open(output / error_file, "w", encoding="utf-8-sig", newline="")
        )
        balance_files = {
            year: stack.enter_context(
                open(
                    output / f"bilanturi_{year}.csv",
                    "w",
                    encoding="utf-8-sig",
                    newline="",
                )
            )
            for year in years
        }
        financials = {
            year: csv.DictWriter(
                balance_files[year],
                fieldnames=BILANT_FIELDS,
                extrasaction="ignore",
            )
            for year in years
        }
        errors = csv.DictWriter(
            fe, fieldnames=["cui", "etapa", "an", "eroare"]
        )
        if firms:
            firms.writeheader()
        for writer in financials.values():
            writer.writeheader()
        errors.writeheader()

        general_cache_dir = args.cache_dir or ".cache_anaf"
        client = (
            Client(general_cache_dir, args.delay)
            if not args.only_balance else None
        )
        balance_clients = {
            year: Client(
                f"{args.cache_dir or '.cache_anaf_bilant'}_{year}",
                args.delay,
            )
            for year in years
        }

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

        logging.info("%s CUI-uri valide, unice", len(cuis))

        if not args.only_balance:
            for start in range(0, len(cuis), args.batch_size):
                batch = cuis[start:start + args.batch_size]
                found = {}
                collected = ""
                batch_error = None

                try:
                    record = client.get_json(
                        "POST", TVA_URL,
                        payload=[
                            {"cui": int(cui), "data": args.date}
                            for cui in batch
                        ],
                    )
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
                            "eroare": batch_error
                        })
                    elif cui not in found:
                        row["status_extragere"] = "negasit"
                        errors.writerow({
                            "cui": cui, "etapa": "date_generale",
                            "eroare": "CUI absent din lista found"
                        })
                    else:
                        row["status_extragere"] = "gasit"
                        row.update(flatten_company(found[cui]))

                    firms.writerow(row)

                ff.flush()
                fe.flush()
                logging.info(
                    "Date generale: %s/%s",
                    min(start + len(batch), len(cuis)), len(cuis)
                )

        for index, cui in enumerate(cuis, start=1):
            for year in years:
                try:
                    record = balance_clients[year].get_json(
                        "GET", BILANT_URL,
                        params={"an": year, "cui": int(cui)},
                    )
                    data = record["data"]
                    indicators = data["i"]

                    if not indicators:
                        errors.writerow({
                            "cui": cui, "etapa": "bilant", "an": year,
                            "eroare": "Lista de indicatori este goala"
                        })

                    row = {
                        "cui": cui,
                        "an": year,
                        "colectat_la": record["colectat_la"],
                        "denumire": data.get("deni"),
                        "cod_caen": data.get("caen"),
                    }
                    indicator_fields = {
                        normalize_indicator_name(name): name
                        for name in BILANT_INDICATOR_FIELDS
                    }
                    for indicator in indicators:
                        name = indicator_fields.get(
                            normalize_indicator_name(
                                indicator.get("val_den_indicator")
                            )
                        )
                        if name:
                            row[name] = indicator.get("val_indicator")
                    financials[year].writerow(row)
                except (requests.RequestException, ValueError, KeyError) as exc:
                    errors.writerow({
                        "cui": cui, "etapa": "bilant",
                        "an": year, "eroare": str(exc)
                    })

            if years:
                for balance_file in balance_files.values():
                    balance_file.flush()
                fe.flush()
                logging.info("Bilanturi: %s/%s", index, len(cuis))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )
    main()