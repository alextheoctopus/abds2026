
# Лабораторная №1. ClickHouse — ЭнергоСбыт

## Цель работы

Разработать хранилище данных ЖКХ-компании «ЭнергоСбыт» на ClickHouse с использованием схемы «звезда», реализовать SCD 1/2/3 и проверить работу движков MergeTree, ReplacingMergeTree и VersionedCollapsingMergeTree через SQL и HTTP API.

## Технологии

- **ClickHouse 26.7** — хранение и обработка данных.
- **Docker Compose** — запуск контейнеров.
- **Python** — генерация и загрузка CSV.
- **FastAPI** — HTTP-сервис.
- **Makefile** — автоматизация команд.

## Структура данных

Созданы 7 таблиц:

| Таблица | Движок | Назначение |
|---|---|---|
| `dim_realty` | MergeTree | Объекты недвижимости |
| `dim_gauges` | MergeTree | Счётчики |
| `dim_tariffs` | ReplacingMergeTree | История тарифов (SCD 2) |
| `dim_users` | ReplacingMergeTree | Собственники (SCD 1/3) |
| `fact_gauge_bindings` | VersionedCollapsingMergeTree | Установки и аннулирования счётчиков |
| `fact_meter_readings` | ReplacingMergeTree | Показания и корректировки |
| `fact_invoice` | MergeTree | Выставленные счета |

### Обоснование ключей и партиционирования

- Измерения сортируются по идентификаторам для эффективного поиска.
- `dim_tariffs`: `ORDER BY (id, valid_from)` позволяет сохранять исторические версии одного тарифа.
- `dim_users`: `ORDER BY id` обеспечивает выбор актуальной версии собственника.
- `fact_gauge_bindings`: `ORDER BY (gauge_id, realty_id)` обеспечивает сопоставление установки и аннулирования.
- `fact_meter_readings`: партиционирование по месяцу показания, сортировка по `(realty_id, gauge_id, reading_date)`.
- `fact_invoice`: партиционирование по месяцу выставления счёта, сортировка по `(realty_id, deadline, gauge_id, created_at)`.

Месячное партиционирование таблиц фактов упрощает обработку данных за отдельные периоды.

## Генерация данных

Команда `make gen` создаёт 7 CSV-файлов в папке `data/`.

| Таблица | Количество строк |
|---|---:|
| dim_realty | 1 000 |
| dim_gauges | 1 100 |
| dim_tariffs | 2 |
| dim_users | 1 000 |
| fact_gauge_bindings | 1 200 |
| fact_meter_readings | 1 128 901 |
| fact_invoice | 36 000 |

Данные включают замены счётчиков, исторические версии тарифов и около 3% корректировок показаний.

Повторный `make load` очищает таблицы перед загрузкой, предотвращая накопление дубликатов.

## Запуск

```bash
make run       # Запустить ClickHouse и HTTP-сервис
make setup     # Создать таблицы, сгенерировать и загрузить данные
make stop      # Остановить контейнеры
make teardown  # Удалить таблицы
```

HTTP-сервис доступен по адресу `http://localhost:8080`.

Swagger UI: `http://localhost:8080/docs`.

Конфигурация задаётся через `.env.local`.

## Проверка сценариев

Все сценарии проверены через HTTP-сервис и SQL.

| Сценарий | Реализация и проверка |
|---|---|
| SCD 1 | `ALTER TABLE dim_users UPDATE fio ...` — старое ФИО заменено |
| SCD 3 | `UPDATE phone_prev = phone, phone = ...` — сохраняется предыдущий телефон |
| SCD 2 | `dim_tariffs` хранит версии с разными `valid_from` / `valid_to`; выбор по дате |
| Исторические счета | Старые счета сохраняют первоначальную стоимость |
| Корректировка показаний | `INSERT` с новым `created_at`; `SELECT FINAL` возвращает одну версию |
| Замена счётчика | `sign = -1` аннулирует установку; новая получает следующую `version` |
| DELETE | `DELETE FROM fact_invoice WHERE ...` удаляет ошибочную запись |

### Примеры SQL-проверок

**SCD 1 и SCD 3:**

```sql
SELECT id, fio, phone, phone_prev
FROM energosbyt.dim_users FINAL
WHERE id = 1;
```

**SCD 2:**

```sql
SELECT *
FROM energosbyt.dim_tariffs FINAL
ORDER BY id, valid_from;
```

**Корректировки показаний:**

```sql
SELECT *
FROM energosbyt.fact_meter_readings FINAL
WHERE realty_id = 1
  AND reading_date = '2026-10-01';
```

**Активные установки счётчиков:**

```sql
SELECT gauge_id, realty_id, sum(sign) AS active
FROM energosbyt.fact_gauge_bindings
GROUP BY gauge_id, realty_id
HAVING active > 0;
```

**DELETE:**

```sql
DELETE FROM energosbyt.fact_invoice
WHERE realty_id = 1
  AND price = 930000
  AND created_at = '2026-11-07 12:00:00';
```

Повторный `SELECT` по тем же условиям возвращает 0 строк.

## Результат

Реализованы хранилище данных ClickHouse, генерация и загрузка датасетов, HTTP API и сценарии SCD 1/2/3. Проверены корректировки показаний, аннулирование установок счётчиков и удаление ошибочных записей.
