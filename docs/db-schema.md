## Схема базы данных

База данных хранит пользователей и их финансовые операции. В разработке используется SQLite, в продакшене планируется PostgreSQL (ORM — SQLAlchemy Async).

### Таблица `users`
- `id` — PK, автоинкремент.
- `telegram_id` — `BigInteger`, уникальный, индексируется.
- `registered_at` — `DateTime(timezone=True)`, `server_default=now()`, не null.
- `settings` — `JSON`, опционально, хранит пользовательские настройки.
- Связь: `transactions` (one-to-many), каскадное удаление `all, delete-orphan` на стороне ORM.

### Таблица `transactions`
- `id` — PK, автоинкремент.
- `user_id` — FK на `users.id`, `ondelete=CASCADE`, индексируется.
- `amount` — `Numeric(12, 2)`, не null, сумма операции.
- `category` — `String(100)`, не null, определенная категоризация траты.
- `raw_text` — `Text`, опционально, оригинальное сообщение пользователя.
- `date` — `Date`, `server_default=current_date`, не null, дата совершения траты.
- `created_at` — `DateTime(timezone=True)`, `server_default=now()`, не null, момент сохранения записи.
- Связь: `user` (many-to-one), обеспечивает доступ к владельцу операции.

### Индексация и ограничения
- Индексы: `users.telegram_id`, `transactions.user_id`.
- Уникальность: `users.telegram_id` предотвращает дублирование учетных записей.
- Каскадное удаление: удаление пользователя приводит к удалению его транзакций.
