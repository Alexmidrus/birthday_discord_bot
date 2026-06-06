# 🎂 Discord Birthday Bot / Бот для поздравлений с днем рождения

---

### 📖 Description

A highly customizable Discord bot that automatically congratulates server members on their birthdays. It generates unique, high-quality greeting cards with the user's avatar, custom background, and neon-style Sci-Fi elements. Supports individual and group birthdays, localized timezones, and flexible styling.

### ✨ Key Features

* **Adaptive Card Generation:** Automatically scales the card and layout based on the text length and number of birthday people.
* **Sci-Fi Design:** Modern look with semi-transparent panels, neon lighting, and orbital rings.
* **Advanced Birthday Handling:** Supports multiple birthdays on the same day with custom "plural" messages.
* **Timezone Awareness:** Sends congratulations precisely at 06:00 based on the user's personal timezone or the server default.
* **Customization:** * Change fonts (place `.ttf` in the root folder).
* Customize text colors (title, body, name) via HEX codes.
* Set custom background images or URLs.



### 🛠️ Configuration Commands (Admin Only)

* `/config channel` — Set the channel for announcements.
* `/config texts` / `/config plural_texts` — Set messages for single or group birthdays.
* `/config color_title` / `/config color_msg` / `/config color_name` — Set text colors using HEX.
* `/config timezone` — Set the server-wide default timezone.
* `/config font` — Select a custom font file.
* `/config image` — Set a custom background image or GIF.
* `/config bd-override-set` — Set a birthday for any user on behalf of an admin.
* `/config bd-override-remove` — Remove a user's birthday on behalf of an admin.
* `/config tz-override-set` — Set a personal timezone for any user on behalf of an admin.

---

### 📖 Описание

Гибко настраиваемый Discord-бот для автоматического поздравления участников сервера с днем рождения. Бот создает стильные открытки в стиле Sci-Fi с использованием аватарок пользователей, кастомного фона и неоновых элементов. Поддерживает множественные дни рождения, индивидуальные часовые пояса и гибкую настройку стиля.

### ✨ Основные возможности

* **Адаптивные открытки:** Холст автоматически растягивается в зависимости от количества текста и количества именинников.
* **Sci-Fi дизайн:** Современный интерфейс с полупрозрачными панелями, неоновым свечением и орбитальными элементами.
* **Умная работа с именинниками:** Если в один день родились несколько человек, бот объединяет их в одной открытке с общим текстом и списком аватарок.
* **Таймзоны:** Поздравления отправляются ровно в 06:00 по локальному времени именинника (с учетом персональной или серверной настройки таймзоны).
* **Кастомизация:** * Выбор шрифтов (закиньте `.ttf` в папку бота).
* Настройка цветов каждого элемента текста через HEX-коды.
* Возможность установки фонового изображения или ссылки на GIF.
* **Административное управление днями рождения:** Администраторы могут устанавливать, удалять дни рождения и часовые пояса любому участнику без его участия.



Вы правы, приношу извинения за неполноту информации в предыдущем руководстве. Поскольку в текущем коде бота реализовано множество новых административных и пользовательских функций, вот полный список всех команд, разбитый по категориям для удобства ваших пользователей и модераторов.

### 📜 Полный справочник команд

#### 👤 Команды для участников сервера (`/birthday`)

Эти команды доступны всем пользователям для управления своими данными:

* `/birthday set day:.. month:..` — Сохраняет ваш день рождения в базу данных бота.
* `/birthday timezone tz_name:..` — Устанавливает ваш личный часовой пояс (например, `Europe/Moscow`). Это позволяет боту поздравить вас ровно в 06:00 утра по вашему локальному времени.
* `/birthday remove` — Полностью удаляет информацию о вашем дне рождения из базы бота.
* `/birthday list` — Выводит список всех зарегистрированных именинников на сервере, отсортированный по датам.

#### 🛠️ Административные команды (`/config`)

Эти команды доступны только пользователям с правами администратора сервера для настройки бота:

* `/config channel channel:..` — Выбор текстового канала, в который бот будет отправлять поздравления.
* `/config texts title:.. message:..` — Настройка заголовка и текста поздравления для случаев, когда именинник один. Используйте `{user}` в тексте для упоминания пользователя.
* `/config plural_texts title:.. message:..` — Настройка текста для случаев, когда в один день родились несколько человек.
* `/config color_title hex_code:..` — Цвет заголовка открытки (в HEX-формате, например `#00E5FF`).
* `/config color_msg hex_code:..` — Цвет основного текста поздравления (HEX).
* `/config color_name hex_code:..` — Цвет имени именинника на открытке (HEX).
* `/config timezone tz_name:..` — Установка часового пояса сервера по умолчанию (используется, если пользователь не задал свой личный пояс).
* `/config font filename:..` — Выбор шрифта из файла `.ttf`, загруженного в папку бота.
* `/config image url:..` — Ссылка на картинку/GIF для фона или слово `local` для использования файла `images/birthday_bg.png`.
* `/config bd-override-set user:.. day:.. month:..` — Устанавливает день рождения указанному пользователю от имени администратора (без участия самого пользователя).
* `/config bd-override-remove user:..` — Удаляет зарегистрированный день рождения у указанного пользователя.
* `/config tz-override-set user:.. tz_name:..` — Устанавливает личный часовой пояс указанному пользователю (например, `Europe/Moscow`).

#### 🧪 Команды для тестирования

* `/birthday test user2:..` — Генерирует и отправляет вам (в скрытом виде) тестовую открытку. Если вы укажете `user2`, бот покажет, как будет выглядеть поздравление сразу для двух именинников в одном сообщении.

---

### 💡 Полезные советы по настройке

1. **HEX-цвета:** Для подбора цветов вы можете использовать любой онлайн-сервис (например, *Google Color Picker* или *Coolors*). Просто скопируйте код вида `#RRGGBB` и вставьте его в команду `/config color_...`.
2. **Таймзоны:** Бот поддерживает стандартные названия из базы IANA. Самые популярные:
* `Europe/Moscow` (Москва)
* `Europe/Kiev` (Киев)
* `UTC` (Всемирное координированное время)
* `Asia/Almaty` (Алматы)


3. **Шрифты:** Если вы хотите сменить шрифт, убедитесь, что `.ttf` файл лежит в той же папке, где находится `bot.py`, и при вызове команды `/config font` укажите его полное имя с расширением (например, `Roboto.ttf`).


### ⚙️ Установка

1. Установите Python (3.8+).
2. Установите зависимости: `pip install discord.py pillow zoneinfo`.
3. Запустите бота: `python bot.py`.
4. Включите `Message Content Intent` и `Server Members Intent` на портале разработчиков Discord.