import pytest

from groundtruth import sec

URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"


def test_download_without_a_declared_user_agent_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(sec.USER_AGENT_VARIABLE, raising=False)
    with pytest.raises(RuntimeError, match=sec.USER_AGENT_VARIABLE):
        sec.get_text(URL, tmp_path)


def test_cached_responses_need_no_user_agent(tmp_path, monkeypatch):
    monkeypatch.delenv(sec.USER_AGENT_VARIABLE, raising=False)
    (tmp_path / sec._cache_path(URL).name).write_text('{"cik": 1}')
    assert sec.get_json(URL, tmp_path) == {"cik": 1}


def test_user_agent_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(sec.USER_AGENT_VARIABLE, "Example Person person@example.com")
    assert sec.user_agent() == "Example Person person@example.com"
