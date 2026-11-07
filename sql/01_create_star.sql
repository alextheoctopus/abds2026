
-- DIMENSIONS

-- 1. Объекты недвижимости
CREATE TABLE IF NOT EXISTS energosbyt.dim_realty
(
    id UInt64,
    address String,
    square UInt32,
    type String,
    number String,
    rooms UInt8,
    floor UInt8,
    porch UInt8,
    created_at DateTime
)
    ENGINE = MergeTree()
    ORDER BY id;


-- 2. Модели счётчиков
CREATE TABLE IF NOT EXISTS energosbyt.dim_gauges
(
    id UInt64,
    name String,
    country String,
    created_at DateTime
)
    ENGINE = MergeTree()
    ORDER BY id;


-- 3. Тарифы (SCD Type 2)
CREATE TABLE IF NOT EXISTS energosbyt.dim_tariffs
(
    id UInt64,
    name String,
    price_day_kwph UInt32,
    price_night_kwph UInt32,
    valid_from DateTime,
    valid_to DateTime,
    created_at DateTime,
    updated_at DateTime
)
    ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY (id, valid_from);


-- 4. Собственники (SCD Type 1 и Type 3)
CREATE TABLE IF NOT EXISTS energosbyt.dim_users
(
    id UInt64,
    fio String,
    phone String,
    phone_prev String,
    created_at DateTime,
    updated_at DateTime
)
    ENGINE = ReplacingMergeTree(updated_at)
    ORDER BY id;

-- FACTS

-- 5. Привязка счётчиков к недвижимости
CREATE TABLE IF NOT EXISTS energosbyt.fact_gauge_bindings
(
    gauge_id UInt64,
    realty_id UInt64,
    created_at DateTime,
    sign Int8,
    version UInt64
)
    ENGINE = VersionedCollapsingMergeTree(sign, version)
    ORDER BY (gauge_id, realty_id);


-- 6. Показания счётчиков
CREATE TABLE IF NOT EXISTS energosbyt.fact_meter_readings
(
    realty_id UInt64,
    user_id UInt64,
    tariff_id UInt64,
    gauge_id UInt64,
    reading_date Date,
    day_kw UInt32,
    night_kw UInt32,
    created_at DateTime
)
    ENGINE = ReplacingMergeTree(created_at)
    PARTITION BY toYYYYMM(reading_date)
    ORDER BY (realty_id, gauge_id, reading_date);


-- 7. Выставленные счета
CREATE TABLE IF NOT EXISTS energosbyt.fact_invoice
(
    realty_id UInt64,
    user_id UInt64,
    tariff_id UInt64,
    gauge_id UInt64,
    day_kw UInt32,
    night_kw UInt32,
    price UInt64,
    deadline Date,
    created_at DateTime
)
    ENGINE = MergeTree()
    PARTITION BY toYYYYMM(created_at)
    ORDER BY (realty_id, deadline, gauge_id, created_at);
