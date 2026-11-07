import base64
import time
from pathlib import Path
from urllib.request import Request, urlopen
import socket

ROOT = Path(__file__).resolve().parent.parent

config = {}
for line in (ROOT / ".env.local").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        config[key] = value

host = socket.gethostbyname(config["CLICKHOUSE_HOST"])
port = config["CLICKHOUSE_HTTP_PORT"]
user = config["CLICKHOUSE_USER"]
password = config["CLICKHOUSE_PASSWORD"]

url = f"http://{host}:{port}/?query=SELECT%201"
credentials = base64.b64encode(
    f"{user}:{password}".encode()
).decode()

request = Request(
    url,
    headers={"Authorization": f"Basic {credentials}"}
)

for attempt in range(60):
    try:
        with urlopen(request, timeout=2) as response:
            if response.status == 200:
                print("ClickHouse is ready!")
                break
    except Exception:
        pass

    time.sleep(1)
else:
    raise SystemExit("ERROR: ClickHouse is unavailable")
