
import argparse
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_sql(sql_file: Path):
    if not sql_file.is_file():
        raise FileNotFoundError(f"SQL file not found: {sql_file}")

    command = [
        "docker", "compose",
        "--env-file", ".env.local",
        "exec", "-T", "clickhouse",
        "sh", "-c",
        'exec clickhouse-client '
        '--user "$CLICKHOUSE_USER" '
        '--password "$CLICKHOUSE_PASSWORD" '
        '--database "$CLICKHOUSE_DB" '
        '--multiquery'
    ]

    print(f"Executing SQL file: {sql_file.name}", flush=True)

    with sql_file.open("rb") as file:
        subprocess.run(
            command,
            stdin=file,
            cwd=PROJECT_ROOT,
            check=True
        )

    print("SQL executed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sql_file", type=Path)
    args = parser.parse_args()

    run_sql((PROJECT_ROOT / args.sql_file).resolve())
