# Keitaro wrapper (тестовое задание)

Обёртка над [Keitaro Admin API v1](https://admin-api.docs.keitaro.io/) из двух частей:

1. **Создаватор кампаний.** Принимает название, гео и оффер. Создаёт кампанию с доменом, группой и источником, а в ней два потока:
   - **#1** ловит посетителей из указанных стран (фильтр `country`) и редиректит на Google;
   - **#2** («запасной», `type=default`) отправляет всех остальных на выбранный оффер (100%).

   Название получает префикс из `CAMPAIGN_PREFIX`: `campaign1` → `test_chalimov_campaign1`.
2. **Редактор существующей кампании** повторяет логику обёртки из видео:
   - **Fetch streams from KT** забирает потоки. Потоки без офферов показываются только заголовком, их содержимое не разбирается.
   - **Add / Remove / Bring back** меняют только локальный черновик. Веса пересчитываются поровну с суммой ровно 100 (3 оффера → 34/33/33), поток подсвечивается жёлтым как неопубликованный.
   - **Push to KT** отправляет черновик в Keitaro. **Cancel** откатывает его: добавленные, но не опубликованные привязки удаляются, остальные возвращаются к опубликованному состоянию.
   - **Remove** не удаляет оффер насовсем. Он становится серым, получает 0%, в Keitaro не отправляется, и его можно вернуть кнопкой **Bring back**.
   - Если оффер удалили прямо в Keitaro, при следующем Fetch он переходит в `removed` (серый) и тоже возвращается через Bring back.
   - **Pin** (📌) закрепляет вес: при пересчётах он не меняется, а остаток до 100% делится между незакреплёнными. Пример: закреплено 25%, остаётся 75% → 38/37. Клик по проценту позволяет задать вес вручную, и он сразу закрепляется.
   - Push не пропустит поток, у которого сумма активных весов не равна 100%.

**Стек:** FastAPI, SQLAlchemy 2.0, Alembic, httpx; фронт на React, Vite и TypeScript. Есть mock-режим, в котором всё работает без API-ключа.

## Структура

```
backend/
  app/
    main.py              – FastAPI-приложение, обработка ошибок, раздача собранного фронта
    api.py               – HTTP-эндпоинты /api/*
    config.py            – настройки из .env (pydantic-settings)
    db.py, models.py     – SQLAlchemy: engine, сессии, модели
    keitaro/             – клиент Keitaro: http_client.py (реальный), mock_client.py (в памяти)
    services/
      campaign_builder.py – создаватор кампаний
      editor.py           – редактор офферов: черновик, push, cancel, pin
      naming.py           – префикс, разбор гео, равномерное распределение весов
      offers.py           – кэш офферов для автокомплита
  alembic/               – миграции
  tests/                 – pytest
frontend/                – React SPA
.env.example             – шаблон настроек
```

### Что хранится в базе

| Таблица         | Назначение                                                                   |
|-----------------|------------------------------------------------------------------------------|
| `campaigns`     | Локальная копия кампаний Keitaro, плюс гео и оффер для созданных через создаватор |
| `streams`       | Потоки кампаний (`has_offers` показывает, редактируется ли поток)             |
| `stream_offers` | Привязки офферов к потокам: черновик (`status`, `share`, `pinned`) и опубликованное состояние (`published_status`, `published_share`) |
| `offer_cache`   | Кэш справочника офферов для автокомплита (TTL задаётся в `.env`)              |
| `audit_log`     | Журнал действий: create, fetch, add, remove, restore, pin, push, cancel       |

Поток считается неопубликованным («жёлтым»), если черновик хотя бы одной привязки отличается от опубликованного состояния.

## Быстрый старт

Нужны Python 3.11+ (проверено на 3.13) и Node.js 18+.

### 1. Настройки

```bash
cp .env.example .env
```

Все настройки берутся только из `.env`, в коде нет значений по умолчанию для бизнес-параметров. Обязательные параметры: `KEITARO_MOCK`, `CAMPAIGN_PREFIX`, `GEO_REDIRECT_URL`, а при `KEITARO_MOCK=false` ещё `KEITARO_URL` и `KEITARO_API_KEY`. Если чего-то не хватает, приложение не стартует и называет, что нужно задать. Значения по умолчанию есть только у технических параметров (таймаут, путь к SQLite, TTL кэша), они указаны в `.env.example`.

В `.env.example` стоит `KEITARO_MOCK=true`: вместо трекера используется фейковый Keitaro в памяти с тестовыми доменами, группами, источниками, двадцатью офферами и демо-кампанией `<CAMPAIGN_PREFIX>demo` (например, `test_chalimov_demo`).

Чтобы работать с настоящим трекером:

```dotenv
KEITARO_URL=https://your-tracker.example.com
KEITARO_API_KEY=<ключ из Keitaro → Maintenance → Users → API keys>
KEITARO_MOCK=false
# необязательно: значения по умолчанию в форме (id из GET /domains и GET /groups?type=campaigns)
DEFAULT_DOMAIN_ID=
DEFAULT_GROUP_ID=
DEFAULT_TRAFFIC_SOURCE_ID=
```

При переключении между mock и настоящим трекером пересоздайте локальную базу: удалите `backend/app.db` и выполните `alembic upgrade head`, иначе в истории останутся кампании из mock.

### 2. Бэкенд

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
alembic upgrade head            # создать или обновить схему базы
uvicorn app.main:app --reload --port 8000
```

Swagger доступен по адресу http://localhost:8000/docs.

### 3. Фронтенд

Режим разработки с hot reload; Vite проксирует `/api` на `:8000`:

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

Или одним процессом: собрать фронт, и FastAPI сам будет его раздавать:

```bash
cd frontend && npm install && npm run build
# затем открыть http://localhost:8000
```

## Миграции (Alembic)

Все команды выполняются из папки `backend/` с активированным venv. Адрес базы берётся из `DATABASE_URL` в `.env`; если он пустой, используется SQLite `backend/app.db`.

| Действие                                  | Команда                                            |
|-------------------------------------------|----------------------------------------------------|
| Применить все миграции                    | `alembic upgrade head`                             |
| Создать миграцию после изменения моделей  | `alembic revision --autogenerate -m "описание"`    |
| Откатить последнюю миграцию               | `alembic downgrade -1`                             |
| Текущая версия базы                       | `alembic current`                                  |
| История миграций                          | `alembic history`                                  |

Порядок работы со схемой:
1. Поменять модели в `app/models.py`.
2. Выполнить `alembic revision --autogenerate -m "..."`.
3. Проверить сгенерированный файл в `alembic/versions/`.
4. Выполнить `alembic upgrade head`.

Для SQLite включён batch-режим (`render_as_batch`), поэтому `ALTER` колонок тоже работает.

Чтобы перейти на PostgreSQL, нужно поставить драйвер (`pip install "psycopg[binary]"`), указать `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db` и выполнить `alembic upgrade head`.

## Тесты

```bash
cd backend
pytest
```

Тесты используют mock-клиент и SQLite в памяти. Покрыты:
- префикс, разбор гео и распределение весов;
- создание кампании: параметры кампании, оба потока, откат при ошибке;
- сценарии редактора из видео: add → 25×4 → push, cancel, remove → bring back, оффер удалён в Keitaro → removed после fetch, pin (38/37/25), проверка суммы 100% при push.

## API

| Метод | Путь                                               | Что делает                                  |
|-------|----------------------------------------------------|---------------------------------------------|
| GET   | `/api/dictionaries`                                | Домены, группы, источники, префикс, mock-режим |
| GET   | `/api/offers?q=`                                   | Автокомплит офферов (по названию или ID)    |
| POST  | `/api/offers/sync`                                 | Принудительно обновить кэш офферов          |
| POST  | `/api/campaigns`                                   | Создать кампанию: `{name, geo, offer_id, domain_id?, group_id?, traffic_source_id?}` |
| GET   | `/api/campaigns/created`                           | Кампании, созданные через создаватор        |
| GET   | `/api/campaigns?q=&only_mine=true`                 | Кампании из Keitaro (по умолчанию только с префиксом) |
| GET   | `/api/campaigns/{id}/streams`                      | Потоки и офферы (при первом открытии делает fetch) |
| POST  | `/api/campaigns/{id}/fetch`                        | Fetch streams from KT                       |
| POST  | `/api/streams/{id}/offers`                         | Добавить оффер `{offer_id}`                 |
| POST  | `/api/streams/{id}/offers/{offer_id}/remove`       | Remove                                      |
| POST  | `/api/streams/{id}/offers/{offer_id}/restore`      | Bring back                                  |
| POST  | `/api/streams/{id}/offers/{offer_id}/pin`          | Закрепить или открепить вес `{pinned, share?}` |
| POST  | `/api/streams/{id}/push`                           | Push to KT                                  |
| POST  | `/api/streams/{id}/cancel`                         | Cancel                                      |
| GET   | `/api/campaigns/{id}/log`                          | Журнал действий                             |
| POST  | `/api/mock/streams/{id}/offers/{offer_id}/delete`  | Только mock: имитирует удаление оффера прямо в Keitaro |

### Какие запросы уходят в Keitaro

| Действие                 | Запрос Keitaro Admin API                                         |
|--------------------------|------------------------------------------------------------------|
| Справочники              | `GET /domains`, `GET /groups?type=campaigns`, `GET /traffic_sources`, `GET /offers` |
| Создание кампании        | `POST /campaigns` (`alias` генерируется из имени, `type=position`, `cost_type=CPC`, `cost_auto=true`, `domain_id`, `group_id`, `traffic_source_id`) |
| Поток #1                 | `POST /streams`: `type=regular`, `schema=redirect`, `action_type=http`, `action_payload=GEO_REDIRECT_URL`, `filters=[{name: country, mode: accept, payload: [...]}]` |
| Поток #2                 | `POST /streams`: `type=default`, `schema=landings`, `offers=[{offer_id, share: 100, state: active}]` |
| Откат при ошибке         | `DELETE /campaigns/{id}` (переносит кампанию в архив)            |
| Fetch                    | `GET /campaigns/{id}`, `GET /campaigns/{id}/streams`             |
| Push                     | `PUT /streams/{id}` с `offers=[{offer_id, share, state}]`        |

## Как проверить сценарии из видео в mock-режиме

1. Открыть **Редактор кампаний** → `<CAMPAIGN_PREFIX>demo`.
2. **Add** → четыре оффера по 25%, поток жёлтый. **Cancel** → снова три оффера: 34/33/33.
3. **Remove** у оффера → он серый, 0%, остальные 50/50. **Push to KT** → в колонке «Keitaro» видно состояние трекера.
4. Удалить оффер «в Keitaro», минуя обёртку:
   ```bash
   curl -X POST http://localhost:8000/api/mock/streams/1002/offers/2/delete
   ```
   После **Fetch streams from KT** оффер станет `removed`, его можно вернуть кнопкой **Bring back**.
5. Нажать 📌 у оффера с 25%, затем Remove или Bring back у другого: закреплённые 25% сохраняются, остальные веса пересчитываются.

## Ограничения и заметки

- Mock-Keitaro хранит данные в памяти и сбрасывается при перезапуске сервера, а локальная база остаётся. После перезапуска в mock-режиме лучше удалить `backend/app.db` и снова выполнить `alembic upgrade head`.
- Fetch считает Keitaro источником истины: неопубликованные черновики потока при Fetch сбрасываются.
- Закрепление веса — локальное свойство обёртки, в Keitaro уходят только итоговые `share`.
- Всё проверено на живом трекере: создание кампании, оба потока, Fetch, Remove → Push (оффер убирается из потока в KT), Bring back → Push, откат через `DELETE /campaigns/{id}`, понятные ошибки на несуществующий оффер.
- Keitaro требует `alias` при создании кампании (в документации поле необязательное). Обёртка генерирует его сама: `test_chalimov_x` → `test-chalimov-x-3f9a1c`.
- **Источник трафика.** Если у API-ключа нет прав на источники трафика (Keitaro отдаёт пустой список, а на запись отвечает 403), кампания создаётся без источника, и форма об этом предупреждает. Когда источники доступны, поле обязательно. ID можно задать вручную в `DEFAULT_TRAFFIC_SOURCE_ID`.
- На несуществующие id перед Keitaro отвечает nginx HTML-страницей 404. Клиент превращает её в понятное сообщение.
- `GET /campaigns` у настоящего трекера отвечает несколько секунд, на это время в списке показывается «Загрузка из Keitaro…».
