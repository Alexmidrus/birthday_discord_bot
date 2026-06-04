import pytest
from PIL import Image, ImageDraw, ImageFont
from bot import hex_to_rgba, strip_emoji, wrap_text_to_pixels


class TestHexToRgba:
    def test_valid_hex(self):
        assert hex_to_rgba("#FF0000") == (255, 0, 0, 255)

    def test_valid_hex_lowercase(self):
        assert hex_to_rgba("#ffffff") == (255, 255, 255, 255)

    def test_without_hash(self):
        assert hex_to_rgba("0000FF") == (0, 0, 255, 255)

    def test_custom_alpha(self):
        assert hex_to_rgba("#00FF00", alpha=128) == (0, 255, 0, 128)

    def test_alpha_zero(self):
        assert hex_to_rgba("#123456", alpha=0) == (18, 52, 86, 0)

    def test_invalid_chars_returns_white(self):
        assert hex_to_rgba("ZZZZZZ") == (255, 255, 255, 255)

    def test_short_hex_returns_white(self):
        # 3-символьный HEX не поддерживается
        assert hex_to_rgba("#FFF") == (255, 255, 255, 255)

    def test_empty_string_returns_white(self):
        assert hex_to_rgba("") == (255, 255, 255, 255)

    def test_black(self):
        assert hex_to_rgba("#000000") == (0, 0, 0, 255)


class TestStripEmoji:
    def test_removes_birthday_emoji(self):
        result = strip_emoji("🎉 С Днем Рождения! 🎈")
        assert "🎉" not in result
        assert "🎈" not in result

    def test_keeps_plain_text(self):
        assert strip_emoji("BIRTHDAY PROTOCOL") == "BIRTHDAY PROTOCOL"

    def test_strips_leading_trailing_punctuation(self):
        assert strip_emoji("...test...") == "test"

    def test_strips_leading_dashes(self):
        assert strip_emoji("--hello--") == "hello"

    def test_empty_string(self):
        assert strip_emoji("") == ""

    def test_only_emoji_returns_empty(self):
        result = strip_emoji("🎂🎈🎉")
        assert result == ""

    def test_mixed_text_and_emoji(self):
        result = strip_emoji("Hello 🎂 World")
        assert "Hello" in result
        assert "World" in result


class TestWrapTextToPixels:
    @pytest.fixture
    def ctx(self):
        img = Image.new("RGBA", (2000, 2000))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()
        return draw, font

    def test_short_text_no_wrap(self, ctx):
        draw, font = ctx
        result = wrap_text_to_pixels("Hi", font, 500, draw)
        assert result == "Hi"

    def test_long_text_wraps_on_newline(self, ctx):
        draw, font = ctx
        result = wrap_text_to_pixels("word " * 50, font, 100, draw)
        assert "\n" in result

    def test_preserves_explicit_newlines(self, ctx):
        draw, font = ctx
        result = wrap_text_to_pixels("line1\nline2", font, 500, draw)
        assert "line1" in result
        assert "line2" in result

    def test_does_not_hang_on_tiny_width(self, ctx):
        """Защита от бесконечного цикла при очень малой ширине."""
        draw, font = ctx
        result = wrap_text_to_pixels("AAAA", font, 1, draw)
        assert isinstance(result, str)

    def test_empty_string(self, ctx):
        draw, font = ctx
        assert wrap_text_to_pixels("", font, 500, draw) == ""

    def test_single_word_fits(self, ctx):
        draw, font = ctx
        result = wrap_text_to_pixels("Test", font, 500, draw)
        assert result == "Test"

    def test_multiple_paragraphs(self, ctx):
        draw, font = ctx
        result = wrap_text_to_pixels("para1\npara2\npara3", font, 500, draw)
        assert result.count("\n") >= 2
