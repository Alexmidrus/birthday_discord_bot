import os
import sys
import json
import pytest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
from PIL import Image

os.environ.setdefault('DISCORD_TOKEN', '')

import bot


@pytest.fixture(autouse=True)
def project_root_cwd(monkeypatch):
    """Рабочая директория — корень проекта, чтобы fonts/ и images/ были доступны."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    monkeypatch.chdir(root)


@pytest.fixture
def tmp_data(tmp_path, monkeypatch):
    """Перенаправляет DATA_FILE во временный файл на время теста."""
    data_file = str(tmp_path / "data.json")
    monkeypatch.setattr(bot, 'DATA_FILE', data_file)
    return data_file


@pytest.fixture
def tmp_sent_log(tmp_path, monkeypatch):
    """Перенаправляет SENT_LOG_FILE во временный файл на время теста."""
    sent_log_file = str(tmp_path / "sent_log.json")
    monkeypatch.setattr(bot, 'SENT_LOG_FILE', sent_log_file)
    return sent_log_file


@pytest.fixture
def mock_interaction():
    interaction = MagicMock()
    interaction.guild.id = 123456789
    interaction.user.id = 987654321
    interaction.user.guild_permissions.administrator = True
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def make_png_bytes(size=(64, 64), color=(100, 150, 200)):
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    buf.seek(0)
    return buf.read()
