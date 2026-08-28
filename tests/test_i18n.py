"""5개 언어의 키·플레이스홀더가 완전히 일치하는지."""
import re

import i18n

PH = re.compile(r"\{(\w+)\}")


def test_all_languages_have_identical_key_sets():
    base = set(i18n.STRINGS["en"])
    for lang in i18n.SUPPORTED:
        keys = set(i18n.STRINGS[lang])
        assert keys == base, f"{lang}: missing={sorted(base - keys)} extra={sorted(keys - base)}"


def test_placeholders_match_english():
    for lang in i18n.SUPPORTED:
        for key, en in i18n.STRINGS["en"].items():
            assert set(PH.findall(en)) == set(PH.findall(i18n.STRINGS[lang][key])), f"{lang}.{key}"


def test_error_keys_used_by_code_exist():
    for key in ("err_redirect", "err_429", "err_network", "err_403", "err_host", "err_401", "err_http",
                "tt_next_try", "tos_note", "about_remove", "btn_open_logs"):
        assert key in i18n.STRINGS["en"]


def test_tr_error_formats_argument():
    i18n.set_language("en")
    assert i18n.tr_error("err_429 120") == "Rate limited (429) — retrying in 120s"
    assert i18n.tr_error("not a key") == "not a key"
