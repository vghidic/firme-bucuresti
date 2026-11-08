"""Load firme.csv and data.gov.ro CSV files into PostgreSQL.

The loader deliberately creates text columns. Government files contain mixed
representations of numbers, dates, and empty values, so preserving the source
values is safer than guessing types during ingestion.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Iterable, TextIO

import psycopg
from psycopg import sql


YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")
ENCODINGS = ("utf-8-sig", "utf-8", "cp1250", "cp1252", "latin-1")


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host="localhost",
        port=int(__import__("os").environ.get("POSTGRES_PORT", "5432")),
        dbname=__import__("os").environ.get("POSTGRES_DB", "firme"),
        user=__import__("os").environ.get("POSTGRES_USER", "firme"),
        password=__import__("os").environ.get("POSTGRES_PASSWORD", "change-me"),
    )


def open_text(path: Path) -> TextIO:
    raw = path.read_bytes()
    for encoding in ENCODINGS:
        try:
            return io.StringIO(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Could not decode {path}")


def parse_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;|\t").delimiter
    except csv.Error:
        return ";"


def clean_identifier(value: str, position: int) -> str:
    value = value.lstrip("\ufeff").strip().lower()
    value = re.sub(r"[^a-z0-9_]+", "_", value).strip("_")
    if not value:
        value = f"column_{position}"
    if value[0].isdigit():
        value = f"column_{value}"
    return value[:63]


def unique_headers(headers: Iterable[str]) -> list[str]:
    result: list[str] = []
    counts: dict[str, int] = {}
    for position, header in enumerate(headers, 1):
        name = clean_identifier(header, position)
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            name = f"{name[: max(1, 63 - len(str(counts[name])) - 1)]}_{counts[name]}"
        result.append(name)
    return result


def table_base_name(path: Path) -> str:
    name = YEAR_RE.sub("", path.stem)
    name = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_").lower()
    return (name or "dataset")[:53]


def schema_hash(columns: list[str]) -> str:
    return hashlib.sha256("\0".join(columns).encode()).hexdigest()


def ensure_table(
    connection: psycopg.Connection, columns: list[str], preferred_name: str
) -> str:
    digest = schema_hash(columns)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name FROM dataset_tables WHERE schema_hash = %s",
            (digest,),
        )
        existing = cursor.fetchone()
        if existing:
            return existing[0]

        cursor.execute(
            "SELECT table_name, array_agg(column_name ORDER BY ordinal_position) "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "GROUP BY table_name"
        )
        for table_name, existing_columns in cursor.fetchall():
            if list(existing_columns) == columns:
                cursor.execute(
                    "INSERT INTO dataset_tables "
                    "(schema_hash, table_name, columns_json) VALUES (%s, %s, %s::jsonb) "
                    "ON CONFLICT (schema_hash) DO NOTHING",
                    (digest, table_name, __import__("json").dumps(columns)),
                )
                return table_name

        table_name = preferred_name
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table_name,),
        )
        if cursor.fetchone():
            table_name = f"{preferred_name}_{digest[:8]}"

        definitions = [
            sql.SQL("{} TEXT").format(sql.Identifier(column)) for column in columns
        ]
        definitions.append(
            sql.SQL("PRIMARY KEY ({}, {})").format(
                sql.Identifier("cui"), sql.Identifier("year")
            )
        )
        cursor.execute(
            sql.SQL("CREATE TABLE {} ({})").format(
                sql.Identifier(table_name), sql.SQL(", ").join(definitions)
            )
        )
        cursor.execute(
            "INSERT INTO dataset_tables (schema_hash, table_name, columns_json) "
            "VALUES (%s, %s, %s::jsonb)",
            (digest, table_name, __import__("json").dumps(columns)),
        )
    return table_name


def database_table_schemas(connection: psycopg.Connection) -> dict[str, list[str]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, array_agg(column_name ORDER BY ordinal_position) "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' "
            "GROUP BY table_name"
        )
        return {
            table_name: list(columns)
            for table_name, columns in cursor.fetchall()
        }


def planned_table_name(
    columns: list[str],
    preferred_name: str,
    table_schemas: dict[str, list[str]],
    planned_schemas: dict[str, list[str]],
) -> tuple[str, bool]:
    digest = schema_hash(columns)
    for table_name, existing_columns in {
        **table_schemas,
        **planned_schemas,
    }.items():
        if existing_columns == columns:
            return table_name, False

    table_name = preferred_name
    if table_name in table_schemas or table_name in planned_schemas:
        table_name = f"{preferred_name}_{digest[:8]}"
    return table_name, True


def plan_load(
    connection: psycopg.Connection,
    archive: Path,
    data_root: Path,
    skip_firme: bool,
) -> None:
    table_schemas = database_table_schemas(connection)
    planned_schemas: dict[str, list[str]] = {}
    print("READ-ONLY LOAD PLAN")
    print("No tables, rows, or import metadata will be written.")

    def show(source: str, table_name: str, columns: list[str], creates: bool) -> None:
        action = "CREATE" if creates else "REUSE"
        print(f"{action} {table_name} <- {source}")
        print(f"  columns ({len(columns)}): {', '.join(columns)}")

    if not skip_firme:
        with zipfile.ZipFile(archive) as source:
            with source.open("firme.csv") as binary:
                text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
                columns, _ = read_csv(text, str(archive))
        table_name, creates = planned_table_name(
            columns, "firme", table_schemas, planned_schemas
        )
        show(str(archive), table_name, columns, creates)
        planned_schemas.setdefault(table_name, columns)

    for path in filtered_cui_files(data_root):
        match = YEAR_RE.search(path.name)
        if not match:
            print(f"SKIP {path}: no year in filename")
            continue
        with open_text(path) as source:
            headers, _ = read_csv(source, str(path))
        if "cui" not in headers:
            print(f"SKIP {path}: no cui column")
            continue
        columns = headers + ["year"]
        table_name, creates = planned_table_name(
            columns,
            table_base_name(path),
            table_schemas,
            planned_schemas,
        )
        show(str(path), table_name, columns, creates)
        planned_schemas.setdefault(table_name, columns)


def read_csv(source: TextIO, path: str) -> tuple[list[str], Iterable[list[str]]]:
    sample = source.read(8192)
    source.seek(0)
    delimiter = parse_delimiter(sample)
    reader = csv.reader(source, delimiter=delimiter, strict=True)
    headers = unique_headers(next(reader))

    def rows() -> Iterable[list[str]]:
        while True:
            try:
                row = next(reader)
            except StopIteration:
                return
            except csv.Error as error:
                logging.warning("Skipping malformed row in %s: %s", path, error)
                continue
            if len(row) != len(headers):
                logging.warning(
                    "Skipping row with %d values (expected %d) in %s",
                    len(row),
                    len(headers),
                    path,
                )
                continue
            yield row

    return headers, rows()


def insert_rows(
    connection: psycopg.Connection,
    table_name: str,
    columns: list[str],
    rows: Iterable[list[str]],
    year: int | None,
) -> tuple[int, int]:
    insert_columns = columns + (["year"] if year is not None else [])
    stage_name = "dataset_load_stage"
    stage_definitions = [
        sql.SQL("{} TEXT").format(sql.Identifier(column))
        for column in insert_columns
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(
                sql.Identifier(stage_name), sql.SQL(", ").join(stage_definitions)
            )
        )
        copy_statement = sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT CSV)"
        ).format(
            sql.Identifier(stage_name),
            sql.SQL(", ").join(map(sql.Identifier, insert_columns)),
        )
        valid_rows = 0
        cui_index = columns.index("cui") if year is not None else None
        with cursor.copy(copy_statement) as copy:
            batch = io.StringIO(newline="")
            writer = csv.writer(batch, lineterminator="\n")
            for row in rows:
                values = row + ([str(year)] if year is not None else [])
                if cui_index is not None:
                    if not values[cui_index].strip():
                        continue
                writer.writerow(values)
                valid_rows += 1
                if valid_rows % 10_000 == 0:
                    copy.write(batch.getvalue())
                    batch.seek(0)
                    batch.truncate(0)
            if batch.tell():
                copy.write(batch.getvalue())

        cursor.execute(
            sql.SQL("INSERT INTO {} ({}) SELECT {} FROM {} "
                    "ON CONFLICT DO NOTHING"
            ).format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, insert_columns)),
                sql.SQL(", ").join(map(sql.Identifier, insert_columns)),
                sql.Identifier(stage_name),
            )
        )
        inserted = cursor.rowcount
    return inserted, valid_rows - inserted


def load_firme(connection: psycopg.Connection, archive: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        with source.open("firme.csv") as binary:
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")
            headers, rows = read_csv(text, str(archive))
            table_name = "firme"
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'firme'"
                )
                if not cursor.fetchone():
                    definitions = [
                        sql.SQL("{} TEXT").format(sql.Identifier(column))
                        for column in headers
                    ]
                    definitions.append(
                        sql.SQL("PRIMARY KEY ({})").format(sql.Identifier("cui"))
                    )
                    cursor.execute(
                        sql.SQL("CREATE TABLE {} ({})").format(
                            sql.Identifier(table_name), sql.SQL(", ").join(definitions)
                        )
                    )
            insert_rows(connection, table_name, headers, rows, None)
            connection.commit()
            logging.info("Loaded %s", archive)


def load_government_file(connection: psycopg.Connection, path: Path) -> None:
    match = YEAR_RE.search(path.name)
    if not match:
        logging.info("Skipping %s: no year in filename", path)
        return
    year = int(match.group(1))
    with open_text(path) as source:
        headers, rows = read_csv(source, str(path))
        if "cui" not in headers:
            logging.info("Skipping %s: no cui column", path)
            return
        columns = headers + ["year"]
        table_name = ensure_table(connection, columns, table_base_name(path))
        inserted, skipped = insert_rows(connection, table_name, headers, rows, year)
        connection.execute(
            "INSERT INTO dataset_imports "
            "(source_path, table_name, year, rows_inserted, rows_skipped) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (source_path) DO UPDATE SET "
            "rows_inserted = EXCLUDED.rows_inserted, "
            "rows_skipped = EXCLUDED.rows_skipped, imported_at = now()",
            (str(path), table_name, year, inserted, skipped),
        )
    connection.commit()
    logging.info("Loaded %s: %d inserted, %d skipped", path, inserted, skipped)


def filtered_cui_files(data_root: Path) -> list[Path]:
    return sorted(
        path
        for directory in data_root.rglob("*_filtered_cui")
        if directory.is_dir()
        for path in directory.glob("*.csv")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firme", type=Path, default=Path("dataset/firme.zip"))
    parser.add_argument(
        "--data-root", type=Path, default=Path("dataset/data.gov.ro")
    )
    parser.add_argument("--skip-firme", action="store_true")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print the table/schema plan without writing to PostgreSQL.",
    )
    args = parser.parse_args()

    with connect() as connection:
        if args.plan:
            plan_load(
                connection,
                args.firme,
                args.data_root,
                args.skip_firme,
            )
            return
        if not args.skip_firme:
            load_firme(connection, args.firme)
        for path in filtered_cui_files(args.data_root):
            load_government_file(connection, path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()
