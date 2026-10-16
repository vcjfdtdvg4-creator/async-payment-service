# Async Payment Processing Service

Микросервис асинхронной обработки платежей: FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL + RabbitMQ (FastStream) + Alembic.

## Запуск

```bash
cp .env.example .env        # уже скопирован; поменяйте API_KEY при желании
docker compose up --build
```

- API: http://localhost:8000 (Swagger: `/docs`)
- RabbitMQ UI: http://localhost:15672 (guest / guest)
- Миграции применяются автоматически при старте `api`; `consumer` стартует после того, как `api` стал healthy.

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
              outbox relay (фон. задача в api, SKIP LOCKED, publisher confirms)
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

```
app/
  api.py        эндпоинты
  main.py       FastAPI + запуск outbox relay
  outbox.py     outbox relay
  messaging.py  exchange, очереди, retry/DLQ-топология
  consumer.py   FastStream consumer
  webhook.py    отправка webhook
  models.py / schemas.py / db.py / config.py / security.py
alembic/versions/0001_init.py   таблицы payments и outbox
```

## Замечания

- Webhook-получатель должен быть идемпотентен (по `payment_id`): доставка at-least-once.
- Изменение `MAX_ATTEMPTS` / `RETRY_BASE_DELAY_SECONDS` меняет аргументы retry-очередей; RabbitMQ не даёт переобъявить очередь
  с другими аргументами — удалите старые очереди (`docker compose down -v`) или используйте новые имена.
- Relay запущен внутри процесса `api` (по условию в compose только 4 сервиса); благодаря `SKIP LOCKED` можно масштабировать api горизонтально
  или вынести relay в отдельный процесс.
- В `.env` по умолчанию тестовый ключ — замените его в реальном окружении.
