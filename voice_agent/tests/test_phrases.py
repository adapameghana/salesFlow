import pytest

from voice_agent.phrases import PHRASES, placeholders, render, split_sentences, static_sentences

SAMPLE = {"name": "Sri Sai Clinic", "business": "Dhanush Healthcare", "order": "seven",
          "amount": "four thousand rupees", "when": "tomorrow", "items": "five box gloves"}


def test_all_languages_have_same_keys():
    keys = set(PHRASES["en"])
    for lang, table in PHRASES.items():
        assert set(table) == keys, lang
        for key, template in table.items():
            assert placeholders(template) == placeholders(PHRASES["en"][key]), (lang, key)


@pytest.mark.parametrize("lang", list(PHRASES))
def test_render_leaves_no_placeholders(lang):
    for key, template in PHRASES[lang].items():
        values = {k: SAMPLE[k] for k in placeholders(template)}
        text = render(key, lang, **values)
        assert "{" not in text and "}" not in text and text.strip()


def test_missing_value_raises():
    with pytest.raises(KeyError):
        render("greet", "en", name="x")


def test_unknown_language_falls_back_to_english():
    assert render("goodbye", "fr") == PHRASES["en"]["goodbye"]


def test_native_scripts():
    assert any("ऀ" <= ch <= "ॿ" for ch in PHRASES["hi"]["greet"])
    assert any("ఀ" <= ch <= "౿" for ch in PHRASES["te"]["greet"])
    assert any("஀" <= ch <= "௿" for ch in PHRASES["ta"]["greet"])


def test_sentences():
    assert split_sentences("Hello. How are you? Fine!") == ["Hello.", "How are you?", "Fine!"]
    assert split_sentences("धन्यवाद। आप कब देंगे?") == ["धन्यवाद।", "आप कब देंगे?"]
    for lang in PHRASES:
        static = static_sentences(lang)
        assert static and all("{" not in s for s in static)
        assert PHRASES[lang]["ask_when"] in static
