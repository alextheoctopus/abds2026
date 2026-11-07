from datetime import date, datetime, timedelta
import re

from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from database import get_client

app = FastAPI(title="EnergoSbyt API")
MAX_UINT64 = 2 ** 64 - 1
MAX_UINT32 = 2 ** 32 - 1
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def error(message: str, status: int = 400):
    raise HTTPException(status_code=status, detail=message)


@app.exception_handler(HTTPException)
async def handle_http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": str(exc.detail)}
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"message": "invalid request"})


def positive_id(value: int) -> int:
    if not 1 <= value <= MAX_UINT64:
        error("Not found", 404)
    return value


def unsigned(value, field: str, bits: int = 64, positive: bool = True) -> int:
    lower = 1 if positive else 0
    if type(value) is not int or not lower <= value <= 2 ** bits - 1:
        error(f'invalid "{field}" field')
    return value


def parse_date(value: str | None, field: str, *, parameter: bool = True) -> date:
    suffix = "parameter" if parameter else "field"
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        error(f'invalid "{field}" {suffix}')
    try:
        return date.fromisoformat(value)
    except ValueError:
        error(f'invalid "{field}" {suffix}')


def body_object(value):
    if not isinstance(value, dict):
        error("invalid request body")
    return value


def assert_keys(value: dict, allowed: set[str]):
    extra = set(value) - allowed
    if extra:
        error(f'invalid "{sorted(extra)[0]}" field')


def exists(client, table: str, record_id: int) -> bool:
    final = "FINAL" if table in ("dim_users", "dim_tariffs") else ""

    result = client.query(
        f"SELECT 1 FROM {table} {final} WHERE id = {{id:UInt64}} LIMIT 1",
        parameters={"id": record_id}
    )

    return bool(result.result_rows)


def user_record(client, user_id: int):
    return list(client.query(
        "SELECT id, fio, phone, phone_prev FROM dim_users FINAL "
        "WHERE id = {id:UInt64} LIMIT 1",
        parameters={"id": user_id},
    ).named_results())


@app.get("/ping")
def ping():
    """Проверка доступности API."""
    return Response(status_code=200)


@app.get("/users/{user_id}")
def get_user(user_id: int):
    """Получить актуального собственника."""
    positive_id(user_id)
    client = get_client()
    try:
        rows = user_record(client, user_id)
        if not rows:
            error("Not found", 404)
        return rows[0]
    finally:
        client.close()


@app.patch("/users/{user_id}", status_code=204)
def patch_user(user_id: int, body: dict = Body(...)):
    """SCD 1: изменение ФИО; SCD 3: изменение телефона."""

    positive_id(user_id)

    # Проверка тела запроса
    body = body_object(body)
    assert_keys(body, {"fio", "phone"})

    if not body:
        error('invalid "fio" field')

    # Проверка ФИО
    if "fio" in body:
        if type(body["fio"]) is not str or not body["fio"].strip():
            error('invalid "fio" field')

    # Проверка телефона
    if "phone" in body:
        if type(body["phone"]) is not str or not body["phone"].strip():
            error('invalid "phone" field')

    client = get_client()

    try:
        # Проверка существования собственника
        if not user_record(client, user_id):
            error("Not found", 404)

        updates = []
        parameters = {"user_id": user_id}

        # SCD 1: перезапись ФИО
        if "fio" in body:
            updates.append("fio = %(fio)s")
            parameters["fio"] = body["fio"]

        # SCD 3: сохранение предыдущего телефона
        if "phone" in body:
            updates.append("phone_prev = phone")
            updates.append("phone = %(phone)s")
            parameters["phone"] = body["phone"]

        # Выполнение изменения в ClickHouse
        query = f"""
            ALTER TABLE dim_users
            UPDATE {', '.join(updates)}
            WHERE id = %(user_id)s
        """

        client.command(
            query,
            parameters=parameters,
            settings={"mutations_sync": 1}
        )

        return Response(status_code=204)

    finally:
        client.close()


@app.get("/realty/{realty_id}")
def get_realty(realty_id: int):
    """Получить объект недвижимости."""
    positive_id(realty_id)
    client = get_client()
    try:
        rows = list(client.query(
            "SELECT id, address, square, type, number, rooms, floor, porch "
            "FROM dim_realty WHERE id = {id:UInt64} LIMIT 1",
            parameters={"id": realty_id},
        ).named_results())
        if not rows:
            error("Not found", 404)
        return rows[0]
    finally:
        client.close()


@app.post("/realty/{realty_id}/readings", status_code=201)
def post_reading(realty_id: int, body: dict = Body(...)):
    """Сохранить или исправить показания."""
    positive_id(realty_id)
    body = body_object(body)
    required = {"user_id", "gauge_id", "tariff_id", "reading_date", "day_kw", "night_kw"}
    assert_keys(body, required)
    values = {}
    for field in ("user_id", "gauge_id", "tariff_id"):
        values[field] = unsigned(body.get(field), field)
    for field in ("day_kw", "night_kw"):
        values[field] = unsigned(body.get(field), field, bits=32, positive=False)
    reading_date = parse_date(body.get("reading_date"), "reading_date", parameter=False)

    client = get_client()
    try:
        if not (exists(client, "dim_realty", realty_id)
                and exists(client, "dim_users", values["user_id"])
                and exists(client, "dim_gauges", values["gauge_id"])):
            error("Not found", 404)
        tariff = client.query(
            "SELECT id FROM dim_tariffs FINAL "
            "WHERE id = {id:UInt64} "
            "AND valid_from <= {moment:DateTime} AND valid_to > {moment:DateTime} LIMIT 1",
            parameters={"id": values["tariff_id"], "moment": datetime.combine(reading_date, datetime.min.time())},
        )
        if not tariff.result_rows:
            error("Not found", 404)
        # Ensure a correction has a strictly later version, even in the same second.
        latest = client.query(
            "SELECT max(created_at) FROM fact_meter_readings "
            "WHERE realty_id = {realty:UInt64} "
            "AND gauge_id = {gauge:UInt64} AND reading_date = {day:Date}",
            parameters={"realty": realty_id, "gauge": values["gauge_id"], "day": reading_date},
        ).result_rows[0][0]
        timestamp = datetime.now().replace(microsecond=0)
        if latest is not None and timestamp <= latest:
            timestamp = latest + timedelta(seconds=1)
        client.insert(
            "fact_meter_readings",
            [[realty_id, values["user_id"], values["tariff_id"],
              values["gauge_id"], reading_date, values["day_kw"], values["night_kw"], timestamp]],
            column_names=["realty_id", "user_id", "tariff_id", "gauge_id",
                          "reading_date", "day_kw", "night_kw", "created_at"],
        )
        return Response(status_code=201)
    finally:
        client.close()


@app.get("/realty/{realty_id}/readings")
def get_readings(realty_id: int, date_from: str | None = None, date_to: str | None = None):
    """Показания за период без дубликатов."""
    positive_id(realty_id)
    start = parse_date(date_from, "date_from")
    end = parse_date(date_to, "date_to")
    if start > end:
        error('invalid "date_from" parameter')
    client = get_client()
    try:
        if not exists(client, "dim_realty", realty_id):
            error("Not found", 404)
        rows = list(client.query(
            "SELECT reading_date, user_id, tariff_id, gauge_id, day_kw, night_kw "
            "FROM fact_meter_readings FINAL "
            "WHERE realty_id = {id:UInt64} "
            "AND reading_date >= {start:Date} AND reading_date <= {end:Date} "
            "ORDER BY reading_date, gauge_id",
            parameters={"id": realty_id, "start": start, "end": end},
        ).named_results())
        for row in rows:
            row["reading_date"] = row["reading_date"].strftime("%Y-%m-%d")
        return {"readings": rows, "count": len(rows)}
    finally:
        client.close()


@app.get("/realty/{realty_id}/invoices")
def get_invoices(realty_id: int, limit: str = "10", offset: str = "0"):
    """Счета объекта с пагинацией."""
    positive_id(realty_id)
    for field, value in (("limit", limit), ("offset", offset)):
        if not value.isascii() or not value.isdecimal() or int(value) > MAX_UINT64:
            error(f'invalid "{field}" parameter')
    limit_n, offset_n = int(limit), int(offset)
    client = get_client()
    try:
        if not exists(client, "dim_realty", realty_id):
            error("Not found", 404)
        count = client.query(
            "SELECT count() FROM fact_invoice WHERE realty_id = {id:UInt64}",
            parameters={"id": realty_id},
        ).result_rows[0][0]
        rows = list(client.query(
            "SELECT tariff_id, gauge_id, day_kw, night_kw, price, deadline, created_at "
            "FROM fact_invoice WHERE realty_id = {id:UInt64} "
            "ORDER BY created_at DESC, deadline DESC "
            "LIMIT {lim:UInt64} OFFSET {off:UInt64}",
            parameters={"id": realty_id, "lim": limit_n, "off": offset_n},
        ).named_results())
        for row in rows:
            row["deadline"] = row["deadline"].strftime("%Y-%m-%d")
            row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        return {"invoices": rows, "count": count}
    finally:
        client.close()


@app.get("/tariffs")
def get_tariffs(date: str | None = None):
    """Версия тарифа на указанную дату."""
    on_date = parse_date(date, "date")
    client = get_client()
    try:
        rows = list(client.query(
            "SELECT id, name, price_day_kwph, price_night_kwph, valid_from, valid_to "
            "FROM dim_tariffs FINAL "
            "WHERE valid_from <= {moment:DateTime} AND valid_to > {moment:DateTime} "
            "ORDER BY id LIMIT 1",
            parameters={"moment": datetime.combine(on_date, datetime.min.time())},
        ).named_results())
        if not rows:
            error("Not found", 404)
        row = rows[0]
        row["valid_from"] = row["valid_from"].strftime("%Y-%m-%d %H:%M:%S")
        row["valid_to"] = row["valid_to"].strftime("%Y-%m-%d %H:%M:%S")
        return row
    finally:
        client.close()


@app.post("/realty/{realty_id}/gauges", status_code=201)
def install_gauge(realty_id: int, body: dict = Body(...)):
    """Аннулировать старую установку и создать новую."""
    positive_id(realty_id)
    body = body_object(body)
    assert_keys(body, {"gauge_id"})
    gauge_id = unsigned(body.get("gauge_id"), "gauge_id")
    client = get_client()
    try:
        if not (exists(client, "dim_realty", realty_id)
                and exists(client, "dim_gauges", gauge_id)):
            error("Not found", 404)
        # A +1 and a -1 of the same key/version cancel one another.
        active = list(client.query(
            "SELECT gauge_id, realty_id, created_at, version, sum(sign) AS balance "
            "FROM fact_gauge_bindings WHERE realty_id = {id:UInt64} "
            "GROUP BY gauge_id, realty_id, created_at, version "
            "HAVING balance > 0 ORDER BY version DESC LIMIT 1",
            parameters={"id": realty_id},
        ).named_results())
        # Determine the next version across all historical installations.
        highest = client.query(
            "SELECT max(version) FROM fact_gauge_bindings "
            "WHERE realty_id = {id:UInt64}",
            parameters={"id": realty_id},
        ).result_rows[0][0]
        version = (highest or 0) + 1
        now = datetime.now().replace(microsecond=0)
        data = []
        if active:
            old = active[0]
            data.append([old["gauge_id"], realty_id, old["created_at"], -1, old["version"]])
        data.append([gauge_id, realty_id, now, 1, version])
        client.insert(
            "fact_gauge_bindings", data,
            column_names=["gauge_id", "realty_id", "created_at", "sign", "version"],
        )
        return Response(status_code=201)
    finally:
        client.close()
