"""macOS 키체인 자격증명 소스 — `security` 를 흉내 내어(실제 키체인·다이얼로그 없이) 파싱과 실패 경로를 검사한다."""
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from providers import claude_code as cc

OAUTH = {"claudeAiOauth": {"accessToken": "sk-ant-oat01-secret", "refreshToken": "sk-ant-ort01-x",
                           "expiresAt": 4102444800000, "subscriptionType": "max", "rateLimitTier": "default_claude_max_20x"}}


def fake_security(rc=0, stdout="", stderr="", raise_exc=None, calls=None):
    def _sec(args, timeout):
        if calls is not None:
            calls.append((list(args), timeout))
        if raise_exc:
            raise raise_exc
        return SimpleNamespace(returncode=rc, stdout=stdout, stderr=stderr)
    return _sec


@pytest.fixture
def mac(monkeypatch, tmp_path):
    """macOS 인 척: 기본 폴더 = tmp/.claude (파일 없음)."""
    cfg = tmp_path / ".claude"
    cfg.mkdir()
    monkeypatch.setattr(cc, "IS_MAC", True)
    monkeypatch.setattr(cc, "DEFAULT_CONFIG_DIR", str(cfg))
    return str(cfg)


def test_keychain_parses_secret_json(mac, monkeypatch):
    calls = []
    monkeypatch.setattr(cc, "_security", fake_security(0, json.dumps(OAUTH) + "\n", calls=calls))
    oauth = cc.read_oauth(mac)
    assert oauth["accessToken"] == "sk-ant-oat01-secret"
    assert calls == [(["find-generic-password", "-s", cc.KEYCHAIN_SERVICE, "-w"], cc.KEYCHAIN_TIMEOUT_SEC)]
    info = cc.ClaudeCode().info(mac)
    assert info["connected"] and info["plan"] == "Max (default_claude_max_20x)"
    assert info["path"].startswith("keychain:")                     # 파일이 아니라 키체인에서 읽었다는 표시


def test_file_wins_over_keychain(mac, monkeypatch):
    with open(os.path.join(mac, ".credentials.json"), "w", encoding="utf-8") as f:
        json.dump({"claudeAiOauth": {"accessToken": "from-file", "expiresAt": 4102444800000}}, f)
    monkeypatch.setattr(cc, "_security", fake_security(raise_exc=AssertionError("security must not be called")))
    assert cc.read_oauth(mac)["accessToken"] == "from-file"


def test_keychain_only_for_default_dir(mac, monkeypatch, tmp_path):
    other = tmp_path / ".claude-b"
    other.mkdir()
    monkeypatch.setattr(cc, "_security", fake_security(raise_exc=AssertionError("security must not be called")))
    with pytest.raises(RuntimeError, match="^err_no_token$"):
        cc.read_oauth(str(other))


def test_not_mac_never_calls_security(monkeypatch, tmp_path):
    monkeypatch.setattr(cc, "IS_MAC", False)
    monkeypatch.setattr(cc, "DEFAULT_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(cc, "_security", fake_security(raise_exc=AssertionError("security must not be called")))
    with pytest.raises(RuntimeError, match="^err_no_token$"):
        cc.read_oauth(str(tmp_path))
    assert cc.ClaudeCode().info(str(tmp_path))["reason"] == "err_no_token"      # Windows 동작 그대로


@pytest.mark.parametrize("rc,stderr,key", [
    (44, "security: SecKeychainSearchCopyNext: The specified item could not be found in the keychain.", "err_no_token"),
    (128, "security: SecKeychainItemCopyContent: User canceled the operation.", "err_keychain_denied"),
    (36, "security: SecKeychainItemCopyContent: User interaction is not allowed.", "err_keychain_denied"),
    (1, "some other failure", "err_keychain_read rc=1"),
])
def test_keychain_failures_map_to_i18n_keys(mac, monkeypatch, rc, stderr, key):
    monkeypatch.setattr(cc, "_security", fake_security(rc, "", stderr))
    with pytest.raises(RuntimeError) as ei:
        cc.read_oauth(mac)
    assert str(ei.value) == key
    assert cc.ClaudeCode().info(mac)["reason"] == key
    assert "some other failure" not in str(ei.value)                 # stderr 원문은 오류에 싣지 않는다


def test_pending_dialog_is_reported_not_crashed(mac, monkeypatch):
    monkeypatch.setattr(cc, "_security", fake_security(raise_exc=subprocess.TimeoutExpired("security", 90)))
    with pytest.raises(RuntimeError, match="^err_keychain_prompt$"):
        cc.ClaudeCode().fetch(mac)
    assert cc.ClaudeCode().info(mac)["reason"] == "err_keychain_prompt"


def test_garbage_secret_is_token_read_error(mac, monkeypatch):
    monkeypatch.setattr(cc, "_security", fake_security(0, "not json"))
    with pytest.raises(RuntimeError, match="^err_token_read "):
        cc.read_oauth(mac)


def test_discover_adds_default_dir_when_item_exists(mac, monkeypatch):
    calls = []
    monkeypatch.setattr(cc, "_security", fake_security(0, "", calls=calls))
    monkeypatch.setattr(os.path, "expanduser", lambda p: os.path.dirname(mac) if p == "~" else p)
    found = cc.ClaudeCode().discover()
    assert found == [os.path.abspath(mac)]
    assert all("-w" not in a for a, _ in calls)                       # 존재 확인은 비밀 값을 읽지 않는다 (다이얼로그 없음)


def test_discover_without_item(mac, monkeypatch):
    monkeypatch.setattr(cc, "_security", fake_security(44, "", "not found"))
    monkeypatch.setattr(os.path, "expanduser", lambda p: os.path.dirname(mac) if p == "~" else p)
    assert cc.ClaudeCode().discover() == []


def test_error_keys_exist_in_all_languages():
    import i18n
    for lang in i18n.SUPPORTED:
        for key in ("err_keychain_prompt", "err_keychain_denied", "err_keychain_read"):
            assert key in i18n.STRINGS[lang]
    i18n.set_language("en")
    assert "Always Allow" in i18n.tr_error("err_keychain_prompt")


def test_export_command_by_extension():
    assert cc.export_command("/x/statusline_export.sh") == '/bin/zsh "/x/statusline_export.sh"'
    assert cc.export_command("C:/x/statusline_export.ps1").startswith("powershell -NoProfile")
    assert cc._is_ours('/bin/zsh "/x/statusline_export.sh"') and cc._is_ours('powershell ... statusline_export.ps1')
    assert not cc._is_ours("bash $HOME/.claude/statusline-command.sh")
