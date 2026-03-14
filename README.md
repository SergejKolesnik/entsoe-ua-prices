# entsoe-ua-prices

Python-інструмент для автоматичного отримання цін на ринку «на добу наперед» (DAM) з платформи ENTSO-E для торгової зони України (UA-IPS).

## Основні можливості
* Отримання актуальних цін через REST API ENTSO-E.
* Конвертація XML-відповідей у зручні формати (JSON/Pandas DataFrame).
* Обробка часових поясів (з UTC у локальний час України).

## Швидкий старт
1. Отримайте `securityToken` на [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/).
2. Скопіюйте `.env.example` у `.env` та впишіть свій токен.
3. Запустіть `main.py`.
