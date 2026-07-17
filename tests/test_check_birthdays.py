import pytest
import datetime
import json
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
from conftest import make_png_bytes
import bot


FIXED_UTC = datetime.timezone.utc


def _guild_data(user_id, date_str, tz="UTC", channel_id=999):
    return {
        "111": {
            "channel_id": channel_id,
            "timezone": "UTC",
            "birthdays": {str(user_id): date_str},
            "user_timezones": {str(user_id): tz},
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


async def _run(b, data, now_utc, sent_log=None):
    """Вызывает check_birthdays с замороженным временем.

    ``sent_log``, если передан, мутируется кодом на месте (как и настоящий
    load_sent_log/save_sent_log), поэтому тест может проверить его после
    вызова через возвращаемый словарь.
    """
    if sent_log is None:
        sent_log = {}
    fake_card = BytesIO(make_png_bytes((1100, 480)))
    b.session = MagicMock()
    with patch.object(bot, 'load_data', return_value=data), \
         patch.object(bot, 'save_data') as mock_save, \
         patch.object(bot, 'load_sent_log', return_value=sent_log), \
         patch.object(bot, 'save_sent_log') as mock_save_sent, \
         patch('bot.create_birthday_card', return_value=fake_card), \
         patch('bot._load_bg_bytes', new=AsyncMock(return_value=None)), \
         patch('bot.datetime') as mock_dt:
        mock_dt.datetime.now.return_value = now_utc
        mock_dt.timezone.utc = FIXED_UTC
        await b.check_birthdays.coro(b)
    return mock_save, mock_save_sent, sent_log


class TestCheckBirthdays:
    async def test_congratulates_at_hour_6_utc(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        mock_save, mock_save_sent, sent_log = await _run(b, data, now)

        channel.send.assert_called_once()
        mock_save.assert_not_called()  # check_birthdays больше не трогает data.json
        mock_save_sent.assert_called_once()
        assert sent_log["111"]["42"] == 2026

    async def test_pings_everyone_not_the_birthday_person(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        await _run(b, data, now)

        content = channel.send.call_args.kwargs["content"]
        assert "@everyone" in content
        assert "<@42>" not in content

    async def test_skips_before_hour_6(self):
        now = datetime.datetime(2026, 6, 5, 3, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        _, mock_save_sent, _ = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save_sent.assert_not_called()

    async def test_congratulates_after_hour_6(self):
        """Bug fix: любой час >= 6 должен поздравлять, а не только ровно 6,
        чтобы даунтайм бота в 6-й час не пропускал поздравление на весь год."""
        now = datetime.datetime(2026, 6, 5, 10, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        _, mock_save_sent, sent_log = await _run(b, data, now)

        channel.send.assert_called_once()
        mock_save_sent.assert_called_once()
        assert sent_log["111"]["42"] == 2026

    async def test_skips_wrong_date(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "10.06", "UTC")  # birthday on 10th, not 5th
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        await _run(b, data, now)

        channel.send.assert_not_called()

    async def test_skips_already_sent_this_year(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel)
        sent_log = {"111": {"42": 2026}}

        _, mock_save_sent, _ = await _run(b, data, now, sent_log=sent_log)

        channel.send.assert_not_called()
        mock_save_sent.assert_not_called()

    async def test_legacy_sent_years_prevents_duplicate_after_migration(self):
        """Bug fix: до перехода на sent_log.json отметка "уже поздравлен"
        хранилась в guild_data["sent_years"] (data.json). При первом же
        запуске с новым кодом это должно быть перенесено в sent_log.json,
        иначе человек, уже поздравленный в этом году по старой схеме,
        получил бы поздравление повторно."""
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        data["111"]["sent_years"] = {"42": 2026}
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        _, mock_save_sent, sent_log = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save_sent.assert_called_once()
        assert sent_log["111"]["42"] == 2026

    async def test_resends_next_year(self):
        now = datetime.datetime(2027, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", "UTC")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))
        sent_log = {"111": {"42": 2026}}  # поздравляли в 2026, сейчас 2027

        _, _, sent_log = await _run(b, data, now, sent_log=sent_log)

        channel.send.assert_called_once()
        assert sent_log["111"]["42"] == 2027

    async def test_skips_no_channel_configured(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", channel_id=None)
        b = _make_bot()

        _, mock_save_sent, _ = await _run(b, data, now)

        mock_save_sent.assert_not_called()

    async def test_skips_channel_not_found(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        b = _make_bot(channel=None)  # get_channel returns None

        _, mock_save_sent, _ = await _run(b, data, now)

        mock_save_sent.assert_not_called()

    async def test_skips_guild_not_found(self):
        """Bug fix: guild=None не должен вызывать AttributeError."""
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=None)

        _, mock_save_sent, _ = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save_sent.assert_not_called()

    async def test_member_not_in_guild_skipped(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        guild = MagicMock()
        guild.get_member.return_value = None  # пользователь вышел с сервера
        b = _make_bot(channel=channel, guild=guild)

        _, mock_save_sent, _ = await _run(b, data, now)

        channel.send.assert_not_called()
        mock_save_sent.assert_not_called()

    async def test_marks_sent_log_after_congratulation(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        _, mock_save_sent, sent_log = await _run(b, data, now)

        mock_save_sent.assert_called_once()
        assert sent_log["111"]["42"] == 2026

    async def test_send_failure_does_not_mark_as_sent(self):
        """Bug fix: если отправка упала, поздравление не должно считаться
        отправленным — иначе именинник был бы пропущен навсегда без единого
        реального сообщения."""
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        channel = AsyncMock()
        channel.send.side_effect = RuntimeError("Discord API недоступен")
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        _, mock_save_sent, sent_log = await _run(b, data, now)

        mock_save_sent.assert_not_called()
        assert "111" not in sent_log or "42" not in sent_log.get("111", {})

    async def test_send_failure_in_one_guild_does_not_block_others(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = {
            "111": {
                "channel_id": 111, "timezone": "UTC",
                "birthdays": {"1": "05.06"}, "user_timezones": {},
                "image_url": "local", "title": "T", "message": "M",
                "plural_title": "PT", "plural_message": "PM",
                "color": "#FF5733", "color_title": "#00d4ff",
                "color_msg": "#c3d2eb", "color_name": "#ffffff",
                "font": "fonts/Jura-Bold.ttf",
            },
            "222": {
                "channel_id": 222, "timezone": "UTC",
                "birthdays": {"2": "05.06"}, "user_timezones": {},
                "image_url": "local", "title": "T", "message": "M",
                "plural_title": "PT", "plural_message": "PM",
                "color": "#FF5733", "color_title": "#00d4ff",
                "color_msg": "#c3d2eb", "color_name": "#ffffff",
                "font": "fonts/Jura-Bold.ttf",
            },
        }
        failing_channel = AsyncMock()
        failing_channel.send.side_effect = RuntimeError("boom")
        working_channel = AsyncMock()

        def get_channel(cid):
            return failing_channel if cid == 111 else working_channel

        b = _make_bot()
        b.get_channel = MagicMock(side_effect=get_channel)
        guild = MagicMock()
        guild.get_member.side_effect = lambda uid: _make_member(str(uid), f"User{uid}")
        b.get_guild = MagicMock(return_value=guild)

        _, mock_save_sent, sent_log = await _run(b, data, now)

        working_channel.send.assert_called_once()
        assert sent_log.get("222", {}).get("2") == 2026
        assert "1" not in sent_log.get("111", {})

    async def test_timezone_utc_plus3_fires_at_utc3(self):
        """Europe/Moscow (UTC+3): поздравить при UTC 03:00 (= московские 06:00)."""
        now = datetime.datetime(2026, 6, 5, 3, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", tz="Europe/Moscow")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        await _run(b, data, now)

        channel.send.assert_called_once()

    async def test_timezone_aware_still_fires_late_for_moscow_user(self):
        """Московский пользователь: UTC 06:00 = Moscow 09:00. Это позже 06:00
        по его поясу, так что поздравление всё равно должно уйти (догоняющая
        проверка на случай, если бот был недоступен ровно в 03:00 UTC)."""
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", tz="Europe/Moscow")
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        await _run(b, data, now)

        channel.send.assert_called_once()

    async def test_timezone_aware_no_fire_before_6am_for_moscow_user(self):
        """Московский пользователь: UTC 02:00 = Moscow 05:00, ещё рано."""
        now = datetime.datetime(2026, 6, 5, 2, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06", tz="Europe/Moscow")
        channel = AsyncMock()
        b = _make_bot(channel=channel)

        await _run(b, data, now)

        channel.send.assert_not_called()

    async def test_multiple_birthdays_same_day_sent_in_one_message(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = {
            "111": {
                "channel_id": 999,
                "timezone": "UTC",
                "birthdays": {"1": "05.06", "2": "05.06"},
                "user_timezones": {},
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

        _, mock_save_sent, sent_log = await _run(b, data, now)

        assert channel.send.call_count == 1  # одно сообщение на двоих
        mock_save_sent.assert_called_once()
        assert sent_log["111"]["1"] == 2026
        assert sent_log["111"]["2"] == 2026

    async def test_empty_data_no_errors(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        b = _make_bot()
        mock_save, mock_save_sent, _ = await _run(b, {}, now)
        mock_save.assert_not_called()
        mock_save_sent.assert_not_called()

    async def test_gif_background_sends_two_embeds(self):
        now = datetime.datetime(2026, 6, 5, 6, 0, 0, tzinfo=FIXED_UTC)
        data = _guild_data(42, "05.06")
        data["111"]["image_url"] = "https://example.com/bg.gif"
        channel = AsyncMock()
        b = _make_bot(channel=channel, guild=MagicMock(
            get_member=MagicMock(return_value=_make_member())))

        await _run(b, data, now)

        kwargs = channel.send.call_args.kwargs
        assert "embeds" in kwargs
        assert len(kwargs["embeds"]) == 2
