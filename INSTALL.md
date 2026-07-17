# Установка и запуск Birthday Bot

## Требования

- Python 3.9+
- Аккаунт Discord с правами на создание приложений

---

## 1. Создать Discord-бота

1. Открыть [discord.com/developers/applications](https://discord.com/developers/applications)
2. **New Application** → ввести название → **Create**
3. Перейти в раздел **Bot**
4. Нажать **Reset Token** → скопировать токен (показывается один раз)
5. Включить интенты:
   - `Server Members Intent` ✅
   - `Message Content Intent` ✅
6. Нажать **Save Changes**

---

## 2. Скачать и настроить проект

```bash
# Клонировать репозиторий
git clone <url>
cd birthday-master
```

---

## 3. Создать виртуальное окружение

**Windows:**
```powershell
py -3 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Создать файл .env

Скопировать шаблон и вставить токен:

**Windows:**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

Открыть `.env` и заменить `your_token_here` на реальный токен:
```
DISCORD_TOKEN=твой_токен_здесь
```

---

## 5. Пригласить бота на сервер

1. В Developer Portal → **OAuth2 → URL Generator**
2. Выбрать **Scopes:** `bot` + `applications.commands`
3. Выбрать **Bot Permissions:**
   - `View Channels`
   - `Send Messages`
   - `Embed Links`
   - `Attach Files`
   - `Mention Everyone` — без этого права поздравление с `@everyone` не
     будет реально пинговать участников, Discord покажет его как обычный
     текст
4. Скопировать ссылку внизу → открыть в браузере → выбрать сервер

Если бот уже приглашён на сервер без этого права, добавить его можно и
без переприглашения: **Настройки сервера → Роли** → найти роль бота →
включить `Упоминание @everyone, @here и всех ролей`.

---

## 6. Запустить бота

**Windows:**
```powershell
.\.venv\Scripts\python.exe bot.py
```

**Linux / macOS:**
```bash
.venv/bin/python bot.py
```

Успешный запуск:
```
✅ Бот YourBot#1234 успешно подключен к Discord!
```

---

## 7. Первоначальная настройка (в Discord)

| Команда | Описание |
|---|---|
| `/config channel #канал` | Канал для поздравлений |
| `/config timezone Europe/Moscow` | Часовой пояс сервера |
| `/birthday test` | Проверить генерацию открытки |

---

## Структура папок

```
birthday-master/
├── bot.py              # Основной файл бота
├── fonts/              # TTF-шрифты для открыток
├── images/             # Фоновое изображение
│   └── birthday_bg.png
├── data/               # База данных (создаётся автоматически)
│   └── data.json
├── tests/              # Тесты
├── .env                # Токен (не коммитить!)
├── .env.example        # Шаблон .env
├── requirements.txt    # Зависимости
└── requirements-dev.txt # Зависимости для разработки
```

---

## Запуск тестов

```powershell
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\pytest tests/ -v
```

---

## Частые проблемы

**Слэш-команды не появляются в Discord**
Синхронизация занимает до 1 часа. Можно перезапустить бота.

**`❌ ОШИБКА: Токен не найден`**
Убедись, что файл `.env` создан и токен в нём корректный.

**`❌ Файл не найден в папке fonts/`**
Команда `/config font` принимает только имя файла без пути, например: `Orbitron-Bold`.

**Бот не поздравляет в нужное время**
Поздравления отправляются ровно в **06:00 по часовому поясу пользователя**.
Убедись, что таймзона настроена: `/birthday timezone Europe/Moscow`.
