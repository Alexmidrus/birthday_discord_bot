import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
import bot

# discord.py оборачивает команды в Command-объекты; тестируем через .callback
config_channel          = bot.config_channel.callback
config_texts            = bot.config_texts.callback
config_plural           = bot.config_plural.callback
config_color_title      = bot.config_color_title.callback
config_color_msg        = bot.config_color_msg.callback
config_color_name       = bot.config_color_name.callback
config_timezone         = bot.config_timezone.callback
config_font             = bot.config_font.callback
config_image            = bot.config_image.callback
config_bd_override_set    = bot.config_bd_override_set.callback
config_bd_override_remove = bot.config_bd_override_remove.callback
config_tz_override_set    = bot.config_tz_override_set.callback
birthday_set            = bot.birthday_set.callback
birthday_timezone       = bot.birthday_timezone.callback
birthday_remove         = bot.birthday_remove.callback
birthday_list           = bot.birthday_list.callback
birthday_test           = bot.birthday_test.callback
help_command            = bot.help_command.callback


def _sent_text(mock_interaction):
    """Возвращает строку первого аргумента из последнего вызова send_message."""
    args = mock_interaction.response.send_message.call_args
    if args.args:
        return args.args[0]
    return str(args)


class TestConfigChannel:
    async def test_sets_channel_id(self, mock_interaction, tmp_data):
        channel = MagicMock()
        channel.id = 555
        channel.mention = "#general"
        await config_channel(mock_interaction, channel)
        assert bot.load_data()["123456789"]["channel_id"] == 555

    async def test_responds_with_channel_mention(self, mock_interaction, tmp_data):
        channel = MagicMock()
        channel.id = 555
        channel.mention = "#general"
        await config_channel(mock_interaction, channel)
        assert "#general" in _sent_text(mock_interaction)


class TestConfigTexts:
    async def test_updates_title(self, mock_interaction, tmp_data):
        await config_texts(mock_interaction, title="New Title")
        assert bot.load_data()["123456789"]["title"] == "New Title"

    async def test_updates_message(self, mock_interaction, tmp_data):
        await config_texts(mock_interaction, message="New Msg")
        assert bot.load_data()["123456789"]["message"] == "New Msg"

    async def test_updates_both(self, mock_interaction, tmp_data):
        await config_texts(mock_interaction, title="T", message="M")
        d = bot.load_data()["123456789"]
        assert d["title"] == "T" and d["message"] == "M"

    async def test_no_params_warns(self, mock_interaction, tmp_data):
        await config_texts(mock_interaction)
        assert "⚠️" in _sent_text(mock_interaction)

    async def test_no_params_does_not_save(self, mock_interaction, tmp_data):
        await config_texts(mock_interaction)
        assert bot.load_data() == {}


class TestConfigPluralTexts:
    async def test_updates_plural_title(self, mock_interaction, tmp_data):
        await config_plural(mock_interaction, title="Plural T")
        assert bot.load_data()["123456789"]["plural_title"] == "Plural T"

    async def test_updates_plural_message(self, mock_interaction, tmp_data):
        await config_plural(mock_interaction, message="Plural M")
        assert bot.load_data()["123456789"]["plural_message"] == "Plural M"

    async def test_no_params_warns(self, mock_interaction, tmp_data):
        await config_plural(mock_interaction)
        assert "⚠️" in _sent_text(mock_interaction)


class TestConfigColors:
    async def test_color_title(self, mock_interaction, tmp_data):
        await config_color_title(mock_interaction, "#AABBCC")
        assert bot.load_data()["123456789"]["color_title"] == "#AABBCC"

    async def test_color_msg(self, mock_interaction, tmp_data):
        await config_color_msg(mock_interaction, "#112233")
        assert bot.load_data()["123456789"]["color_msg"] == "#112233"

    async def test_color_name(self, mock_interaction, tmp_data):
        await config_color_name(mock_interaction, "#FFFFFF")
        assert bot.load_data()["123456789"]["color_name"] == "#FFFFFF"

    async def test_responds_with_hex_code(self, mock_interaction, tmp_data):
        await config_color_title(mock_interaction, "#00FF00")
        assert "#00FF00" in _sent_text(mock_interaction)


class TestConfigTimezone:
    async def test_valid_timezone_saved(self, mock_interaction, tmp_data):
        await config_timezone(mock_interaction, "Europe/Moscow")
        assert bot.load_data()["123456789"]["timezone"] == "Europe/Moscow"

    async def test_utc_timezone(self, mock_interaction, tmp_data):
        await config_timezone(mock_interaction, "UTC")
        assert bot.load_data()["123456789"]["timezone"] == "UTC"

    async def test_invalid_timezone_returns_error(self, mock_interaction, tmp_data):
        await config_timezone(mock_interaction, "Invalid/Zone")
        assert "❌" in _sent_text(mock_interaction)

    async def test_invalid_timezone_not_saved(self, mock_interaction, tmp_data):
        await config_timezone(mock_interaction, "Fake/Timezone")
        assert bot.load_data() == {}


class TestConfigFont:
    async def test_valid_font_with_extension(self, mock_interaction, tmp_data):
        await config_font(mock_interaction, "Jura-Bold.ttf")
        assert "Jura-Bold.ttf" in bot.load_data()["123456789"]["font"]

    async def test_valid_font_without_extension(self, mock_interaction, tmp_data):
        await config_font(mock_interaction, "Jura-Bold")
        assert "Jura-Bold.ttf" in bot.load_data()["123456789"]["font"]

    async def test_font_stored_with_fonts_dir(self, mock_interaction, tmp_data):
        await config_font(mock_interaction, "Jura-Bold")
        assert bot.load_data()["123456789"]["font"].startswith("fonts")

    async def test_nonexistent_font_returns_error(self, mock_interaction, tmp_data):
        await config_font(mock_interaction, "nonexistent_font.ttf")
        assert "❌" in _sent_text(mock_interaction)

    async def test_nonexistent_font_not_saved(self, mock_interaction, tmp_data):
        await config_font(mock_interaction, "ghost.ttf")
        assert bot.load_data() == {}


class TestConfigImage:
    async def test_sets_url(self, mock_interaction, tmp_data):
        await config_image(mock_interaction, "https://example.com/bg.png")
        assert bot.load_data()["123456789"]["image_url"] == "https://example.com/bg.png"

    async def test_sets_local(self, mock_interaction, tmp_data):
        await config_image(mock_interaction, "local")
        assert bot.load_data()["123456789"]["image_url"] == "local"

    async def test_sets_gif_url(self, mock_interaction, tmp_data):
        await config_image(mock_interaction, "https://example.com/bg.gif")
        assert bot.load_data()["123456789"]["image_url"].endswith(".gif")


class TestBirthdaySet:
    async def test_valid_date_saved(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=15, month=6)
        assert bot.load_data()["123456789"]["birthdays"]["987654321"] == "15.06"

    async def test_date_zero_padded(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=1, month=1)
        assert bot.load_data()["123456789"]["birthdays"]["987654321"] == "01.01"

    async def test_invalid_date_31_feb_returns_error(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=31, month=2)
        assert "❌" in _sent_text(mock_interaction)

    async def test_invalid_date_not_saved(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=30, month=2)
        assert bot.load_data() == {}

    async def test_overwrites_existing_date(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=1, month=1)
        await birthday_set(mock_interaction, day=5, month=5)
        assert bot.load_data()["123456789"]["birthdays"]["987654321"] == "05.05"

    async def test_responds_with_set_date(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=20, month=3)
        assert "20.03" in _sent_text(mock_interaction)


class TestBirthdayTimezone:
    async def test_valid_timezone_saved(self, mock_interaction, tmp_data):
        await birthday_timezone(mock_interaction, "Asia/Tokyo")
        assert bot.load_data()["123456789"]["user_timezones"]["987654321"] == "Asia/Tokyo"

    async def test_invalid_timezone_returns_error(self, mock_interaction, tmp_data):
        await birthday_timezone(mock_interaction, "Fake/Zone")
        assert "❌" in _sent_text(mock_interaction)

    async def test_invalid_timezone_not_saved(self, mock_interaction, tmp_data):
        await birthday_timezone(mock_interaction, "Not/Real")
        assert bot.load_data() == {}

    async def test_updates_existing_timezone(self, mock_interaction, tmp_data):
        await birthday_timezone(mock_interaction, "UTC")
        await birthday_timezone(mock_interaction, "Europe/Moscow")
        assert bot.load_data()["123456789"]["user_timezones"]["987654321"] == "Europe/Moscow"


class TestBirthdayRemove:
    async def test_removes_existing_birthday(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=10, month=10)
        await birthday_remove(mock_interaction)
        assert "987654321" not in bot.load_data()["123456789"]["birthdays"]

    async def test_remove_nonexistent_warns(self, mock_interaction, tmp_data):
        await birthday_remove(mock_interaction)
        assert "⚠️" in _sent_text(mock_interaction)

    async def test_responds_with_trash_emoji(self, mock_interaction, tmp_data):
        await birthday_set(mock_interaction, day=1, month=6)
        await birthday_remove(mock_interaction)
        assert "🗑️" in _sent_text(mock_interaction)


class TestBirthdayList:
    async def test_empty_list_responds_with_empty_message(self, mock_interaction, tmp_data):
        await birthday_list(mock_interaction)
        assert "📭" in _sent_text(mock_interaction)

    async def test_non_empty_list_sends_embed(self, mock_interaction, tmp_data):
        data = {
            "123456789": {
                "channel_id": None,
                "timezone": "UTC",
                "birthdays": {"111": "01.06", "222": "15.03"},
                "sent_years": {},
                "user_timezones": {},
            }
        }
        with open(tmp_data, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        await birthday_list(mock_interaction)
        mock_interaction.response.send_message.assert_called_once()
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert "embed" in kwargs

    async def test_list_sorted_by_date(self, mock_interaction, tmp_data):
        data = {
            "123456789": {
                "channel_id": None, "timezone": "UTC",
                "birthdays": {"1": "15.12", "2": "01.01", "3": "05.06"},
                "sent_years": {}, "user_timezones": {},
            }
        }
        with open(tmp_data, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        await birthday_list(mock_interaction)
        embed = mock_interaction.response.send_message.call_args.kwargs["embed"]
        desc = embed.description
        assert desc.index("01.01") < desc.index("05.06") < desc.index("15.12")


class TestHelpCommand:
    async def test_help_sends_embed(self, mock_interaction):
        await help_command(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert "embed" in kwargs

    async def test_help_is_ephemeral(self, mock_interaction):
        await help_command(mock_interaction)
        kwargs = mock_interaction.response.send_message.call_args.kwargs
        assert kwargs.get("ephemeral") is True


class TestBirthdayTest:
    async def test_non_admin_gets_error(self, mock_interaction, tmp_data):
        mock_interaction.user.guild_permissions.administrator = False
        with patch('bot.create_birthday_card'):
            await birthday_test(mock_interaction)
        assert "❌" in str(mock_interaction.followup.send.call_args)

    async def test_generates_card_for_admin(self, mock_interaction, tmp_data):
        from io import BytesIO
        from conftest import make_png_bytes

        av = AsyncMock()
        av.read = AsyncMock(return_value=make_png_bytes())
        mock_interaction.user.display_avatar.replace.return_value = av
        bot.bot.session = MagicMock()

        with patch('bot.create_birthday_card', return_value=BytesIO(make_png_bytes((1100, 480)))), \
             patch('bot._load_bg_bytes', new=AsyncMock(return_value=None)):
            await birthday_test(mock_interaction)

        mock_interaction.followup.send.assert_called_once()

    async def test_test_with_second_user(self, mock_interaction, tmp_data):
        from io import BytesIO
        from conftest import make_png_bytes

        def _av():
            m = AsyncMock()
            m.read = AsyncMock(return_value=make_png_bytes())
            return m

        mock_interaction.user.display_avatar.replace.return_value = _av()
        user2 = MagicMock()
        user2.display_name = "Bob"
        user2.display_avatar.replace.return_value = _av()
        bot.bot.session = MagicMock()

        with patch('bot.create_birthday_card', return_value=BytesIO(make_png_bytes())) as mock_card, \
             patch('bot._load_bg_bytes', new=AsyncMock(return_value=None)):
            await birthday_test(mock_interaction, user2=user2)

        avatars = mock_card.call_args.args[0]
        assert len(avatars) == 2


def _make_target_user(user_id: int = 111222333) -> MagicMock:
    """Создаёт мок-участника сервера с заданным id."""
    user = MagicMock()
    user.id = user_id
    user.mention = f"<@{user_id}>"
    return user


class TestConfigBdOverrideSet:
    async def test_sets_birthday_for_target_user(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=10, month=5)
        assert bot.load_data()["123456789"]["birthdays"][str(target.id)] == "10.05"

    async def test_date_zero_padded(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=1, month=1)
        assert bot.load_data()["123456789"]["birthdays"][str(target.id)] == "01.01"

    async def test_overwrites_existing_birthday(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=1, month=1)
        await config_bd_override_set(mock_interaction, user=target, day=20, month=8)
        assert bot.load_data()["123456789"]["birthdays"][str(target.id)] == "20.08"

    async def test_invalid_date_returns_error(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=31, month=2)
        assert "❌" in _sent_text(mock_interaction)

    async def test_invalid_date_not_saved(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=30, month=2)
        assert bot.load_data() == {}

    async def test_success_response_contains_date(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=15, month=7)
        assert "15.07" in _sent_text(mock_interaction)

    async def test_does_not_affect_other_users(self, mock_interaction, tmp_data):
        target = _make_target_user(111)
        other = _make_target_user(222)
        await config_bd_override_set(mock_interaction, user=target, day=5, month=3)
        await config_bd_override_set(mock_interaction, user=other, day=9, month=9)
        data = bot.load_data()["123456789"]["birthdays"]
        assert data["111"] == "05.03"
        assert data["222"] == "09.09"


class TestConfigBdOverrideRemove:
    async def test_removes_existing_birthday(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=12, month=6)
        await config_bd_override_remove(mock_interaction, user=target)
        assert str(target.id) not in bot.load_data()["123456789"]["birthdays"]

    async def test_remove_nonexistent_warns(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_remove(mock_interaction, user=target)
        assert "⚠️" in _sent_text(mock_interaction)

    async def test_remove_nonexistent_does_not_crash(self, mock_interaction, tmp_data):
        target = _make_target_user()
        # Не должно бросать исключение
        await config_bd_override_remove(mock_interaction, user=target)

    async def test_success_response_contains_trash_emoji(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_bd_override_set(mock_interaction, user=target, day=1, month=1)
        await config_bd_override_remove(mock_interaction, user=target)
        assert "🗑️" in _sent_text(mock_interaction)

    async def test_removes_only_target_user(self, mock_interaction, tmp_data):
        t1 = _make_target_user(111)
        t2 = _make_target_user(222)
        await config_bd_override_set(mock_interaction, user=t1, day=1, month=1)
        await config_bd_override_set(mock_interaction, user=t2, day=2, month=2)
        await config_bd_override_remove(mock_interaction, user=t1)
        data = bot.load_data()["123456789"]["birthdays"]
        assert "111" not in data
        assert data["222"] == "02.02"


class TestConfigTzOverrideSet:
    async def test_valid_timezone_saved_for_target(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_tz_override_set(mock_interaction, user=target, tz_name="Europe/Moscow")
        assert bot.load_data()["123456789"]["user_timezones"][str(target.id)] == "Europe/Moscow"

    async def test_utc_timezone_saved(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_tz_override_set(mock_interaction, user=target, tz_name="UTC")
        assert bot.load_data()["123456789"]["user_timezones"][str(target.id)] == "UTC"

    async def test_overwrites_existing_timezone(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_tz_override_set(mock_interaction, user=target, tz_name="UTC")
        await config_tz_override_set(mock_interaction, user=target, tz_name="Asia/Tokyo")
        assert bot.load_data()["123456789"]["user_timezones"][str(target.id)] == "Asia/Tokyo"

    async def test_invalid_timezone_returns_error(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_tz_override_set(mock_interaction, user=target, tz_name="Invalid/Zone")
        assert "❌" in _sent_text(mock_interaction)

    async def test_invalid_timezone_not_saved(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_tz_override_set(mock_interaction, user=target, tz_name="Fake/TZ")
        assert bot.load_data() == {}

    async def test_success_response_contains_tz_name(self, mock_interaction, tmp_data):
        target = _make_target_user()
        await config_tz_override_set(mock_interaction, user=target, tz_name="Europe/London")
        assert "Europe/London" in _sent_text(mock_interaction)

    async def test_does_not_affect_other_users(self, mock_interaction, tmp_data):
        t1 = _make_target_user(111)
        t2 = _make_target_user(222)
        await config_tz_override_set(mock_interaction, user=t1, tz_name="UTC")
        await config_tz_override_set(mock_interaction, user=t2, tz_name="Asia/Tokyo")
        tzs = bot.load_data()["123456789"]["user_timezones"]
        assert tzs["111"] == "UTC"
        assert tzs["222"] == "Asia/Tokyo"
