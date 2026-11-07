import csv
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
COMPOSE = ["docker", "compose", "--env-file", ".env.local"]
#проверить совпадают ли столбцы файлов загрузки с полями таблиц
TABLE_COLUMNS = {
    "dim_realty": ["id", "address", "square", "type", "number", "rooms", "floor", "porch", "created_at"],
    "dim_gauges": ["id", "name", "country", "created_at"],
    "dim_tariffs": ["id", "name", "price_day_kwph", "price_night_kwph", "valid_from", "valid_to", "created_at", "updated_at"],
    "dim_users": ["id", "fio", "phone", "phone_prev", "created_at", "updated_at"],
    "fact_gauge_bindings": ["gauge_id", "realty_id", "created_at", "sign", "version"],
    "fact_meter_readings": ["realty_id", "user_id", "tariff_id", "gauge_id", "reading_date", "day_kw", "night_kw", "created_at"],
    "fact_invoice": ["realty_id", "user_id", "tariff_id", "gauge_id", "day_kw", "night_kw", "price", "deadline", "created_at"],
}

#подключение к ClickHouse
def client_command(query: str) -> list[str]:
    return COMPOSE + [
        "exec", "-T", "clickhouse", "sh", "-c",
        'exec clickhouse-client --user "$CLICKHOUSE_USER" '
        '--password "$CLICKHOUSE_PASSWORD" --database "$CLICKHOUSE_DB" '
        f'--query "{query}"',
    ]

def execute(query: str, source: Path | None = None) -> None:
    if source is None:
        subprocess.run(client_command(query), cwd=ROOT, check=True)
    else:
        # Stream the CSV into the container: no large in-memory buffers.
        with source.open("rb") as stream:
            subprocess.run(client_command(query), cwd=ROOT, stdin=stream, check=True)


def validate_inputs() -> None:
    for table, expected_columns in TABLE_COLUMNS.items():
        path = DATA_DIR / f"{table}.csv"
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(f"Missing/empty CSV: {path}. Run 'make gen' first.")
        with path.open("r", newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f), [])
        if header != expected_columns:
            raise ValueError(
                f"Wrong header in {path.name}:\n"
                f"  expected: {expected_columns}\n"
                f"  actual:   {header}"
            )


def main() -> None:
    validate_inputs()  # Do not erase existing tables when input files are missing.
    start = time.perf_counter()
    print("Checking ClickHouse connection...", flush=True)
    execute("SELECT 1")
    print("All CSV files found. Replacing data in seven lab tables...", flush=True)

    for table in TABLE_COLUMNS:
        path = DATA_DIR / f"{table}.csv"
        print(f"[{table}] TRUNCATE + INSERT ({path.stat().st_size / 1024**2:.1f} MiB)", flush=True)
        execute(f"TRUNCATE TABLE {table}")
        execute(f"INSERT INTO {table} FORMAT CSVWithNames", source=path)

    print(f"Completed in {time.perf_counter() - start:.1f} seconds.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Load failed: {error}") from error