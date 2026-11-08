# PostgreSQL dataset setup

This document explains how to reproduce the current PostgreSQL setup from
either:

- `postgres.dump`, the current database dump; or
- `dataset/data.gov.ro_filtered_cui.zip`, the filtered source files.

The dump and ZIP are intentionally not tracked by Git. They must be shared
separately with anyone who needs the same data.

## Requirements

- Docker Desktop with Docker Compose
- Python 3.13 or newer
- The repository
- `postgres.dump` or `dataset/data.gov.ro_filtered_cui.zip`

The project uses PostgreSQL 16 in Docker. PostgreSQL data is stored in the
persistent Docker volume `postgres_data`.

## Option 1: Restore the database dump

This is the fastest way to reproduce the current database, including its
tables and data.

1. Copy `postgres.dump` to the repository root.
2. Start PostgreSQL:

   ```powershell
   docker compose up -d
   ```

3. Wait until PostgreSQL is healthy:

   ```powershell
   docker compose ps
   ```

4. Restore the dump into the database:

   ```powershell
   cmd /c "docker compose exec -T postgres pg_restore -U firme -d firme --clean --if-exists < postgres.dump"
   ```

The default connection settings are:

```text
Host:     localhost
Port:     5432
Database: firme
User:     firme
Password: change-me
```

For a different password or port, define the variables before starting the
container:

```powershell
$env:POSTGRES_PASSWORD = "use-a-private-password"
$env:POSTGRES_PORT = "5433"
docker compose up -d
```

The dump was created in PostgreSQL custom format. It can be inspected with:

```powershell
cmd /c "docker compose exec -T postgres pg_restore --list < postgres.dump"
```

## Option 2: Rebuild from the filtered CSV ZIP

This option recreates the database by loading the filtered CSV files. The ZIP
contains only files from `*_filtered_cui` directories and preserves the
hierarchy below `dataset/data.gov.ro`.

1. Copy `data.gov.ro_filtered_cui.zip` to the `dataset` directory.
2. Extract it from the repository root:

   ```powershell
   Expand-Archive -LiteralPath dataset\data.gov.ro_filtered_cui.zip `
     -DestinationPath dataset -Force
   ```

   The result should contain paths such as:

   ```text
   dataset/data.gov.ro/situatii_financiare2023_filtered_cui/WEBASIG2023.csv
   ```

3. Start PostgreSQL:

   ```powershell
   docker compose up -d
   ```

4. Install the Python dependencies:

   ```powershell
   python -m pip install -e .
   ```

5. Inspect the planned tables and schemas without writing data:

   ```powershell
   python scripts\load_postgres.py --plan
   ```

6. Load the database:

   ```powershell
   python scripts\load_postgres.py
   ```

The loader also loads `dataset/firme.zip` into the `firme` table. To load only
the government datasets:

```powershell
python scripts\load_postgres.py --skip-firme
```

## How the loader works

The following processing steps have already been performed on the shared
source files and database:

1. The `firme.csv` file is stored in `dataset/firme.zip`.
2. Government files are searched only below directories ending in
   `_filtered_cui`.
3. The year is extracted from each government filename.
4. Government rows use `(cui, year)` as their primary key.
5. The `firme` table uses `cui` as its primary key.
6. CSV values are stored as text to avoid guessing incompatible data types.
7. Malformed CSV rows and rows with the wrong number of fields are skipped.
8. Rows with an empty `cui` are skipped for government datasets.
9. Similar CSV schemas reuse the same PostgreSQL table.
10. Different schemas receive different table names. A short schema hash is
    appended when the preferred table name is already used by another schema.
11. Data loading uses PostgreSQL `COPY` into a temporary staging table,
    followed by one set-based `INSERT ... ON CONFLICT DO NOTHING`.
12. `dataset_tables` records schema-to-table mappings.
13. `dataset_imports` records source files, target tables, years, and row
    counts.

The current filtered ZIP is the source snapshot used for the current
filtered-file setup. It can be used to rebuild a database, but the dump is
the authoritative fastest way to reproduce the current database contents.

## Inspecting schemas and row counts

Export the current public table definitions:

```powershell
python scripts\export_postgres_schema.py
```

This writes `postgres_schema.sql`. The file contains table definitions,
primary keys, and estimated row counts, but no table data.

The read-only load plan can be reviewed before loading source files:

```powershell
python scripts\load_postgres.py --plan
```

## Testing the connection

After loading or restoring:

```powershell
python scripts\test_postgres.py
```

This inserts the deterministic test CUI `99999999` into `firme` if it is not
already present and verifies that it can be read back.

## Creating a new dump

To share a later database snapshot:

```powershell
cmd /c "docker compose exec -T postgres pg_dump -U firme -d firme --format=custom > postgres.dump"
```

The dump is ignored by Git through `.gitignore`. Share it through the agreed
file-transfer method rather than committing it to the repository.

## Important notes

- Do not run `docker compose down -v` unless you intentionally want to delete
  the persistent PostgreSQL volume and all database data.
- The initialization SQL in
  `docker/postgres/init/001_schema.sql` runs automatically only when the
  PostgreSQL data directory is initialized for the first time.
- If PostgreSQL is already initialized, changing that SQL file does not
  retroactively modify existing tables.
- The dump includes the database contents at the time it was created. New
  CSV changes require a new load or a new dump.
