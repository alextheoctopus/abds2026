# Changelog

Все значимые изменения в этом проекте будут документированы в этом файле.

Формат основан на [Keep a Changelog](https://keepachangelog.com/ru/1.0.0/),
и этот проект придерживается [Semantic Versioning](https://semver.org/lang/ru/).

## [v1.0.0] - 2026-10-30

### Добавлено

- CI-воркфлоу `Energosbyt Labs` для автоматической проверки
лабораторных работ (`.github/workflows/energosbyt.lab.yml`)
и скрипт определения номера лабораторной работы из `.labrc` [.github/scripts/lab_number.sh](.github/scripts/lab_number.sh)
- Файл `.gitignore`
- Файл `.labrc` с номером проверяемой лабораторной работы
- Файл `.env.local` с переменными окружения для Docker Compose
- Файл `CODEOWNERS` с назначением владельца кода
- `Makefile` с командами управления сервисами: `run`, `rund`, `services`, `stop`, `clean`
- `CONTRIBUTING.md` с требованиями к структуре проекта, процессу разработки и проверки
- Инструкция по настройке репозитория в `README.md`: защита мастер-ветки, добавление коллабораторов
