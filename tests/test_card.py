import pytest
from io import BytesIO
from PIL import Image
from conftest import make_png_bytes
from bot import create_birthday_card


GUILD_DATA = {
    "color_title": "#00d4ff",
    "color_msg":   "#c3d2eb",
    "color_name":  "#ffffff",
    "font":        "fonts/Jura-Bold.ttf",
}


class TestCreateBirthdayCard:
    def test_returns_bytesio(self):
        result = create_birthday_card(
            [make_png_bytes()], ["TestUser"], None,
            "Happy Birthday", "Congrats!", GUILD_DATA,
        )
        assert isinstance(result, BytesIO)

    def test_output_is_valid_png(self):
        result = create_birthday_card(
            [make_png_bytes()], ["TestUser"], None,
            "Happy Birthday", "Congrats!", GUILD_DATA,
        )
        img = Image.open(result)
        assert img.format == "PNG"

    def test_width_is_fixed_1100(self):
        result = create_birthday_card(
            [make_png_bytes()], ["Alice"], None, "T", "M", GUILD_DATA,
        )
        assert Image.open(result).width == 1100

    def test_height_at_least_480(self):
        result = create_birthday_card(
            [make_png_bytes()], ["Alice"], None, "T", "M", GUILD_DATA,
        )
        assert Image.open(result).height >= 480

    def test_multiple_avatars_produce_taller_card(self):
        single = create_birthday_card(
            [make_png_bytes()], ["Alice"], None, "T", "M", GUILD_DATA,
        )
        triple = create_birthday_card(
            [make_png_bytes(), make_png_bytes(), make_png_bytes()],
            ["Alice", "Bob", "Carol"], None, "T", "M", GUILD_DATA,
        )
        assert Image.open(triple).height > Image.open(single).height

    def test_with_background_image(self):
        result = create_birthday_card(
            [make_png_bytes()], ["TestUser"], make_png_bytes((1100, 480)),
            "T", "M", GUILD_DATA,
        )
        assert Image.open(result).format == "PNG"

    def test_corrupted_background_falls_back_gracefully(self):
        result = create_birthday_card(
            [make_png_bytes()], ["TestUser"], b"not_an_image",
            "T", "M", GUILD_DATA,
        )
        assert Image.open(result).format == "PNG"

    def test_corrupted_avatar_skipped_gracefully(self):
        result = create_birthday_card(
            [b"bad_avatar_data"], ["TestUser"], None,
            "T", "M", GUILD_DATA,
        )
        assert Image.open(result).format == "PNG"

    def test_long_username_shrinks_font(self):
        result = create_birthday_card(
            [make_png_bytes()], ["A" * 50], None,
            "T", "M", GUILD_DATA,
        )
        assert isinstance(result, BytesIO)

    def test_invalid_font_falls_back_to_default(self):
        data = {**GUILD_DATA, "font": "fonts/nonexistent_font.ttf"}
        result = create_birthday_card(
            [make_png_bytes()], ["TestUser"], None,
            "T", "M", data,
        )
        assert Image.open(result).format == "PNG"

    def test_long_message_expands_height(self):
        short_msg = create_birthday_card(
            [make_png_bytes()], ["Alice"], None, "T", "Short", GUILD_DATA,
        )
        long_msg = create_birthday_card(
            [make_png_bytes()], ["Alice"], None,
            "T", "Very long message. " * 20, GUILD_DATA,
        )
        assert Image.open(long_msg).height >= Image.open(short_msg).height

    def test_card_is_rgba(self):
        result = create_birthday_card(
            [make_png_bytes()], ["Alice"], None, "T", "M", GUILD_DATA,
        )
        assert Image.open(result).mode == "RGBA"
