--SCD1 - меняем фамилию пользователя без сохранения старой--
ALTER TABLE energosbyt.dim_users
UPDATE
    fio = 'Соколов Иван'
WHERE id = 1
    SETTINGS mutations_sync = 1;