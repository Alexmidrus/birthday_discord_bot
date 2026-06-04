import pytest
import json
import bot


class TestLoadData:
    def test_returns_empty_dict_if_no_file(self, tmp_data):
        assert bot.load_data() == {}

    def test_loads_existing_json(self, tmp_data):
        payload = {"123": {"channel_id": 1, "birthdays": {}}}
        with open(tmp_data, 'w', encoding='utf-8') as f:
            json.dump(payload, f)
        assert bot.load_data() == payload

    def test_preserves_unicode(self, tmp_data):
        payload = {"1": {"message": "Поздравляем!"}}
        with open(tmp_data, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False)
        assert bot.load_data()["1"]["message"] == "Поздравляем!"


class TestSaveData:
    def test_saves_and_reloads(self, tmp_data):
        data = {"456": {"channel_id": 2, "birthdays": {}}}
        bot.save_data(data)
        assert bot.load_data() == data

    def test_overwrites_previous(self, tmp_data):
        bot.save_data({"a": 1})
        bot.save_data({"b": 2})
        assert bot.load_data() == {"b": 2}

    def test_saves_unicode(self, tmp_data):
        bot.save_data({"1": {"msg": "Привет"}})
        assert bot.load_data()["1"]["msg"] == "Привет"


class TestGetGuildData:
    def test_new_guild_gets_default_structure(self, tmp_data):
        d, all_d = bot.get_guild_data(999)
        assert "channel_id" in d
        assert "birthdays" in d
        assert "sent_years" in d
        assert "user_timezones" in d
        assert d["birthdays"] == {}

    def test_new_guild_stored_in_all_data(self, tmp_data):
        d, all_d = bot.get_guild_data(999)
        assert "999" in all_d

    def test_existing_guild_returned_unchanged(self, tmp_data):
        existing = {
            "999": {
                "channel_id": 42,
                "birthdays": {"1": "01.01"},
                "sent_years": {},
                "user_timezones": {},
            }
        }
        with open(tmp_data, 'w', encoding='utf-8') as f:
            json.dump(existing, f)
        d, _ = bot.get_guild_data(999)
        assert d["channel_id"] == 42
        assert d["birthdays"]["1"] == "01.01"

    def test_default_timezone_is_utc(self, tmp_data):
        d, _ = bot.get_guild_data(111)
        assert d["timezone"] == "UTC"

    def test_default_font_references_fonts_dir(self, tmp_data):
        d, _ = bot.get_guild_data(222)
        assert "fonts" in d["font"]

    def test_default_image_url_is_local(self, tmp_data):
        d, _ = bot.get_guild_data(333)
        assert d["image_url"] == "local"

    def test_different_guilds_are_isolated(self, tmp_data):
        d1, all_d = bot.get_guild_data(1)
        d1["channel_id"] = 100
        all_d["1"] = d1
        bot.save_data(all_d)

        d2, _ = bot.get_guild_data(2)
        assert d2["channel_id"] is None
