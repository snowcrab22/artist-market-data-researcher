import os

from artistscore.config import load_dotenv


def test_load_dotenv_sets_missing_vars_only(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nLASTFM_API_KEY=abc123\nYOUTUBE_API_KEY="quoted"\n\nCONTACT_EMAIL = me@example.com\nBROKEN\n')
    monkeypatch.setenv("YOUTUBE_API_KEY", "already-set")
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    load_dotenv(env)
    assert os.environ["LASTFM_API_KEY"] == "abc123"
    assert os.environ["YOUTUBE_API_KEY"] == "already-set"
    assert os.environ["CONTACT_EMAIL"] == "me@example.com"


def test_load_dotenv_missing_file_is_noop(tmp_path):
    load_dotenv(tmp_path / "nope.env")
