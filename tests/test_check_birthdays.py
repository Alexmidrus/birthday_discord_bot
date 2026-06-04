import pytest
import datetime
import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from conftest import make_png_bytes
import bot


FIXED_UTC = datetime.timezone.utc


def _guild_data(user_id, date_str, tz="UTC", sent_year=None, channel_id=999):
    return {
        "111": {
            "channel_id": channel_id,
            "timezone": "UTC",
            "birthdays": {str(user_id): date_str},
            "user_timezones": {str(user_id): tz},
            "sent_years": {str(user_id): sent_year} if sent_year else {},
            "image_url": "local",
            "title": "Title",
            "message": "Msg",
            "plural_title": "Title+",
            "plural_message": "Msg+",
            "color": "#FF5733",
            "color_title": "#00d4ff",
            "color_msg":   "#c3d2eb",
            "color_name":  "#ffffff",
            "font": "fonts/Jura-Bold.ttf",
        }
    }


def _make_member(uid="42", name="Alice"):
    member = MagicMock()
    member.display_name = name
    member.mention = f"<@{uid}>"
    av = AsyncMock()
    av.read = AsyncMock(return_value=make_png_bytes())
    member.display_avatar.replace.return_value = av
    return member


def _make_bot(channel=None, guild=None):
    b = bot.BirthdayBot()
    b.get_channel = MagicMock(return_value=channel or AsyncMock())
    b.get_guild = MagicMock(return_value=guild)
    return b


async def _run(b, data, now_utc):
    """Вызывает check_birthdays с замороженным временем."""
    fake_card = BytesIO(make_png_bytes((1100, 480)))
    b.session = MagicMock()
    with patch.object(bot, 'load_data', return_value=data), \
         patch.object(bot, 'save_data') as mock_save, \
         patch('bot.create_birthday_card', return_value=fake_card), \
         patch('bot._load_bg_bytes', new=AsyncMock(return_value=None)), \
         patch('bot.datetime') as mock_dt:
        mock_dt.datetime.now.return_value = now_utc
        mock_dt.timezone.utc = FIXED_UTC
        await b.check_birthdays.coro(b)
    return mock_save


class TestCheckBirthdays:
    async def test_congratulates_at_hour_6_utc(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        mock_save = await _run(b, data, now)

        channel.send.assert_called_once()
        mock_save.assert_called_once()

    async def test_skips_wrong_hour(self):
        now = datetime.datetime(2026, 6, 5, 10, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        mock_save = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save.assert_not_called()

    async def test_skips_wrong_date(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "10.06", "UTC")  # birthday on 10th, not 5th
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        mock_save = await _run(b, data, now)

        channel.send.assert_not_called()

    async def test_skips_already_sent_this_year(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC", sent_year=2026)
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        mock_save = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save.assert_not_called()

    async def test_resends_next_year(self):
        now = datetime.datetime(2027, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC", sent_year=2026)  # sent in 2026, now 2027
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        mock_save = await _run(b, data, now)

        channel.send.assert_called_once()

    async def test_skips_no_channel_configured(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", channel_id=None)
        b = _make_bot()

        mock_save = await _run(b, data, now)

        mock_save.assert_not_called()

    async def test_skips_channel_not_found(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        b = _make_bot(channel=None)  # get_channel returns None

        mock_save = await _run(b, data, now)

        mock_save.assert_not_called()

    async def test_skips_guild_not_found(self):
        """Bug fix: guild=None не должен вызывать AttributeError."""
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=None)

        mock_save = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save.assert_not_called()

    async def test_member_not_in_guild_skipped(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        guild = MagicMock()
        guild.get_member.return_value = None  # пользователь вышел с сервера
        b = _make_bot(channel=channel, guild=guild)

        mock_save = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save.assert_not_called()

    async def test_marks_sent_year_after_congratulation(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        mock_save = await _run(b, data, now)

        saved = mock_save.call_args.args[0]
        assert saved["111"]["sent_years"].get("42") == 2026

    async def test_timezone_utc_plus3_fires_at_utc3(self):
        """Europe/Moscow (UTC+3): поздравить при UTC 03:00 (= московские 06:00)."""
        now = datetime.datetime(2026, 6, 5, 3, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", tz="Europe/Moscow")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        mock_save = await _run(b, data, now)

        channel.send.assert_called_once()

    async def test_timezone_aware_no_fire_at_utc6_for_moscow_user(self):
        """Московский пользователь: UTC 06:00 = Moscow 09:00, не должно поздравлять."""
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", tz="Europe/Moscow")
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        mock_save = await _run(b, data, now)

        channel.send.assert_not_called()

    async def test_multiple_birthdays_same_day_sent_in_one_message(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = {
            "111": {
                "channel_id": 999,
                "timezone": "UTC",
                "birthdays": {"1": "05.06", "2": "05.06"},
                "user_timezones": {},
                "sent_years": {},
                "image_url": "local",
                "title": "T", "message": "M",
                "plural_title": "PT", "plural_message": "PM",
                "color": "#FF5733",
                "color_title": "#00d4ff", "color_msg": "#c3d2eb", "color_name": "#ffffff",
                "font": "fonts/Jura-Bold.ttf",
            }
        }
        channel = AsyncMock()
        guild = MagicMock()
        guild.get_member.side_effect = lambda uid: _make_member(str(uid), f"User{uid}")
        b = _make_bot(channel=channel, guild=guild)

        await _run(b, data, now)

        assert channel.send.call_count == 1  # одно сообщение на двоих

    async def test_empty_data_no_errors(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        b = _make_bot()
        mock_save = await _run(b, {}, now)
        mock_save.assert_not_called()

    async def test_gif_background_sends_two_embeds(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        data["111"]["image_url"] = "https://example.com/bg.gif"
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        fake_card = BytesIO(make_png_bytes((1100, 480)))
        b.session = MagicMock()
        with patch.object(bot, 'load_data', return_value=data), \
             patch.object(bot, 'save_data'), \
             patch('bot.create_birthday_card', return_value=fake_card), \
             patch('bot._load_bg_bytes', new=AsyncMock(return_value=None)), \
             patch('bot.datetime') as mock_dt:
            mock_dt.datetime.now.return_value = now
            mock_dt.timezone.utc = FIXED_UTC
            await b.check_birthdays.coro(b)

        kwargs = channel.send.call_args.kwargs
        assert "embeds" in kwargs
        assert len(kwargs["embeds"]) == 2
