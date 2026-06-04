import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
import datetime
import aiohttp
import re
import random
import zoneinfo
from io import BytesIO
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageFilter

load_dotenv()

DATA_DIR   = "data"
DATA_FILE  = os.path.join(DATA_DIR, "data.json")
BG_IMAGE   = "images/birthday_bg.png"
FONTS_DIR  = "fonts"
DEFAULT_FONT = os.path.join(FONTS_DIR, "Jura-Bold.ttf")

os.makedirs(DATA_DIR, exist_ok=True)

# --- Утилиты ---
def hex_to_rgba(hex_color, alpha=255):
    """Конвертирует HEX (#FF00FF) в RGBA кортеж для Pillow."""
    hex_color = hex_color.lstrip('#')
    try:
        if len(hex_color) == 6:
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)) + (alpha,)
    except ValueError:
        pass
    return (255, 255, 255, alpha)

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "]+",
    flags=re.UNICODE,
)

def strip_emoji(text: str) -> str:
    """Убирает эмодзи, чтобы шрифты не рисовали квадратики-тофу."""
    return _EMOJI_RE.sub("", text).strip(" .-_")

def wrap_text_to_pixels(text, font, max_width, draw):
    """Разбивает текст на строки по ширине в пикселях."""
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


# --- Основной генератор открытки ---
def create_birthday_card(avatars_bytes: list, usernames: list, bg_bytes, title_text, message_text, guild_data):
    # ── ПАРАМЕТРЫ ХОЛСТА (Ширина фиксированная, Высота резиновая) ─────────────
    W = 1100
    base_H = 480
    divider_x = 320        
    av_cx = 185            
    
    # Расчет размеров аватарок (если именинников несколько - делаем их чуть меньше и ставим в столбик)
    avatars_count = len(avatars_bytes)
    avatar_size = 175 if avatars_count == 1 else 130
    avatar_spacing = 30
    avatars_total_h = avatars_count * avatar_size + (avatars_count - 1) * avatar_spacing

    tx = divider_x + 48      
    tw = W - tx - 36         

    # ── ЦВЕТОВАЯ ПАЛИТРА (С учетом настроек сервера) ──────────────────────────
    CYAN      = (0, 212, 255, 255)
    CYAN_160  = (0, 212, 255, 160)
    CYAN_80   = (0, 212, 255, 80)
    CYAN_38   = (0, 212, 255, 38)
    GOLD      = (255, 196, 0, 255)
    BG_COLOR  = (6, 10, 22, 255)

    # Кастомные цвета текста (подставляем дефолтные значения из старого дизайна)
    c_title = hex_to_rgba(guild_data.get("color_title", "#00d4ff"), 185) 
    c_name  = hex_to_rgba(guild_data.get("color_name", "#FFFFFF"), 255)
    c_msg   = hex_to_rgba(guild_data.get("color_msg", "#C3D2EB"), 220)

    font_path = guild_data.get("font", DEFAULT_FONT)

    # ── 1. ШРИФТЫ И ЗАМЕР КОНТЕНТА ────────────────────────────────────────────
    try:
        f_label  = ImageFont.truetype(font_path, 16)
        f_name   = ImageFont.truetype(font_path, 62)
        f_msg    = ImageFont.truetype(font_path, 26)
        f_status = ImageFont.truetype(font_path, 12)
    except IOError:
        f_label = f_name = f_msg = f_status = ImageFont.load_default()

    dummy = Image.new("RGBA", (2000, 2000))
    dd    = ImageDraw.Draw(dummy)

    # Метка
    label_raw = strip_emoji(title_text).upper().strip() or "BIRTHDAY PROTOCOL"
    lbl_wrap  = wrap_text_to_pixels(label_raw, f_label, tw, dd)
    lbl_h     = dd.multiline_textbbox((0, 0), lbl_wrap, font=f_label)[3]

    # Имена (перечисляем через запятую)
    names_str = ", ".join(usernames)
    name_w_px = dd.textbbox((0, 0), names_str, font=f_name)[2]
    
    # Автоподбор размера имени
    f_name_adj = f_name
    if name_w_px > tw:
        adj_size   = max(28, int(62 * tw / name_w_px))
        try:
            f_name_adj = ImageFont.truetype(font_path, adj_size)
        except IOError:
            pass
            
    names_wrap = wrap_text_to_pixels(names_str, f_name_adj, tw, dd)
    name_h     = dd.multiline_textbbox((0, 0), names_wrap, font=f_name_adj)[3]

    # Сообщение
    msg_wrap = wrap_text_to_pixels(message_text, f_msg, tw, dd)
    msg_h    = dd.multiline_textbbox((0, 0), msg_wrap, font=f_msg)[3]

    # Вычисление финальной высоты холста H (Адаптивность)
    G1, G2, G3 = 7, 10, 12
    text_block_h = lbl_h + G1 + name_h + G2 + 2 + G3 + msg_h
    
    # Выбираем максимальную высоту: либо базовые 480, либо высота по тексту, либо по аватаркам
    H = max(base_H, text_block_h + 80, avatars_total_h + 80)
    
    # Центровка
    text_start_y = max(40, (H - text_block_h) // 2)
    av_start_y = (H - avatars_total_h) // 2
    
    # Массив центров по Y для каждой аватарки
    avatar_centers_y = [av_start_y + (avatar_size // 2) + i * (avatar_size + avatar_spacing) for i in range(avatars_count)]

    # ── 2. ФОНОВЫЙ ХОЛСТ ──────────────────────────────────────────────────────
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

    # ── 3. СЛОЙ СВЕЧЕНИЯ АВАТАРОК ─────────────────────────────────────────────
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    for cy_i in avatar_centers_y:
        for extra, alpha in [(82, 18), (56, 34), (33, 58), (14, 100)]:
            r = (avatar_size + extra) // 2
            gd.ellipse([av_cx - r, cy_i - r, av_cx + r, cy_i + r], fill=(0, 212, 255, alpha))
            
    glow = glow.filter(ImageFilter.GaussianBlur(radius=14))
    card = Image.alpha_composite(card, glow)

    # ── 4. ДЕКОРАТИВНЫЙ СЛОЙ ──────────────────────────────────────────────────
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

    # ── 5. ОТРИСОВКА ТЕКСТА ───────────────────────────────────────────────────
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

    # Рассеянные звёзды
    rng = random.Random(42)
    for _ in range(int(H * 0.15)): # Количество звезд зависит от высоты
        sx = rng.randint(5, divider_x - 10)
        sy = rng.randint(5, H - 5)
        
        # Не рисуем поверх аватарок
        overlap = any(((sx - av_cx)**2 + (sy - cy_i)**2) ** 0.5 < (avatar_size // 2 + 22) for cy_i in avatar_centers_y)
        if overlap: continue
        
        alpha = rng.randint(25, 115)
        size  = rng.choice([0, 0, 1])
        d.ellipse([sx, sy, sx + size, sy + size], fill=(255, 255, 255, alpha))

    card = Image.alpha_composite(card, layer)

    # ── 6. ОТРИСОВКА АВАТАРОК ─────────────────────────────────────────────────
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


# --- Вспомогательные функции ---

def _pick_texts(guild_data: dict, is_plural: bool) -> tuple:
    if is_plural:
        title = guild_data.get("plural_title", guild_data.get("title", "🎉 С Днем Рождения! 🎈"))
        msg   = guild_data.get("plural_message", guild_data.get("message", "Поздравляем вас!"))
    else:
        title = guild_data.get("title", "🎉 С Днем Рождения! 🎈")
        msg   = guild_data.get("message", "Поздравляем тебя!")
    return title, msg


async def _load_bg_bytes(image_url: str, session: aiohttp.ClientSession) -> bytes | None:
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


def _build_card_message(avatars, usernames, bg_bytes, t_text, m_text, guild_data, image_url):
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


# --- КЛАСС БОТА И ДАННЫЕ ---
class BirthdayBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.session: aiohttp.ClientSession | None = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        self.check_birthdays.start()
        await self.tree.sync()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    @tasks.loop(hours=1)
    async def check_birthdays(self):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        current_year = now_utc.year
        all_data = load_data()
        changed = False

        for guild_id_str, guild_data in all_data.items():
            channel_id = guild_data.get("channel_id")
            if not channel_id: continue

            channel = self.get_channel(channel_id)
            if not channel: continue

            server_tz_str = guild_data.get("timezone", "UTC")
            if "sent_years" not in guild_data: guild_data["sent_years"] = {}
            if "user_timezones" not in guild_data: guild_data["user_timezones"] = {}

            to_congratulate = []

            for user_id_str, date_str in guild_data.get("birthdays", {}).items():
                if guild_data["sent_years"].get(user_id_str) == current_year:
                    continue

                user_tz_str = guild_data["user_timezones"].get(user_id_str, server_tz_str)
                try:
                    tz = zoneinfo.ZoneInfo(user_tz_str)
                except:
                    tz = zoneinfo.ZoneInfo("UTC")

                user_local_time = now_utc.astimezone(tz)

                if f"{user_local_time.day:02d}.{user_local_time.month:02d}" == date_str and user_local_time.hour == 6:
                    to_congratulate.append(user_id_str)

            if not to_congratulate:
                continue

            guild = self.get_guild(int(guild_id_str))
            if not guild:
                continue

            avatars, usernames, mentions = [], [], []

            for uid in to_congratulate:
                user = guild.get_member(int(uid))
                if user:
                    avatars.append(await user.display_avatar.replace(format="png", size=256).read())
                    usernames.append(user.display_name)
                    mentions.append(user.mention)
                    guild_data["sent_years"][uid] = current_year

            if not avatars: continue

            image_url = guild_data.get("image_url", "local")
            t_text, m_text = _pick_texts(guild_data, is_plural=len(avatars) > 1)
            bg_bytes = await _load_bg_bytes(image_url, self.session)
            file, embeds = _build_card_message(avatars, usernames, bg_bytes, t_text, m_text, guild_data, image_url)

            mention_str = " ".join(mentions)
            await channel.send(content=f"🎉 {mention_str}", embeds=embeds, file=file)

            all_data[guild_id_str] = guild_data
            changed = True

        if changed: save_data(all_data)

    @check_birthdays.before_loop
    async def before_check_birthdays(self):
        await self.wait_until_ready()
        await self.check_birthdays()
        now = datetime.datetime.now(datetime.timezone.utc)
        seconds_until_next_hour = 3600 - (now.minute * 60 + now.second)
        await asyncio.sleep(seconds_until_next_hour)


bot = BirthdayBot()

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r', encoding='utf-8') as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def get_guild_data(guild_id):
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
            "birthdays": {}, "user_timezones": {}, "sent_years": {}
        }
    return data[str(guild_id)], data


# --- КОМАНДЫ ---
@bot.tree.command(name="help", description="Справка по командам бота")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🎂 Birthday Bot Help", description="Я автоматически поздравляю участников сервера с днем рождения!\n\n"
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
                        "`/birthday test` — 🛠️ Проверить открытку", 
                        color=discord.Color.blurple())
    await interaction.response.send_message(embed=embed, ephemeral=True)


config_group = app_commands.Group(name="config", description="Настройки бота", default_permissions=discord.Permissions(administrator=True))
birthday_group = app_commands.Group(name="birthday", description="Управление днями рождения")

@config_group.command(name="channel", description="Установить канал для отправки поздравлений")
async def config_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    d, all_d = get_guild_data(interaction.guild.id)
    d["channel_id"] = channel.id
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Канал установлен: {channel.mention}", ephemeral=True)

@config_group.command(name="texts", description="Текст поздравления для 1 именинника")
async def config_texts(interaction: discord.Interaction, title: str = None, message: str = None):
    if not title and not message:
        await interaction.response.send_message("⚠️ Укажи хотя бы один параметр: `title` или `message`.", ephemeral=True)
        return
    d, all_d = get_guild_data(interaction.guild.id)
    if title: d["title"] = title
    if message: d["message"] = message
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message("✅ Тексты для одного именинника обновлены.", ephemeral=True)

@config_group.command(name="plural_texts", description="Текст поздравления для нескольких именинников в один день")
async def config_plural(interaction: discord.Interaction, title: str = None, message: str = None):
    if not title and not message:
        await interaction.response.send_message("⚠️ Укажи хотя бы один параметр: `title` или `message`.", ephemeral=True)
        return
    d, all_d = get_guild_data(interaction.guild.id)
    if title: d["plural_title"] = title
    if message: d["plural_message"] = message
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message("✅ Тексты для множественных дней рождения обновлены.", ephemeral=True)

@config_group.command(name="color_title", description="Цвет метки заголовка (HEX)")
async def config_color_title(interaction: discord.Interaction, hex_code: str):
    d, all_d = get_guild_data(interaction.guild.id)
    d["color_title"] = hex_code
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Цвет заголовка установлен на {hex_code}", ephemeral=True)

@config_group.command(name="color_msg", description="Цвет основного текста (HEX)")
async def config_color_msg(interaction: discord.Interaction, hex_code: str):
    d, all_d = get_guild_data(interaction.guild.id)
    d["color_msg"] = hex_code
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Цвет текста установлен на {hex_code}", ephemeral=True)

@config_group.command(name="color_name", description="Цвет имени (HEX)")
async def config_color_name(interaction: discord.Interaction, hex_code: str):
    d, all_d = get_guild_data(interaction.guild.id)
    d["color_name"] = hex_code
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Цвет имени установлен на {hex_code}", ephemeral=True)

@config_group.command(name="timezone", description="Глобальный часовой пояс (например, Europe/Moscow)")
async def config_timezone(interaction: discord.Interaction, tz_name: str):
    try:
        zoneinfo.ZoneInfo(tz_name)
        d, all_d = get_guild_data(interaction.guild.id)
        d["timezone"] = tz_name
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(f"✅ Глобальный часовой пояс установлен на `{tz_name}`.", ephemeral=True)
    except zoneinfo.ZoneInfoNotFoundError:
        await interaction.response.send_message("❌ Ошибка: Неверное имя таймзоны.", ephemeral=True)

@config_group.command(name="font", description="Имя файла шрифта .ttf из папки fonts/")
async def config_font(interaction: discord.Interaction, filename: str):
    if not filename.endswith('.ttf'): filename += '.ttf'
    font_path = os.path.join(FONTS_DIR, filename)
    if not os.path.exists(font_path):
        await interaction.response.send_message(f"❌ Файл `{filename}` не найден в папке `{FONTS_DIR}/`.", ephemeral=True)
        return
    d, all_d = get_guild_data(interaction.guild.id)
    d["font"] = font_path
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message(f"✅ Шрифт изменен на `{filename}`.", ephemeral=True)

@config_group.command(name="image", description="Ссылка на фон или 'local'")
async def config_image(interaction: discord.Interaction, url: str):
    d, all_d = get_guild_data(interaction.guild.id)
    d["image_url"] = url
    all_d[str(interaction.guild.id)] = d
    save_data(all_d)
    await interaction.response.send_message("✅ Фон обновлен!", ephemeral=True)


@birthday_group.command(name="set", description="Установить дату своего дня рождения")
async def birthday_set(interaction: discord.Interaction, day: app_commands.Range[int, 1, 31], month: app_commands.Range[int, 1, 12]):
    try:
        date_str = f"{day:02d}.{month:02d}"
        datetime.datetime.strptime(f"2000.{date_str}", "%Y.%d.%m")
        d, all_d = get_guild_data(interaction.guild.id)
        d["birthdays"][str(interaction.user.id)] = date_str
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(f"✅ Твой день рождения установлен на **{date_str}**!", ephemeral=True)
    except ValueError:
        await interaction.response.send_message("❌ Указана несуществующая дата.", ephemeral=True)

@birthday_group.command(name="timezone", description="Установить свой личный часовой пояс (Europe/Moscow)")
async def birthday_timezone(interaction: discord.Interaction, tz_name: str):
    try:
        zoneinfo.ZoneInfo(tz_name)
        d, all_d = get_guild_data(interaction.guild.id)
        if "user_timezones" not in d: d["user_timezones"] = {}
        d["user_timezones"][str(interaction.user.id)] = tz_name
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message(f"✅ Личный часовой пояс установлен на `{tz_name}`.", ephemeral=True)
    except zoneinfo.ZoneInfoNotFoundError:
        await interaction.response.send_message("❌ Ошибка: Неверное имя таймзоны.", ephemeral=True)

@birthday_group.command(name="remove", description="Удалить свой день рождения")
async def birthday_remove(interaction: discord.Interaction):
    d, all_d = get_guild_data(interaction.guild.id)
    if str(interaction.user.id) in d.get("birthdays", {}):
        del d["birthdays"][str(interaction.user.id)]
        all_d[str(interaction.guild.id)] = d
        save_data(all_d)
        await interaction.response.send_message("🗑️ Твой день рождения удален.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ Данные не найдены.", ephemeral=True)

@birthday_group.command(name="list", description="Показать список всех именинников сервера")
async def birthday_list(interaction: discord.Interaction):
    d, _ = get_guild_data(interaction.guild.id)
    birthdays = d.get("birthdays", {})
    if not birthdays:
        await interaction.response.send_message("📭 Список пуст.", ephemeral=True)
        return
    sorted_bdays = sorted(birthdays.items(), key=lambda item: (int(item[1].split('.')[1]), int(item[1].split('.')[0])))
    lines = [f"**{date}** — <@{user_id}>" for user_id, date in sorted_bdays[:50]]
    description = "\n".join(lines) + ("\n\n*...*" if len(sorted_bdays) > 50 else "")
    await interaction.response.send_message(embed=discord.Embed(title="📅 Дни рождения сервера", description=description, color=discord.Color.blurple()))

@birthday_group.command(name="test", description="[Админ] Проверить генерацию открытки")
async def birthday_test(interaction: discord.Interaction, user2: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    if not interaction.user.guild_permissions.administrator:
        return await interaction.followup.send("❌ Только для администраторов.", ephemeral=True)

    guild_data, _ = get_guild_data(interaction.guild.id)
    
    users = [interaction.user]
    if user2: users.append(user2)
    
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
async def on_ready():
    print(f'✅ Бот {bot.user} успешно подключен к Discord!')

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    print("❌ ОШИБКА: Токен не найден! Убедись, что файл .env создан.")
else:
    bot.run(TOKEN)