# chat-agent-cli

Минимальный CLI-агент на Python с сохранением контекста между запусками.

## Что делает

- запускает диалог с LLM в терминале;
- выводит ответ модели потоково (по мере генерации);
- хранит историю сессий в SQLite;
- позволяет продолжать прошлые сессии по списку или по `session_id`.

## Требования

- Python 3.11+

## Переменные окружения

- `OPENAI_API_KEY` - API ключ (обязательно)
- `OPENAI_BASE_URL` - базовый URL API (опционально)
- `OPENAI_MODEL` - модель (по умолчанию `gpt-4.1-mini`)
- `CHAT_MODELS_PATH` - путь к TOML-файлу с профилями моделей (по умолчанию `~/.chat-agent/models.toml`)
- `CHAT_DEFAULT_MODEL` - alias профиля по умолчанию из `CHAT_MODELS_PATH` (опционально)
- `SYSTEM_PROMPT` - системный промпт (опционально)
- `CHAT_STORAGE_PATH` - путь к SQLite БД (по умолчанию `~/.chat-agent/history.db`)
- `CHAT_USER_PROFILE_PATH` - путь к JSON-профилю пользователя (по умолчанию `~/.chat-agent/user_profile.json`)
- `MODEL_CONTEXT_LIMIT` - лимит контекста модели для предупреждений и demo (по умолчанию `128000`)
- `INPUT_COST_PER_1M` - цена входных токенов за 1M токенов (по умолчанию `0`)
- `OUTPUT_COST_PER_1M` - цена выходных токенов за 1M токенов (по умолчанию `0`)

## Профили моделей

Если нужен быстрый fallback, можно по-прежнему использовать один набор `OPENAI_*` переменных.

Если нужно переключаться между локальной и удалённой моделями, создайте `~/.chat-agent/models.toml`:

```toml
default_model = "remote"

[models.remote]
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"
model = "gpt-4.1-mini"
context_limit = 128000
input_cost_per_1m = 0.40
output_cost_per_1m = 1.60

[models.local]
api_key = "ollama"
base_url = "http://localhost:11434/v1"
model = "qwen2.5:14b-instruct"
context_limit = 32768
input_cost_per_1m = 0
output_cost_per_1m = 0
```

Поддерживаются поля:

- `api_key` - ключ прямо в профиле
- `api_key_env` - имя env-переменной, из которой брать ключ
- `base_url` - URL API для профиля
- `model` - имя модели
- `context_limit` - лимит контекста
- `input_cost_per_1m`, `output_cost_per_1m` - цены токенов

## Команды агента

- `chat-agent chat` - начать новую сессию
- `chat-agent chat --model local` - начать новую сессию на выбранном профиле модели
- `chat-agent resume` - показать сессии и выбрать, какую продолжить
- `chat-agent resume --id <session_id>` - продолжить конкретную сессию
- `chat-agent resume --id <session_id> --model remote` - продолжить сессию и переключить её на другой профиль
- `chat-agent sessions` - показать список сохраненных сессий
- `chat-agent profile-show` - показать активный профиль пользователя
- `chat-agent profile-set style.verbosity short` - обновить одно поле профиля пользователя
- `chat-agent token-demo` - сравнить короткий/длинный/переполненный диалоги по токенам и стоимости

### Стратегия контекста при создании сессии

- `chat-agent chat --context sliding --window-messages 6` - sliding window, в запрос идут только последние `N` несистемных сообщений
- `chat-agent chat --context facts --window-messages 6` - key-value memory, в запрос идут `facts` + последние `N` сообщений
- `chat-agent chat --context memory --window-messages 6` - memory layers: short-term + working memory + long-term memory
- `chat-agent chat --context branching` - ветвящийся диалог с checkpoint и независимыми ветками
- `chat-agent chat --context full` - legacy-режим без сжатия истории
- `chat-agent chat --context sum --summary-after-user-messages 5` - legacy-режим со summary-чанками
- стратегия сохраняется в сессии при создании и не меняется при `resume`

## Команды внутри чата

- `/exit` - завершить сессию
- `/clear` - очистить историю текущей сессии
- `/debug` - включить/выключить вывод токенов после каждого ответа модели
- `/stats` - показать все токены и биллинг-токены по всей истории текущего чата
- `/summary` - показать текущее накопленное summary (чанки сжатой истории)
- `/compact` - вручную пересобрать summary всей истории через LLM (перезаписывает старые summary)
- `/model` - показать текущую модель и открыть интерактивный выбор профиля
- `/model <alias>` - переключить текущую сессию на другой профиль модели
- `/memory` - показать short-term / working / long-term memory (`context=memory`)
- `/checkpoint <name>` - сохранить checkpoint текущей ветки (`context=branching`)
- `/branch <checkpoint> <new-branch>` - создать новую ветку от checkpoint (`context=branching`)
- `/branches` - показать список веток и активную ветку (`context=branching`)
- `/switch <branch-name>` - переключиться на другую ветку (`context=branching`)

Выбранный профиль модели сохраняется в сессии. При обычном `resume` чат продолжится на той же модели, а `--model` и `/model` меняют это значение.

## Профиль пользователя

Агент поддерживает глобальный профиль пользователя, который автоматически добавляется в каждый запрос к модели как отдельный system-блок.

Пример `~/.chat-agent/user_profile.json`:

```json
{
  "user_id": "default",
  "name": "Алексей",
  "preferences": {
    "style": {
      "tone": "neutral",
      "verbosity": "short",
      "explanation_level": "practical"
    },
    "format": {
      "prefer_bullets": true,
      "prefer_examples": true
    },
    "constraints": {
      "answer_language": "ru",
      "no_emojis": true,
      "max_paragraphs": 3
    }
  }
}
```

Как это работает:

- профиль хранится отдельно от истории чата;
- при каждом запросе он автоматически подмешивается в контекст;
- если пользователь в текущем сообщении явно просит другой стиль, это важнее профиля.

Быстрая настройка:

```bash
chat-agent profile-set name Алексей
chat-agent profile-set style.verbosity short
chat-agent profile-set format.prefer_bullets true
chat-agent profile-set constraints.answer_language ru
chat-agent profile-show
```

## Явная модель памяти

Для `context=memory` агент разделяет контекст на 3 слоя:

- `short-term` - только последние `N` несистемных сообщений текущего диалога
- `working memory` - данные текущей задачи: цель, ограничения, дедлайны, статус, текущие технические параметры
- `long-term memory` - более стабильные данные: профиль, предпочтения, знания, принятые решения

Как выбирается слой:

- по умолчанию слой определяется явно в коде через routing-правила по ключу
- при необходимости слой можно форсировать в сообщении пользователя:
  - `working: owner=task captain Olga`
  - `long: constraint=always keep audit trail`

Хранение разделено:

- short-term хранится в истории сообщений
- working memory хранится в отдельной таблице `session_working_memory`
- long-term memory хранится в отдельной таблице `session_long_term_memory`

## Сравнение стратегий

Автоматический сценарий лежит в `tests/test_context_strategies.py`: один и тот же диалог на 9 user-сообщений гоняется через `sliding`, `facts` и `branching`, затем сравниваются качество ответа, устойчивость к потере ранних деталей и расход входных токенов.

Итог сценария:
- `sliding` даёт минимальный расход токенов, но теряет ранние факты за пределами окна
- `facts` сохраняет ранние договорённости и ограничения заметно стабильнее, при умеренном росте токенов
- `branching` даёт такое же качество памяти, как полный контекст активной ветки, но расходует больше токенов; взамен позволяет безопасно разводить альтернативные продолжения диалога

Практический вывод:
- если важна экономия, берите `sliding`
- если нужен баланс памяти и стоимости, берите `facts`
- если нужно сравнивать альтернативы и переключаться между ними, берите `branching`

## Проверка memory layers

Сценарий для явной модели памяти лежит в `tests/test_memory_layers.py`.

Что проверяется:

- какие данные попадают в `working memory` и `long-term memory`
- что ранние важные детали исчезают из `short-term`, но остаются в правильном memory layer
- что в одном и том же сценарии `context=memory` отвечает стабильнее, чем `context=sliding`

Итог сценария:

- `memory` сохраняет ранние цель, ограничения, предпочтения и решения даже после выхода этих сообщений из короткого окна
- `sliding` дешевле по токенам, но быстрее теряет важные детали
- `memory` расходует больше входных токенов из-за двух системных блоков памяти, но заметно устойчивее на длинном ТЗ-сценарии

## Live-тест на реальной модели

Тест, который реально отправляет сообщения в LLM и сравнивает `full` vs `sum`:

```bash
OPENAI_API_KEY=... .venv/bin/pytest -q tests/test_context_compression_live.py --live-model-tests
```

Что делает тест:
- поднимает 2 сессии (`full` и `sum` c `summary_trigger_user_messages=3`) и гоняет их параллельно;
- отправляет 7 сообщений, затем для `sum` выполняет ручной `compact`, после этого задаёт контрольный вопрос на память;
- проверяет, что обе сессии помнят кодовое слово и что у `sum` меньше `billed_input_tokens`;
- проверяет, что после `compact` в `sum` остаётся один summary.

Артефакты после прогона:
- `.chat/live_context_full.db`
- `.chat/live_context_sum.db`
- `.chat/live_context_compare_sessions.txt`
