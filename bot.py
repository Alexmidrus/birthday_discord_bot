"""Discord-бот для автоматических поздравлений с днём рождения.

Бот отслеживает дни рождения участников серверов Discord и отправляет
персонализированные поздравительные открытки ровно в 06:00 по часовому
поясу каждого пользователя.

Основные возможности:
    - Генерация открыток в стиле Sci-Fi с аватаром именинника через Pillow.
    - Поддержка нескольких именинников в один день (групповая открытка).
    - Индивидуальные и серверные часовые пояса.
    - Гибкая настройка текстов, цветов, шрифтов и фонового изображения.
    - Slash-команды через discord.py app_commands.

Требования:
    - Python 3.9+ (для zoneinfo).
    - Переменная окружения ``DISCORD_TOKEN`` с токеном бота.
    - Включённые интенты: ``Server Members``, ``Message Content``.

Example:
    Запуск бота::

        python bot.py
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import logging
import os
import datetime
import aiohttp
import re
import random
import zoneinfo
from io import BytesIO
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter

load_dotenv()

DATA_DIR   = "data"
DATA_FILE  = os.path.join(DATA_DIR, "data.json")
SENT_LOG_FILE = os.path.join(DATA_DIR, "sent_log.json")
LOG_FILE   = os.path.join(DATA_DIR, "bot.log")
BG_IMAGE   = "images/birthday_bg.png"
FONTS_DIR  = "fonts"
DEFAULT_FONT = os.path.join(FONTS_DIR, "Jura-Bold.ttf")

os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
# Отдельный логгер (не 'discord') с собственными хендлерами, чтобы не
# зависеть от того, настраивает ли discord.py логирование через bot.run().

logger = logging.getLogger("birthday_bot")
logger.setLevel(logging.INFO)

_log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)
logger.addHandler(_console_handler)

_file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
_file_handler.setFormatter(_log_formatter)
logger.addHandler(_file_handler)

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    """Конвертирует HEX-строку цвета в RGBA-кортеж для Pillow.

    Принимает цвет в формате ``#RRGGBB`` или ``RRGGBB``. При некорректном
    значении возвращает белый цвет с заданной прозрачностью.

    Args:
        hex_color: Строка цвета в формате ``#RRGGBB`` или ``RRGGBB``.
        alpha: Значение альфа-канала от 0 (прозрачный) до 255 (непрозрачный).
            По умолчанию 255.

    Returns:
        Кортеж ``(R, G, B, A)`` с целочисленными значениями от 0 до 255.
        При ошибке парсинга возвращает ``(255, 255, 255, alpha)``.

    Example:
        >>> hex_to_rgba("#FF0000")
        (255, 0, 0, 255)
        >>> hex_to_rgba("#00FF00", alpha=128)
        (0, 255, 0, 128)
    """
    hex_color = hex_color.lstrip('#')
    try:
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)
    except ValueError:
        pass
    return (255, 255, 255, alpha)


def strip_emoji(text: str) -> str:
    """Удаляет эмодзи из строки и обрезает граничные символы.

    Используется перед рендерингом текста шрифтами TrueType, которые не
    содержат глифов для эмодзи и отображают их как квадраты-тофу.

    Args:
        text: Исходная строка, возможно содержащая эмодзи.

    Returns:
        Строка без эмодзи, с обрезанными пробелами, точками, дефисами
        и подчёркиваниями по краям.

    Example:
        >>> strip_emoji("🎉 Happy Birthday! 🎈")
        'Happy Birthday!'
        >>> strip_emoji("BIRTHDAY PROTOCOL")
        'BIRTHDAY PROTOCOL'
    """
    return _EMOJI_RE.sub("", text).strip(" .-_")


def wrap_text_to_pixels(text: str, font: ImageFont.FreeTypeFont,
                        max_width: int, draw: ImageDraw.ImageDraw) -> str:
    """Переносит текст на новую строку по ширине в пикселях.

    В отличие от стандартного переноса по символам, функция измеряет
    реальную ширину строки отрисованного текста через ``draw.textbbox``.
    Длинные слова, не помещающиеся в ``max_width``, принудительно
    разбиваются с дефисом.

    Args:
        text: Исходный текст. Символы ``\\n`` сохраняются как разрывы абзацев.
        font: Шрифт Pillow для замера ширины глифов.
        max_width: Максимально допустимая ширина строки в пикселях.
        draw: Объект ``ImageDraw`` для замеров через ``textbbox``.

    Returns:
        Строка с вставленными символами ``\\n`` в местах переноса.

    Note:
        Если даже один символ с дефисом не вписывается в ``max_width``
        (например, шрифт очень крупный), слово выводится как есть без
        бесконечного зависания.
    """
    lines = []
    for paragraph in text.split('\n'):
        words = paragraph.split(' ')
        if not words:
            lines.append("")
            continue

        current_line = ""
        for word in words:
            while draw.textbbox((0, 0), word, font=font)[2] > max_width:
                split_done = False
                for i in range(len(word), 0, -1):
                    part_with_hyphen = word[:i] + "-"
                    if draw.textbbox((0, 0), part_with_hyphen, font=font)[2] <= max_width:
                        if current_line:
                            lines.append(current_line)
                            current_line = ""
                        lines.append(part_with_hyphen)
                        word = word[i:]
                        split_done = True
                        break
                if not split_done:
                    break

            test_line = f"{current_line} {word}".strip()
            if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Генератор открытки
# ---------------------------------------------------------------------------

def create_birthday_card(avatars_bytes: list, usernames: list,
                         bg_bytes: bytes | None, title_text: str,
                         message_text: str, guild_data: dict) -> BytesIO:
    """Генерирует поздравительную открытку в стиле Sci-Fi.

    Создаёт изображение PNG размером 1100×H пикселей (высота адаптивная),
    где H определяется количеством текста и аватаров. Стиль: тёмный фон,
    неоновые линии, круглые аватары с эффектом свечения, звёздное поле.

    Слои отрисовки (снизу вверх):
        1. Фоновое изображение с тёмным оверлеем (или однотонный фон).
        2. Слой свечения вокруг аватаров (GaussianBlur).
        3. Декоративные элементы (рамки, разделитель, угловые маркеры).
        4. Текст (заголовок, имена, сообщение, статусная строка).
        5. Круглые аватары именинников.

    Args:
        avatars_bytes: Список байтовых строк PNG-изображений аватаров.
            При нескольких аватарах они выстраиваются в столбик.
        usernames: Список отображаемых имён именинников в том же порядке,
            что и ``avatars_bytes``.
        bg_bytes: Байты фонового изображения. Если ``None``, используется
            тёмный однотонный фон ``(6, 10, 22)``.
        title_text: Текст заголовка-метки (например, «BIRTHDAY PROTOCOL»).
            Эмодзи удаляются автоматически.
        message_text: Основной текст поздравления.
        guild_data: Словарь настроек сервера. Используемые ключи:
            ``color_title``, ``color_name``, ``color_msg``, ``font``.

    Returns:
        Объект ``BytesIO`` с PNG-изображением, готовый к передаче
        в ``discord.File``.

    Note:
        Размер шрифта имён автоматически уменьшается, если строка имён
        превышает доступную ширину. Минимальный размер — 28pt.
    """
    W = 1100
    base_H = 480
    divider_x = 320
    av_cx = 185

    avatars_count = len(avatars_bytes)
    avatar_size = 175 if avatars_count == 1 else 130
    avatar_spacing = 30
    avatars_total_h = avatars_count * avatar_size + (avatars_count - 1) * avatar_spacing

    tx = divider_x + 48
    tw = W - tx - 36

    CYAN      = (0, 212, 255, 255)
    CYAN_160  = (0, 212, 255, 160)
    CYAN_80   = (0, 212, 255, 80)
    CYAN_38   = (0, 212, 255, 38)
    GOLD      = (255, 196, 0, 255)
    BG_COLOR  = (6, 10, 22, 255)

    c_title = hex_to_rgba(guild_data.get("color_title", "#00d4ff"), 185)
    c_name  = hex_to_rgba(guild_data.get("color_name", "#FFFFFF"), 255)
    c_msg   = hex_to_rgba(guild_data.get("color_msg", "#C3D2EB"), 220)

    font_path = guild_data.get("font", DEFAULT_FONT)

    try:
        f_label  = ImageFont.truetype(font_path, 16)
        f_name   = ImageFont.truetype(font_path, 62)
        f_msg    = ImageFont.truetype(font_path, 26)
        f_status = ImageFont.truetype(font_path, 12)
    except IOError:
        f_label = f_name = f_msg = f_status = ImageFont.load_default()

    dummy = Image.new("RGBA", (2000, 2000))
    dd    = ImageDraw.Draw(dummy)

    label_raw = strip_emoji(title_text).upper().strip() or "BIRTHDAY PROTOCOL"
    lbl_wrap  = wrap_text_to_pixels(label_raw, f_label, tw, dd)
    lbl_h     = dd.multiline_textbbox((0, 0), lbl_wrap, font=f_label)[3]

    names_str = ", ".join(usernames)
    name_w_px = dd.textbbox((0, 0), names_str, font=f_name)[2]

    f_name_adj = f_name
    if name_w_px > tw:
        adj_size = max(28, int(62 * tw / name_w_px))
        try:
            f_name_adj = ImageFont.truetype(font_path, adj_size)
        except IOError:
            pass

    names_wrap = wrap_text_to_pixels(names_str, f_name_adj, tw, dd)
    name_h     = dd.multiline_textbbox((0, 0), names_wrap, font=f_name_adj)[3]

    msg_wrap = wrap_text_to_pixels(message_text, f_msg, tw, dd)
    msg_h    = dd.multiline_textbbox((0, 0), msg_wrap, font=f_msg)[3]

    G1, G2, G3 = 7, 10, 12
    text_block_h = lbl_h + G1 + name_h + G2 + 2 + G3 + msg_h

    H = max(base_H, text_block_h + 80, avatars_total_h + 80)

    text_start_y = max(40, (H - text_block_h) // 2)
    av_start_y = (H - avatars_total_h) // 2

    avatar_centers_y = [
        av_start_y + (avatar_size // 2) + i * (avatar_size + avatar_spacing)
        for i in range(avatars_count)
    ]

    card = Image.new("RGBA", (W, H), BG_COLOR)
    if bg_bytes:
        try:
            raw = (Image.open(BytesIO(bg_bytes))
                   .convert("RGBA")
                   .resize((W, H), Image.Resampling.LANCZOS))
            dark_overlay = Image.new("RGBA", (W, H), (0, 5, 15, 215))
            card = Image.alpha_composite(raw, dark_overlay)
        except Exception:
            pass

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for cy_i in avatar_centers_y:
        for extra, alpha in [(82, 18), (56, 34), (33, 58), (14, 100)]:
            r = (avatar_size + extra) // 2
            gd.ellipse([av_cx - r, cy_i - r, av_cx + r, cy_i + r], fill=(0, 212, 255, alpha))

    glow = glow.filter(ImageFilter.GaussianBlur(radius=14))
    card = Image.alpha_composite(card, glow)

    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)

    d.rectangle([(0,   0), (W,   2)], fill=CYAN)
    d.rectangle([(0,   2), (W,   4)], fill=(0, 212, 255, 75))
    d.rectangle([(0, H-3), (W, H-1)], fill=CYAN)
    d.rectangle([(0, H-5), (W, H-3)], fill=(0, 212, 255, 75))
    d.rectangle([(0, 0), (3, H)], fill=(0, 212, 255, 235))

    cs = 22
    for ex, ey, dx, dy in [(18, 18, 1, 1), (W-18, 18, -1, 1), (18, H-18, 1, -1), (W-18, H-18, -1, -1)]:
        d.line([(ex, ey), (ex + dx*cs, ey)],  fill=(0, 212, 255, 155), width=2)
        d.line([(ex, ey), (ex, ey + dy*cs)],  fill=(0, 212, 255, 155), width=2)

    FADE_H = 55
    STEPS  = 12
    d.rectangle([(divider_x, FADE_H), (divider_x + 1, H - FADE_H)], fill=CYAN_160)
    for i in range(STEPS):
        seg = max(1, FADE_H // STEPS)
        y_t = int(i * FADE_H / STEPS)
        y_b = H - FADE_H + int(i * FADE_H / STEPS)
        a_t = int(160 * i / STEPS)
        a_b = int(160 * (1 - i / STEPS))
        d.rectangle([(divider_x, y_t), (divider_x+1, y_t+seg)], fill=(0, 212, 255, a_t))
        d.rectangle([(divider_x, y_b), (divider_x+1, y_b+seg)], fill=(0, 212, 255, a_b))

    for cy_i in avatar_centers_y:
        ring_r = avatar_size // 2 + 5
        d.ellipse([av_cx - ring_r, cy_i - ring_r, av_cx + ring_r, cy_i + ring_r], outline=CYAN, width=3)
        arc_r = avatar_size // 2 + 13
        d.arc([av_cx - arc_r, cy_i - arc_r, av_cx + arc_r, cy_i + arc_r], start=30, end=150, fill=(255, 196, 0, 190), width=2)

    y = text_start_y
    d.multiline_text((tx, y), lbl_wrap, font=f_label, fill=c_title)
    y += lbl_h + G1

    d.multiline_text((tx, y), names_wrap, font=f_name_adj, fill=c_name, stroke_width=1, stroke_fill=(0, 0, 0, 100))
    y += name_h + G2

    d.rectangle([(tx, y), (tx + 80, y + 2)], fill=GOLD)
    d.rectangle([(tx + 88, y), (tx + tw, y + 1)], fill=CYAN_80)
    y += 2 + G3

    d.multiline_text((tx, y), msg_wrap, font=f_msg, fill=c_msg, spacing=6)
    d.text((tx, H - 22), "NEURAL INTERFACE  //  CLONE STATUS: ACTIVE", font=f_status, fill=CYAN_38)

    rng = random.Random(42)
    for _ in range(int(H * 0.15)):
        sx = rng.randint(5, divider_x - 10)
        sy = rng.randint(5, H - 5)
        overlap = any(
            ((sx - av_cx)**2 + (sy - cy_i)**2) ** 0.5 < (avatar_size // 2 + 22)
            for cy_i in avatar_centers_y
        )
        if overlap:
            continue
        alpha = rng.randint(25, 115)
        size  = rng.choice([0, 0, 1])
        d.ellipse([sx, sy, sx + size, sy + size], fill=(255, 255, 255, alpha))

    card = Image.alpha_composite(card, layer)

    for idx, cy_i in enumerate(avatar_centers_y):
        try:
            av = (Image.open(BytesIO(avatars_bytes[idx]))
                  .convert("RGBA")
                  .resize((avatar_size, avatar_size), Image.Resampling.LANCZOS))
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_size, avatar_size), fill=255)
            circle_av = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
            circle_av.paste(av, (0, 0), mask)
            card.paste(circle_av, (av_cx - avatar_size // 2, cy_i - avatar_size // 2), circle_av)
        except Exception:
            pass

    out = BytesIO()
    card.save(out, format="PNG")
    out.seek(0)
    return out


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _pick_texts(guild_data: dict, is_plural: bool) -> tuple[str, str]:
    """Выбирает тексты заголовка и сообщения в зависимости от числа именинников.

    Args:
        guild_data: Словарь настроек сервера с ключами ``title``, ``message``,
            ``plural_title``, ``plural_message``.
        is_plural: ``True``, если именинников несколько в один день.

    Returns:
        Кортеж ``(title, message)`` — строки для отрисовки на открытке.
    """
    if is_plural:
        title = guild_data.get("plural_title", guild_data.get("title", "🎉 С Днем Рождения! 🎈"))
        msg   = guild_data.get("plural_message", guild_data.get("message", "Поздравляем вас!"))
    else:
        title = guild_data.get("title", "🎉 С Днем Рождения! 🎈")
        msg   = guild_data.get("message", "Поздравляем тебя!")
    return title, msg


async def _load_bg_bytes(image_url: str,
                         session: aiohttp.ClientSession) -> bytes | None:
    """Загружает байты фонового изображения из указанного источника.

    Поддерживает три режима:
        - ``"local"`` — читает файл ``images/birthday_bg.png`` с диска.
        - HTTP/HTTPS URL — скачивает изображение через ``session``.
        - GIF URL — возвращает ``None`` (GIF обрабатывается отдельно как embed).

    Args:
        image_url: URL изображения, ``"local"`` для локального файла,
            или URL GIF-анимации.
        session: Активная ``aiohttp.ClientSession`` для HTTP-запросов.

    Returns:
        Байты изображения или ``None``, если загрузка не удалась,
        URL указывает на GIF, либо локальный файл не найден.
    """
    if ".gif" in image_url.lower():
        return None
    if image_url.lower() == "local":
        if os.path.exists(BG_IMAGE):
            with open(BG_IMAGE, 'rb') as f:
                return f.read()
        return None
    if image_url.startswith("http"):
        try:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception:
            pass
    return None


def _build_card_message(avatars: list, usernames: list, bg_bytes: bytes | None,
                        t_text: str, m_text: str, guild_data: dict,
                        image_url: str) -> tuple:
    """Генерирует открытку и собирает объекты для отправки в Discord.

    Вызывает :func:`create_birthday_card`, создаёт ``discord.File`` и список
    embed-объектов. Если ``image_url`` указывает на GIF, добавляет второй
    embed с анимацией поверх открытки.

    Args:
        avatars: Список байтов PNG-аватаров именинников.
        usernames: Список отображаемых имён именинников.
        bg_bytes: Байты фонового изображения или ``None``.
        t_text: Текст заголовка для открытки.
        m_text: Текст сообщения для открытки.
        guild_data: Словарь настроек сервера (цвета, шрифт и т.д.).
        image_url: URL фона или ``"local"``; используется для определения
            наличия GIF.

    Returns:
        Кортеж ``(file, embeds)``, где ``file`` — ``discord.File`` с PNG,
        ``embeds`` — список ``discord.Embed`` (1 или 2 элемента при GIF).
    """
    card_buffer = create_birthday_card(avatars, usernames, bg_bytes, t_text, m_text, guild_data)
    file   = discord.File(card_buffer, filename="card.png")
    color  = discord.Color.from_str(guild_data.get("color", "#FF5733"))
    embed  = discord.Embed(color=color)
    embed.set_image(url="attachment://card.png")
    embeds = [embed]
    if ".gif" in image_url.lower():
        embed2 = discord.Embed(color=color)
        embed2.set_image(url=image_url)
        embeds.append(embed2)
    return file, embeds


# ---------------------------------------------------------------------------
# Класс бота
# ---------------------------------------------------------------------------

class BirthdayBot(commands.Bot):
    """Discord-бот для автоматических поздравлений с днём рождения.

    Наследует ``commands.Bot`` и добавляет:
        - Фоновую задачу ``check_birthdays``, запускаемую раз в час.
        - Управление жизненным циклом ``aiohttp.ClientSession``.
        - Синхронизацию slash-команд при подключении.

    Attributes:
        session (aiohttp.ClientSession | None): HTTP-сессия для загрузки
            фоновых изображений. Инициализируется в ``setup_hook``,
            закрывается в ``close``.
    """

    def __init__(self) -> None:
        """Инициализирует бота с необходимыми интентами."""
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self) -> None:
        """Выполняется при запуске бота до события ``on_ready``.

        Создаёт HTTP-сессию, запускает фоновый цикл проверки дней рождения
        и синхронизирует slash-команды с Discord.
        """
        self.session = aiohttp.ClientSession()
        self.check_birthdays.start()
        await self.tree.sync()
        logger.info("setup_hook завершён: HTTP-сессия создана, check_birthdays запущен, slash-команды синхронизированы.")

    async def close(self) -> None:
        """Корректно завершает работу бота.

        Закрывает ``aiohttp.ClientSession`` перед отключением от Discord,
        чтобы избежать утечки ресурсов.
        """
        if self.session:
            await self.session.close()
        await super().close()

    @tasks.loop(hours=1)
    async def check_birthdays(self) -> None:
        """Проверяет дни рождения и отправляет поздравления.

        Запускается раз в час. Для каждого сервера проверяет, у кого
        из участников уже наступило 06:00 или позже по их локальному
        часовому поясу и совпадает ли сегодняшняя дата с зарегистрированным
        днём рождения. Условие "``>= 6``", а не "``== 6``", сделано намеренно:
        если бот был недоступен ровно в 6-й час (рестарт, деплой, обрыв связи),
        поздравление всё равно уйдёт, как только бот снова начнёт проверку в
        тот же день, вместо того чтобы быть пропущенным до следующего года.

        Логика пропуска:
            - Канал для поздравлений не настроен.
            - Канал или сервер недоступен (бот покинул сервер).
            - Поздравление уже было отправлено в текущем году (журнал
              ``sent_log.json``, см. :func:`load_sent_log`).
            - Участник покинул сервер.

        Отметка "поздравление отправлено" пишется в ``sent_log.json`` сразу
        после успешного ``channel.send`` для конкретного сервера — не
        батчем в конце всей проверки. Это защищает от дублей: если бот
        упадёт сразу после отправки на одном сервере, но до обработки
        остальных, уже отправленное поздравление не потеряется и не
        уйдёт повторно после перезапуска. По той же причине отметка
        ставится только после успешной отправки, а не заранее — если
        ``channel.send`` упадёт с ошибкой, попытка будет повторена на
        следующей часовой проверке в тот же день.

        Note:
            Метод вызывается как обычная корутина из ``before_check_birthdays``
            при старте бота (для обработки случая перезапуска во время 6-го часа),
            и автоматически планировщиком задач каждый час.
        """
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        current_year = now_utc.year
        all_data = load_data()
        sent_log = load_sent_log()

        logger.info("Проверка дней рождения запущена (%s).", now_utc.isoformat(timespec="seconds"))

        for guild_id_str, guild_data in all_data.items():
            channel_id = guild_data.get("channel_id")
            if not channel_id:
                continue

            channel = self.get_channel(channel_id)
            if not channel:
                logger.warning("Сервер %s: канал %s недоступен, пропускаю.", guild_id_str, channel_id)
                continue

            server_tz_str = guild_data.get("timezone", "UTC")
            user_timezones = guild_data.get("user_timezones", {})
            guild_sent = sent_log.setdefault(guild_id_str, {})

            # Разовая миграция устаревшего guild_data["sent_years"] (до перехода
            # на sent_log.json) в новый журнал. Без этого пользователи, уже
            # отмеченные отправленными в старом формате, получили бы повторное
            # поздравление, если их день рождения ещё не наступил на момент
            # обновления бота.
            legacy_sent = guild_data.get("sent_years") or {}
            migrated = {uid: year for uid, year in legacy_sent.items() if uid not in guild_sent}
            if migrated:
                guild_sent.update(migrated)
                save_sent_log(sent_log)
                logger.info(
                    "Сервер %s: перенёс устаревшие отметки sent_years в sent_log.json: %s.",
                    guild_id_str, migrated)

            to_congratulate = []

            for user_id_str, date_str in guild_data.get("birthdays", {}).items():
                if guild_sent.get(user_id_str) == current_year:
                    continue

                user_tz_str = user_timezones.get(user_id_str, server_tz_str)
                try:
                    tz = zoneinfo.ZoneInfo(user_tz_str)
                except Exception:
                    logger.warning(
                        "Сервер %s: некорректный часовой пояс '%s' у пользователя %s, использую UTC.",
                        guild_id_str, user_tz_str, user_id_str)
                    tz = zoneinfo.ZoneInfo("UTC")

                user_local_time = now_utc.astimezone(tz)

                if (f"{user_local_time.day:02d}.{user_local_time.month:02d}" == date_str
                        and user_local_time.hour >= 6):
                    to_congratulate.append(user_id_str)

            if not to_congratulate:
                continue

            guild = self.get_guild(int(guild_id_str))
            if not guild:
                logger.warning("Сервер %s недоступен (бот больше не на сервере?), пропускаю.", guild_id_str)
                continue

            avatars, usernames, matched_uids = [], [], []

            for uid in to_congratulate:
                user = guild.get_member(int(uid))
                if not user:
                    logger.warning("Сервер %s: участник %s не найден, пропускаю.", guild_id_str, uid)
                    continue
                avatars.append(await user.display_avatar.replace(format="png", size=256).read())
                usernames.append(user.display_name)
                matched_uids.append(uid)

            if not avatars:
                continue

            try:
                image_url = guild_data.get("image_url", "local")
                t_text, m_text = _pick_texts(guild_data, is_plural=len(avatars) > 1)
                bg_bytes = await _load_bg_bytes(image_url, self.session)
                file, embeds = _build_card_message(avatars, usernames, bg_bytes, t_text, m_text, guild_data, image_url)
                await channel.send(content="🎉 @everyone", embeds=embeds, file=file)
            except Exception:
                logger.exception(
                    "Сервер %s: не удалось отправить поздравление для %s, повторю на следующей проверке.",
                    guild_id_str, matched_uids)
                continue

            for uid in matched_uids:
                guild_sent[uid] = current_year
            save_sent_log(sent_log)
            logger.info("Сервер %s: поздравление отправлено для %s.", guild_id_str, matched_uids)

    @check_birthdays.before_loop
    async def before_check_birthdays(self) -> None:
        """Выравнивает запуск цикла на начало следующего целого часа.

        Ждёт готовности бота, затем немедленно выполняет разовую проверку
        (на случай если бот был перезапущен в промежутке 6:00–6:59),
        после чего засыпает до начала следующего часа UTC.
        """
        await self.wait_until_ready()
        await self.check_birthdays()
        now = datetime.datetime.now(datetime.timezone.utc)
        seconds_until_next_hour = 3600 - (now.minute * 60 + now.second)
        await asyncio.sleep(seconds_until_next_hour)

    @check_birthdays.error
    async def check_birthdays_error(self, error: BaseException) -> None:
        """Логирует необработанные ошибки цикла и перезапускает его.

        По умолчанию ``tasks.loop`` при необработанном исключении в теле
        задачи молча останавливает цикл насовсем (до перезапуска процесса),
        не оставляя следа в логах — из-за этого падение можно было заметить
        только по факту "бот перестал поздравлять". Здесь ошибка логируется
        с трассировкой, а цикл перезапускается, чтобы часовая проверка не
        прерывалась из-за одного сбойного прогона.
        """
        logger.exception("check_birthdays упал с необработанной ошибкой, перезапускаю цикл.", exc_info=error)
        if not self.check_birthdays.is_running():
            self.check_birthdays.restart()


bot = BirthdayBot()


# ---------------------------------------------------------------------------
# Работа с данными
# ---------------------------------------------------------------------------

def load_data() -> dict:
    """Загружает данные всех серверов из JSON-файла.

    Returns:
        Словарь вида ``{guild_id: guild_data}``. Если файл не существует,
        возвращает пустой словарь.
    """
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_data(data: dict) -> None:
    """Сохраняет данные всех серверов в JSON-файл.

    Args:
        data: Словарь вида ``{guild_id: guild_data}`` для записи.
    """
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_sent_log() -> dict:
    """Загружает журнал уже отправленных поздравлений из отдельного файла.

    Хранится отдельно от ``data.json``, чтобы отметка об отправке
    сохранялась на диск сразу после каждого успешного поздравления, а не
    только в конце всей часовой проверки — это исключает повторную отправку
    при падении/перезапуске бота в середине обработки нескольких серверов.

    Returns:
        Словарь вида ``{guild_id: {user_id: year}}``. Если файл не
        существует, возвращает пустой словарь.
    """
    if not os.path.exists(SENT_LOG_FILE):
        return {}
    with open(SENT_LOG_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_sent_log(data: dict) -> None:
    """Сохраняет журнал отправленных поздравлений в JSON-файл.

    Args:
        data: Словарь вида ``{guild_id: {user_id: year}}`` для записи.
    """
    with open(SENT_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_guild_data(guild_id: int) -> tuple[dict, dict]:
    """Возвращает данные конкретного сервера, создавая запись при первом обращении.

    Если сервер ещё не имеет записи в базе, создаёт её с дефолтными
    значениями (канал не настроен, стандартные тексты, часовой пояс UTC).

    Args:
        guild_id: Числовой идентификатор сервера Discord.

    Returns:
        Кортеж ``(guild_data, all_data)``, где ``guild_data`` — настройки
        конкретного сервера, ``all_data`` — полный словарь всех серверов
        (для последующего сохранения через :func:`save_data`).
    """
    data = load_data()
    if str(guild_id) not in data:
        data[str(guild_id)] = {
            "channel_id": None,
            "title": "BIRTHDAY PROTOCOL",
            "message": "Поздравляем тебя с днем рождения! Желаем успехов во всех начинаниях.",
            "plural_title": "BIRTHDAY PROTOCOL MULTIPLE",
            "plural_message": "Поздравляем вас с днем рождения! Двойной праздник - двойная радость!",
            "color_title": "#00d4ff", "color_msg": "#c3d2eb", "color_name": "#ffffff",
            "image_url": "local", "color": "#FF5733", "timezone": "UTC", "font": DEFAULT_FONT,
            "birthdays": {}, "user_timezones": {}
        }
    return data[str(guild_id)], data


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------

@bot.tree.command(name="help", description="Справка по командам бота")
async def help_command(interaction: discord.Interaction) -> None:
    """Отображает справку по всем командам бота.

    Args:
        interaction: Объект взаимодействия Discord.
    """
    embed = discord.Embed(
        title="🎂 Birthday Bot Help",
        description=(
            "Я автоматически поздравляю участников сервера с днем рождения!\n\n"
            "**👤 Пользователям:**\n"
            "`/birthday set` — Установить свой день рождения\n"
            "`/birthday timezone` — Установить свой личный часовой пояс\n"
            "`/birthday remove` — Удалить свои данные\n"
            "`/birthday list` — 📅 Список именинников\n\n"
            "**🛠️ Администраторам:**\n"
            "`/config channel` — Установить канал\n"
            "`/config texts` / `/config plural_texts` — Тексты (один или несколько именинников)\n"
            "`/config color_...` — Настройка цветов шрифтов\n"
            "`/config timezone` — Глобальный часовой пояс сервера\n"
            "`/config font` — Изменить шрифт\n"
            "`/config image` — Настроить фон (URL или `local`)\n"
            "`/config bd-override-set` — Установить день рождения пользователю\n"
            "`/config bd-override-remove` — Удалить день рождения пользователя\n"
            "`/config tz-override-set` — Установить часовой пояс пользователю\n"
            "`/birthday test` — 🛠️ Проверить открытку"
        ),
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


config_group = app_commands.Group(
    name="config",
    description="Настройки бота",
    default_permissions=discord.Permissions(administrator=True)
)
birthday_group = app_commands.Group(name="birthday", description="Управление днями рождения")


@config_group.command(name="channel", description="Установить канал для отправки поздравлений")
async def config_channel(interaction: discord.Interaction,
                         channel: discord.TextChannel) -> None:
    """Устанавливает канал, в который бот будет отправлять поздравления.

    Args:
        interaction: Объект взаимодействия Discord.
        channel: Текстовый канал для поздравлений.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    d["channel_id"] = channel.id
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Канал установлен: {channel.mention}", ephemeral=True)


@config_group.command(name="texts", description="Текст поздравления для 1 именинника")
async def config_texts(interaction: discord.Interaction,
                       title: str = None, message: str = None) -> None:
    """Настраивает текст поздравления для одного именинника.

    Args:
        interaction: Объект взаимодействия Discord.
        title: Новый заголовок открытки. Если не указан — не изменяется.
        message: Новый текст поздравления. Если не указан — не изменяется.
    """
    if not title and not message:
        await interaction.response.send_message(
            "⚠️ Укажи хотя бы один параметр: `title` или `message`.", ephemeral=True)
        return
    d, all_d = get_guild_data(interaction.guild.id)
    if title:
        d["title"] = title
    if message:
        d["message"] = message
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message("✅ Тексты для одного именинника обновлены.", ephemeral=True)


@config_group.command(name="plural_texts", description="Текст поздравления для нескольких именинников в один день")
async def config_plural(interaction: discord.Interaction,
                        title: str = None, message: str = None) -> None:
    """Настраивает текст поздравления для нескольких именинников в один день.

    Args:
        interaction: Объект взаимодействия Discord.
        title: Новый заголовок групповой открытки. Если не указан — не изменяется.
        message: Новый текст группового поздравления. Если не указан — не изменяется.
    """
    if not title and not message:
        await interaction.response.send_message(
            "⚠️ Укажи хотя бы один параметр: `title` или `message`.", ephemeral=True)
        return
    d, all_d = get_guild_data(interaction.guild.id)
    if title:
        d["plural_title"] = title
    if message:
        d["plural_message"] = message
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message("✅ Тексты для множественных дней рождения обновлены.", ephemeral=True)


@config_group.command(name="color_title", description="Цвет метки заголовка (HEX)")
async def config_color_title(interaction: discord.Interaction, hex_code: str) -> None:
    """Устанавливает цвет заголовка открытки.

    Args:
        interaction: Объект взаимодействия Discord.
        hex_code: Цвет в формате HEX, например ``#00E5FF``.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    d["color_title"] = hex_code
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Цвет заголовка установлен на {hex_code}", ephemeral=True)


@config_group.command(name="color_msg", description="Цвет основного текста (HEX)")
async def config_color_msg(interaction: discord.Interaction, hex_code: str) -> None:
    """Устанавливает цвет основного текста поздравления.

    Args:
        interaction: Объект взаимодействия Discord.
        hex_code: Цвет в формате HEX, например ``#C3D2EB``.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    d["color_msg"] = hex_code
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Цвет текста установлен на {hex_code}", ephemeral=True)


@config_group.command(name="color_name", description="Цвет имени (HEX)")
async def config_color_name(interaction: discord.Interaction, hex_code: str) -> None:
    """Устанавливает цвет имени именинника на открытке.

    Args:
        interaction: Объект взаимодействия Discord.
        hex_code: Цвет в формате HEX, например ``#FFFFFF``.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    d["color_name"] = hex_code
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Цвет имени установлен на {hex_code}", ephemeral=True)


@config_group.command(name="timezone", description="Глобальный часовой пояс (например, Europe/Moscow)")
async def config_timezone(interaction: discord.Interaction, tz_name: str) -> None:
    """Устанавливает глобальный часовой пояс сервера по умолчанию.

    Применяется к участникам, не установившим личный часовой пояс через
    ``/birthday timezone``.

    Args:
        interaction: Объект взаимодействия Discord.
        tz_name: Название таймзоны в формате IANA, например ``Europe/Moscow``.
    """
    try:
        zoneinfo.ZoneInfo(tz_name)
        d, all_d = get_guild_data(interaction.guild.id)
        d["timezone"] = tz_name
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(
            f"✅ Глобальный часовой пояс установлен на `{tz_name}`.", ephemeral=True)
    except zoneinfo.ZoneInfoNotFoundError:
        await interaction.response.send_message("❌ Ошибка: Неверное имя таймзоны.", ephemeral=True)


@config_group.command(name="font", description="Имя файла шрифта .ttf из папки fonts/")
async def config_font(interaction: discord.Interaction, filename: str) -> None:
    """Устанавливает шрифт для открыток из папки ``fonts/``.

    Args:
        interaction: Объект взаимодействия Discord.
        filename: Имя файла шрифта с расширением ``.ttf`` или без него,
            например ``Orbitron-Bold`` или ``Orbitron-Bold.ttf``.
    """
    if not filename.endswith('.ttf'):
        filename += '.ttf'
    font_path = os.path.join(FONTS_DIR, filename)
    if not os.path.exists(font_path):
        await interaction.response.send_message(
            f"❌ Файл `{filename}` не найден в папке `{FONTS_DIR}/`.", ephemeral=True)
        return
    d, all_d = get_guild_data(interaction.guild.id)
    d["font"] = font_path
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Шрифт изменен на `{filename}`.", ephemeral=True)


@config_group.command(name="bd-override-set", description="[Админ] Установить день рождения указанному пользователю")
async def config_bd_override_set(interaction: discord.Interaction,
                                  user: discord.Member,
                                  day: app_commands.Range[int, 1, 31],
                                  month: app_commands.Range[int, 1, 12]) -> None:
    """Устанавливает день рождения указанному участнику сервера от имени администратора.

    Позволяет добавить или перезаписать дату рождения любого пользователя
    без его участия. Год не сохраняется — поздравление отправляется ежегодно.

    Args:
        interaction: Объект взаимодействия Discord.
        user: Участник сервера, которому устанавливается дата.
        day: День рождения от 1 до 31.
        month: Месяц рождения от 1 до 12.
    """
    try:
        # Проверяем, что дата реально существует (например, 31.02 недопустима)
        date_str = f"{day:02d}.{month:02d}"
        datetime.datetime.strptime(f"2000.{date_str}", "%Y.%d.%m")
        d, all_d = get_guild_data(interaction.guild.id)
        d["birthdays"][str(user.id)] = date_str
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(
            f"✅ День рождения {user.mention} установлен на **{date_str}**.", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Указана несуществующая дата.", ephemeral=True)


@config_group.command(name="bd-override-remove", description="[Админ] Удалить день рождения указанного пользователя")
async def config_bd_override_remove(interaction: discord.Interaction,
                                     user: discord.Member) -> None:
    """Удаляет день рождения указанного участника сервера от имени администратора.

    Args:
        interaction: Объект взаимодействия Discord.
        user: Участник сервера, чья дата рождения удаляется.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    if str(user.id) in d.get("birthdays", {}):
        del d["birthdays"][str(user.id)]
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(
            f"🗑️ День рождения {user.mention} удалён.", ephemeral=True)
    else:
        await interaction.response.send_message(
            f"⚠️ У {user.mention} не зарегистрирован день рождения.", ephemeral=True)


@config_group.command(name="tz-override-set", description="[Админ] Установить часовой пояс указанному пользователю")
async def config_tz_override_set(interaction: discord.Interaction,
                                  user: discord.Member,
                                  tz_name: str) -> None:
    """Устанавливает личный часовой пояс указанному участнику сервера от имени администратора.

    Переопределяет серверный часовой пояс для конкретного пользователя.
    Поздравление будет отправлено в 06:00 по указанному поясу.

    Args:
        interaction: Объект взаимодействия Discord.
        user: Участник сервера, которому устанавливается часовой пояс.
        tz_name: Название таймзоны в формате IANA, например ``Europe/Moscow``.
    """
    try:
        zoneinfo.ZoneInfo(tz_name)
        d, all_d = get_guild_data(interaction.guild.id)
        if "user_timezones" not in d:
            d["user_timezones"] = {}
        d["user_timezones"][str(user.id)] = tz_name
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(
            f"✅ Часовой пояс {user.mention} установлен на `{tz_name}`.", ephemeral=True)
    except zoneinfo.ZoneInfoNotFoundError:
        await interaction.response.send_message("❌ Ошибка: Неверное имя таймзоны.", ephemeral=True)


@config_group.command(name="image", description="Ссылка на фон или 'local'")
async def config_image(interaction: discord.Interaction, url: str) -> None:
    """Устанавливает фоновое изображение для открыток.

    Args:
        interaction: Объект взаимодействия Discord.
        url: URL изображения или GIF, либо строка ``"local"`` для использования
            файла ``images/birthday_bg.png``.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    d["image_url"] = url
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message("✅ Фон обновлен!", ephemeral=True)


@birthday_group.command(name="set", description="Установить дату своего дня рождения")
async def birthday_set(interaction: discord.Interaction,
                       day: app_commands.Range[int, 1, 31],
                       month: app_commands.Range[int, 1, 12]) -> None:
    """Сохраняет дату дня рождения пользователя.

    Год не сохраняется — поздравление отправляется ежегодно.

    Args:
        interaction: Объект взаимодействия Discord.
        day: День рождения от 1 до 31.
        month: Месяц рождения от 1 до 12.
    """
    try:
        date_str = f"{day:02d}.{month:02d}"
        datetime.datetime.strptime(f"2000.{date_str}", "%Y.%d.%m")
        d, all_d = get_guild_data(interaction.guild.id)
        d["birthdays"][str(interaction.user.id)] = date_str
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(
            f"✅ Твой день рождения установлен на **{date_str}**!", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Указана несуществующая дата.", ephemeral=True)


@birthday_group.command(name="timezone", description="Установить свой личный часовой пояс (Europe/Moscow)")
async def birthday_timezone(interaction: discord.Interaction, tz_name: str) -> None:
    """Устанавливает личный часовой пояс пользователя.

    Переопределяет серверный часовой пояс для конкретного участника.
    Поздравление будет отправлено в 06:00 по указанному поясу.

    Args:
        interaction: Объект взаимодействия Discord.
        tz_name: Название таймзоны в формате IANA, например ``Asia/Tokyo``.
    """
    try:
        zoneinfo.ZoneInfo(tz_name)
        d, all_d = get_guild_data(interaction.guild.id)
        if "user_timezones" not in d:
            d["user_timezones"] = {}
        d["user_timezones"][str(interaction.user.id)] = tz_name
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(
            f"✅ Личный часовой пояс установлен на `{tz_name}`.", ephemeral=True)
    except zoneinfo.ZoneInfoNotFoundError:
        await interaction.response.send_message("❌ Ошибка: Неверное имя таймзоны.", ephemeral=True)


@birthday_group.command(name="remove", description="Удалить свой день рождения")
async def birthday_remove(interaction: discord.Interaction) -> None:
    """Удаляет данные о дне рождения пользователя с сервера.

    Args:
        interaction: Объект взаимодействия Discord.
    """
    d, all_d = get_guild_data(interaction.guild.id)
    if str(interaction.user.id) in d.get("birthdays", {}):
        del d["birthdays"][str(interaction.user.id)]
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message("🗑️ Твой день рождения удален.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Данные не найдены.", ephemeral=True)


@birthday_group.command(name="list", description="Показать список всех именинников сервера")
async def birthday_list(interaction: discord.Interaction) -> None:
    """Отображает список всех зарегистрированных именинников сервера.

    Список отсортирован по дате (по месяцу и дню). Показывается не более
    50 записей; при большем количестве добавляется отметка ``...``.

    Args:
        interaction: Объект взаимодействия Discord.

    Note:
        Для каждой записи проверяется, состоит ли пользователь ещё в
        гильдии (``guild.get_member``). Прямая вставка ``<@user_id>`` без
        этой проверки выглядела нормально для действующих участников (их
        клиент Discord резолвит ID в ник по своему кэшу), но для тех, кто
        покинул сервер или удалил аккаунт, рендерилась как нечитаемый
        сырой текст ``<@id>`` — Discord просто не может разрешить такой ID
        в отображаемое имя. Явная проверка через ``get_member`` заменяет
        такие записи понятной пометкой.
    """
    d, _ = get_guild_data(interaction.guild.id)
    birthdays = d.get("birthdays", {})
    if not birthdays:
        await interaction.response.send_message("📭 Список пуст.", ephemeral=True)
        return
    sorted_bdays = sorted(
        birthdays.items(),
        key=lambda item: (int(item[1].split('.')[1]), int(item[1].split('.')[0]))
    )
    lines = []
    for user_id, date in sorted_bdays[:50]:
        member = interaction.guild.get_member(int(user_id))
        who = member.mention if member else f"*участник покинул сервер* (`{user_id}`)"
        lines.append(f"**{date}** — {who}")
    description = "\n".join(lines) + ("\n\n*...*" if len(sorted_bdays) > 50 else "")
    await interaction.response.send_message(
        embed=discord.Embed(
            title="📅 Дни рождения сервера",
            description=description,
            color=discord.Color.blurple()
        )
    )


@birthday_group.command(name="test", description="[Админ] Проверить генерацию открытки")
async def birthday_test(interaction: discord.Interaction,
                        user2: discord.Member = None) -> None:
    """Генерирует и отправляет тестовую открытку без ожидания дня рождения.

    Доступно только администраторам сервера. Позволяет убедиться, что
    открытка выглядит корректно с текущими настройками.

    Args:
        interaction: Объект взаимодействия Discord.
        user2: Второй участник для проверки группового режима открытки.
            Если не указан — генерируется одиночная открытка.
    """
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        return await interaction.followup.send("❌ Только для администраторов.", ephemeral=True)

    guild_data, _ = get_guild_data(interaction.guild.id)

    users = [interaction.user]
    if user2:
        users.append(user2)

    avatars = []
    usernames = []
    for u in users:
        avatars.append(await u.display_avatar.replace(format="png", size=256).read())
        usernames.append(u.display_name)

    image_url = guild_data.get("image_url", "local")
    t_text, m_text = _pick_texts(guild_data, is_plural=len(users) > 1)
    bg_bytes = await _load_bg_bytes(image_url, bot.session)
    file, embeds = _build_card_message(avatars, usernames, bg_bytes, t_text, m_text, guild_data, image_url)

    await interaction.followup.send(content="*Тест оформления:*", embeds=embeds, file=file)


bot.tree.add_command(config_group)
bot.tree.add_command(birthday_group)


@bot.event
async def on_ready() -> None:
    """Вызывается когда бот успешно подключился к Discord и готов к работе."""
    logger.info("Бот %s подключён к Discord. Серверов: %d.", bot.user, len(bot.guilds))


TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    logger.error("Токен не найден! Убедись, что файл .env создан.")
else:
    bot.run(TOKEN)
