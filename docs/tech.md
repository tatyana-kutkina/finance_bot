# Техническая документация

## 1. Технологический Стек

### Core (Ядро)
- **Language:** Python (Latest Stable)
- **Runtime:** AsyncIO (асинхронное выполнение для высокой производительности)
- **Configuration:** Pydantic Settings / `.env` (управление секретами и конфигурацией)

### Interface (Telegram)
- **Framework:** `aiogram` 3.x
- **Interaction Mode:** Polling (MVP) -> Webhooks (Production)
- **State Management:** FSM (Finite State Machine) для сценариев диалога
- **Storage:** MemoryStorage (MVP) -> Redis (Production)

### AI & ML (Интеллект)
- **LLM Provider:** OpenAI API или DeepSeek 
  - **NLP (Natural Language Processing):** GPT-4o-mini / GPT-4o (извлечение сущностей из текста)
  - **STT (Speech-to-Text):** Whisper (транскрибация голосовых сообщений)
- **Prompt Engineering:** Системные промпты для строгого форматирования ответов (Structured Output, JSON)

### Data Layer (Данные)
- **Database:**
  - **Dev/MVP:** SQLite (файловая БД, zero-config)
  - **Prod:** PostgreSQL (надежность, масштабируемость)
- **ORM (Object-Relational Mapping):** SQLAlchemy (Async)
- **Migrations:** Alembic (версионирование схемы БД)

---

## 2. Архитектура Приложения

### Компоненты
1.  **Bot Handlers (`/handlers`):**
    - Принимают `Update` от Telegram.
    - Не содержат бизнес-логики.
    - Вызывают сервисы и отправляют отформатированные ответы.
    
2.  **Services (`/services`):**
    - **AIService:** Инкапсулирует логику работы с LLM. Принимает сырой текст/аудио, возвращает структурированные данные (DTO).
    - **FinanceService:** Отвечает за создание записей траты, расчеты, валидацию бизнес-правил.
    
3.  **Database Repositories (`/database`):**
    - Абстракция над ORM. Методы типа `add_transaction`, `get_user_stats`.

---

## 3. Поток Данных (Data Flow)

### Сценарий: Добавление расхода
1.  **Input:** Пользователь отправляет голосовое сообщение "Купил продукты на 5000".
2.  **Handler:** Получает файл голоса.
3.  **AIService (STT):** Отправляет файл в Whisper -> получает текст "Купил продукты на 5000".
4.  **AIService (NLP):** Отправляет текст в GPT с инструкцией извлечь JSON.
    - *Output:* `{"category": "Продукты", "amount": 5000, "currency": "RUB"}`
5.  **FinanceService:**
    - Проверяет корректность данных.
    - Создает запись в БД через Repository.
6.  **Handler:** Формирует ответ "✅ Записано: Продукты - 5000 RUB".

---

## 4. Внешние Интеграции
- **Telegram Bot API:** Основной интерфейс.
- **OpenAI API / DeepSeek API:** Обработка естественного языка и голоса.

