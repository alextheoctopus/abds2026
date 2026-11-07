
import csv
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SEED = 42
OBJECTS = 1_000
REPLACEMENTS = 100
START = date(2023, 11, 1)
END = date(2026, 10, 31)
REPLACEMENT_DATE = date(2025, 5, 1)
TARIFF_CHANGE_DATE = date(2025, 1, 1)
OPEN_END = "2099-01-01 00:00:00"
CREATED = "2023-10-01 09:00:00"
rng = random.Random(SEED)


def save_rows(table, fields, rows):
    path = DATA_DIR / f"{table}.csv"
    count = 0
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        for row in rows:
            writer.writerow(row)
            count += 1
    print(f"{table}: {count:,} rows", flush=True)
    return count


def generate_realty():
    rows = []
    for i in range(1, OBJECTS + 1):
        building = (i - 1) // 50 + 1
        is_nrcp = i % 10 == 0
        rows.append((
            i, f"Ижевск, ул. Пушкинская, д. {building}",
            rng.randint(40, 150) if is_nrcp else rng.randint(25, 110),
            "nrcp" if is_nrcp else "flat",
            "" if is_nrcp else str((i - 1) % 50 + 1),
            0 if is_nrcp else rng.randint(1, 4),
            (i - 1) % 9 + 1,
            (i - 1) % 4 + 1,
            CREATED,
        ))
    save_rows("dim_realty", ["id", "address", "square", "type", "number", "rooms", "floor", "porch", "created_at"], rows)


def generate_gauges():
    models = ("Меркурий 200", "Энергомера CE102", "НЕВА 103")
    rows = [(i, models[(i - 1) % len(models)], "Россия", CREATED)
            for i in range(1, OBJECTS + REPLACEMENTS + 1)]
    save_rows("dim_gauges", ["id", "name", "country", "created_at"], rows)



def generate_tariffs():
    # Two historical versions of ONE tariff with disjoint, half-open time ranges.
    rows = [
        (1, "Двухзонный", 500, 250,
         "2023-11-01 00:00:00", "2025-01-01 00:00:00",
         "2023-10-01 09:00:00", "2025-01-01 00:00:01"),
        (1, "Двухзонный", 650, 350,
         "2025-01-01 00:00:00", OPEN_END,
         "2025-01-01 00:00:00", "2025-01-01 00:00:01"),
    ]
    save_rows("dim_tariffs", ["id", "name", "price_day_kwph", "price_night_kwph", "valid_from", "valid_to", "created_at", "updated_at"], rows)


def generate_users():
    first = ("Иван", "Пётр", "Мария", "Анна", "Ольга")
    last = ("Иванов", "Петров", "Сидоров", "Смирнов", "Кузнецов")
    rows = [(i, f"{last[(i - 1) % 5]} {first[((i - 1) // 5) % 5]}",
             f"+7900{i:07d}", "", CREATED, CREATED)
            for i in range(1, OBJECTS + 1)]
    save_rows("dim_users", ["id", "fio", "phone", "phone_prev", "created_at", "updated_at"], rows)


def replacement_gauge(realty_id):
    # Exactly 100 objects (every tenth) are assigned replacement gauges.
    return OBJECTS + realty_id // 10


def gauge_for(realty_id, on_date):
    if realty_id % 10 == 0 and on_date >= REPLACEMENT_DATE:
        return replacement_gauge(realty_id)
    return realty_id


def generate_bindings():
    def rows():
        for i in range(1, OBJECTS + 1):
            installed_at = "2023-10-15 12:00:00"
            # Cancellation reproduces all non-sign values of installation.
            yield (i, i, installed_at, 1, 1)
            if i % 10 == 0:
                yield (i, i, installed_at, -1, 1)
                yield (replacement_gauge(i), i, "2025-05-01 00:00:00", 1, 2)

    save_rows("fact_gauge_bindings", ["gauge_id", "realty_id", "created_at", "sign", "version"], rows())


def month_after(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1


def generate_readings_and_invoices():
    # Stream readings to disk. Only per-object counters and month totals stay in RAM.
    fields = ["realty_id", "user_id", "tariff_id", "gauge_id", "reading_date", "day_kw", "night_kw", "created_at"]
    path = DATA_DIR / "fact_meter_readings.csv"
    counters = [(0, 0) for _ in range(OBJECTS + 1)]
    monthly = defaultdict(lambda: [0, 0])
    total = 0
    corrections = 0
    current = START

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(fields)
        while current <= END:
            day_str = current.isoformat()
            for i in range(1, OBJECTS + 1):
                if i % 10 == 0 and current == REPLACEMENT_DATE:
                    counters[i] = (0, 0)  # new physical meter starts from zero
                gauge_id = gauge_for(i, current)
                inc_day = rng.randint(1, 9)
                inc_night = rng.randint(0, 4)
                previous_day, previous_night = counters[i]
                cumulative_day = previous_day + inc_day
                cumulative_night = previous_night + inc_night

                # About 3% of dates are corrected. True readings and invoice
                # consumption use the corrected values, not the old ones.
                corrected = rng.random() < 0.03
                if corrected:
                    writer.writerow((i, i, 1, gauge_id, day_str,
                                     cumulative_day + 2, cumulative_night + 1,
                                     day_str + " 10:00:00"))
                    writer.writerow((i, i, 1, gauge_id, day_str,
                                     cumulative_day, cumulative_night,
                                     day_str + " 12:00:00"))
                    corrections += 1
                    total += 2
                else:
                    writer.writerow((i, i, 1, gauge_id, day_str,
                                     cumulative_day, cumulative_night,
                                     day_str + " 10:00:00"))
                    total += 1

                counters[i] = (cumulative_day, cumulative_night)
                totals = monthly[(i, current.year, current.month)]
                totals[0] += inc_day
                totals[1] += inc_night
            current += timedelta(days=1)

    print(f"fact_meter_readings: {total:,} rows ({corrections:,} corrected dates)", flush=True)

    def invoice_rows():
        for (realty_id, year, month), (day_kw, night_kw) in sorted(monthly.items()):
            price_day, price_night = (500, 250) if date(year, month, 1) < TARIFF_CHANGE_DATE else (650, 350)
            next_year, next_month = month_after(year, month)
            deadline = date(next_year, next_month, 10).isoformat()
            # Issued at month end, after the readings for that billing month.
            next_month_first = date(next_year, next_month, 1)
            issued = (next_month_first - timedelta(days=1)).isoformat() + " 20:00:00"
            yield (realty_id, realty_id, 1,
                   gauge_for(realty_id, next_month_first - timedelta(days=1)),
                   day_kw, night_kw, day_kw * price_day + night_kw * price_night,
                   deadline, issued)

    save_rows("fact_invoice", ["realty_id", "user_id", "tariff_id", "gauge_id", "day_kw", "night_kw", "price", "deadline", "created_at"], invoice_rows())


def main():
    generate_realty()
    generate_gauges()
    generate_tariffs()
    generate_users()
    generate_bindings()
    generate_readings_and_invoices()

if __name__ == "__main__":
    main()