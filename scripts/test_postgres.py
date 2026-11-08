"""Insert a deterministic test row and verify it can be read back."""

from __future__ import annotations

import os

import psycopg


def main() -> None:
    with psycopg.connect(
        host="localhost",
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "firme"),
        user=os.environ.get("POSTGRES_USER", "firme"),
        password=os.environ.get("POSTGRES_PASSWORD", "change-me"),
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO firme (cui) VALUES ('99999999') "
                "ON CONFLICT (cui) DO NOTHING"
            )
            cursor.execute("SELECT cui FROM firme WHERE cui = '99999999'")
            row = cursor.fetchone()
            if row != ("99999999",):
                raise RuntimeError("The test row could not be read back")
            print("PostgreSQL test insert succeeded:", row[0])


if __name__ == "__main__":
    main()
