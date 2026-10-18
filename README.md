# Async Payment Processing Service

Микросервис асинхронной обработки платежей: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + RabbitMQ (FastStream) + Alembic.

## Запуск

```bash
cp .env.example .env        # уже скопирован; поменяйте API_KEY при желании
docker compose up --build
```

- API: http://localhost:8000 (Swagger: `/docs`)
- RabbitMQ UI: http://localhost:15672 (guest / guest)
- Админка: http://localhost:8000/ui/ (вход по `API_KEY`)
- Сервисы: `migrate` (alembic upgrade head, разовый) → `api`, `relay`, `consumer` стартуют после успешных миграций.

## Примеры

Для запроса webhook можно взять https://webhook.site или поднять локальный приёмник:
`python -m http.server 9000` (вернёт 501 на POST — удобно проверить retry/DLQ) или любой свой эндпоинт.
Из контейнеров хост доступен как `host.docker.internal` (на Linux добавьте `extra_hosts: ["host.docker.internal:host-gateway"]`).

```bash
curl -i -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: super-secret-key" \
  -H "Idempotency-Key: order-1001" \
  -H "Content-Type: application/json" \
  -d '{
        "amount": "1500.00",
        "currency": "RUB",
        "description": "Order #1001",
        "metadata": {"order_id": 1001},
        "webhook_url": "https://webhook.site/<your-uuid>"
      }'
# 202 Accepted: {"payment_id":"...","status":"pending","created_at":"..."}

curl -s http://localhost:8000/api/v1/payments/<payment_id> -H "X-API-Key: super-secret-key"
```

Повтор запроса с тем же `Idempotency-Key` и тем же телом вернёт тот же `payment_id` (новый платёж не создаётся).
Тот же ключ с другим телом → `409 Conflict`. Без ключа → `422`, без/с неверным `X-API-Key` → `401`.

## Архитектура

```
POST /payments ──► [payments + outbox в одной транзакции] ──► PostgreSQL
                                   │
              outbox relay (отдельный сервис, SKIP LOCKED, publisher confirms)
                                   ▼
        exchange "payments" ──payments.new──► queue payments.new ──► consumer
                                                   │ ошибка
                      ┌────────────────────────────┴───────────────┐
         attempt < 3: payments.new.retry.N                  attempt = 3: payments.dlq
         (TTL 5s, 10s; по TTL → обратно в exchange)
```

**Outbox.** Платёж и событие пишутся в одной транзакции, поэтому «платёж создан, но событие потеряно» невозможно.
Relay читает `outbox WHERE published_at IS NULL ... FOR UPDATE SKIP LOCKED`, публикует с подтверждением брокера и только потом
ставит `published_at`. Гарантия — at-least-once (при падении между publish и commit событие уйдёт повторно), поэтому consumer идемпотентен.

**Идемпотентность.** `UNIQUE(idempotency_key)` + проверка до вставки + обработка `IntegrityError` при гонке одинаковых запросов.
Consumer: статус меняется условным `UPDATE ... WHERE status='pending'`; уже обработанный платёж не пересчитывается;
webhook повторно не отправляется, если выставлен `webhook_delivered_at`.

**Consumer** (один обработчик): читает `payments.new` → эмулирует шлюз (2–5 с, 90 % `succeeded` / 10 % `failed`) →
обновляет статус и `processed_at` → шлёт webhook (`POST`, JSON, 2xx = успех).

**Retry.** Всего 3 попытки (`MAX_ATTEMPTS`). Любая ошибка (в т.ч. недоступный webhook / не-2xx) → сообщение уходит в
`payments.new.retry.<n>` с TTL `5s * 2^(n-1)` (5 с, 10 с) и по истечении возвращается в основную очередь.
Номер попытки хранится в заголовке `x-attempt`. На повторе статус не пересчитывается — повторяется только недоставленный webhook.
Отдельная retry-очередь на каждую задержку исключает head-of-line blocking, свойственный per-message TTL.

**DLQ.** После 3-й неудачной попытки сообщение публикуется в `payments.dlq` с заголовком `x-last-error`.
Кроме того, основная очередь имеет dead-letter-exchange на `payments.dlq`, так что отклонённые (невалидные/не-десериализуемые)
сообщения тоже попадают в DLQ, а не теряются и не зацикливаются.

## Структура

Слоистая архитектура: зависимости направлены внутрь, `domain` ничего не знает о FastAPI, SQLAlchemy и RabbitMQ.

```
app/
  config.py                      настройки (pydantic-settings, .env)
  domain/                        бизнес-модель, без внешних зависимостей
    payments/                    entity (Payment), values (Currency, Status), events, exceptions
    ports/                       протоколы: UnitOfWork, PaymentRepository, PaymentGateway, PaymentNotifier, Clock
  application/                   сценарии (use cases)
    payments/                    create_payment (идемпотентность, 409), get_payment, process_payment
    admin/                       список/статистика платежей, детали + outbox, управление очередями, порты read-моделей
  infrastructure/                реализации портов
    db/                          engine/session, ORM-модели payments и outbox
    repositories/ mappers/ uow.py    SQLAlchemy-репозитории, ORM <-> entity, Unit of Work (+ запись событий в outbox)
    outbox/                      сериализация событий и relay
    broker/                      подключение, топология (exchange, retry-очереди, DLQ), retry-публикация, publisher для requeue
    gateway/emulator.py          эмуляция платёжного шлюза
    webhooks/                    payload и HTTP-отправка webhook
    rabbitmq_management/         клиент Management API для админки
  presentation/
    api/                         JSON API: routers, schemas, presenters, deps (auth, use cases), errors
    consumer/                    обработчик payments.new, схема сообщения, зависимости
    ui/                          админка: routers (auth, dashboard, payments, outbox, queues), templates, static
  entrypoints/                   точки входа процессов
    api.py                       uvicorn app.entrypoints.api:app
    relay.py                     faststream run app.entrypoints.relay:app
    consumer.py                  faststream run app.entrypoints.consumer:app
migrations/                      alembic (0001: таблицы payments и outbox)
tests/                           unit-тесты домена и use cases, тесты API и consumer (без БД и брокера)
```

## Разработка и тесты

Зависимости описаны в `pyproject.toml` и зафиксированы в `uv.lock` ([uv](https://docs.astral.sh/uv/)).

```bash
uv sync           # создаст .venv с зависимостями, включая dev
uv run pytest     # тесты не требуют PostgreSQL и RabbitMQ
```
