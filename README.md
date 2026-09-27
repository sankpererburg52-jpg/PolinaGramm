# PolinaGram

Мессенджер в стиле Telegram: Python-бэкенд (FastAPI + WebSocket) + Android-клиент на Kivy.

## Состав проекта

```
server/    — API: авторизация по коду из SMS, чаты, сообщения, realtime через WebSocket
mobile/    — Android-приложение (Kivy) + buildozer.spec для сборки APK
.github/   — GitHub Actions: сборка APK автоматически при пуше
```

## 1. Запуск сервера

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # поменяйте JWT_SECRET!
uvicorn main:app --host 0.0.0.0 --port 8000
```

Документация API будет на `http://localhost:8000/docs`. В dev-режиме
код подтверждения возвращается прямо в ответе `/auth/request-code`.

## 2. Сборка APK

Вариант A — облако (проще всего):
1. Создайте репозиторий на GitHub и залейте этот проект.
2. В `mobile/main.py` укажите адрес сервера в переменной `SERVER`.
3. Откройте вкладку Actions → запустится сборка → скачайте artifact `PolinaGram-apk`.

Вариант B — локально (нужны Linux, Python, Java 17, Docker для buildozer):

```bash
cd mobile
pip install buildozer cython
buildozer -v android debug        # APK появится в mobile/bin/
buildozer android deploy run      # установить на подключённый телефон
```

## 3. Подпись релизного APK (обязательно для публикации)

Debug-APK годится для тестов, но Google Play и «серьёзная» установка требуют подпись:

```bash
keytool -genkey -v -keystore release.keystore -alias polinagram \
        -keyalg RSA -keysize 2048 -validity 10000
```

Раскомментируйте `android.keystore` в `mobile/buildozer.spec`, положите keystore
в `mobile/`, затем `buildozer android release`. Храните keystore и пароли в секретах
GitHub (`KEYSTORE_BASE64` и т.п.) и добавьте их в workflow для release-сборки.

## 4. Чек-лист для публичного запуска на 1000+ пользователей

- **База данных**: переключите `DATABASE_URL` на PostgreSQL (asyncpg уже в requirements).
- **HTTPS/WSS**: поставьте nginx + certbot перед uvicorn; в приложении — `https://`/`wss://`.
- **Несколько воркеров**: in-memory менеджер WebSocket работает в одном процессе.
  Для нескольких воркеров замените broadcast на Redis pub/sub (комментарий в `server/ws.py`).
- **SMS**: поставьте `DEV_RETURN_CODE=false` и подключите SMS-шлюз в `/auth/request-code`.
- **Push-уведомления**: для Kivy это отдельная интеграция через pyjnius/FCM —
  самое сложное место стека. Если пуши критичны на старте, рассмотрите Flutter-клиент
  поверх того же API.
- **Нагрузка**: 1000 пользователей — это мало; один сервер за 10–20 $/мес с uvicorn
  спокойно выдержит. Начните с 1 воркера, включите `pool_pre_ping` (уже есть).
- **Бэкапы**: ежедневный `pg_dump` + выгрузка на отдельное хранилище.
- **Юридика**: не копируйте название/логотип/иконки Telegram — функции копировать
  можно, чужой брендинг нельзя. Для Play Market нужна политика конфиденциальности
  и аккаунт разработчика (25 $ разово).

## 5. Ограничения текущей версии

Реализовано: регистрация по коду, поиск пользователей, личные чаты, история,
непрочитанные, realtime-доставка по WebSocket, отметки прочтения.
Не реализовано (следующие итерации): группы/каналы, медиа и голосовые,
E2E-шифрование, редактирование/удаление сообщений, push, звонки.
