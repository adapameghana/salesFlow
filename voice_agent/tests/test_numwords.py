from datetime import date

import pytest

from voice_agent.numwords import (
    date_to_words, digits_to_words, number_to_words, quantity_to_words, rupees_to_words,
    when_to_words,
)

CASES = {
    "en": {4250: "four thousand two hundred fifty", 125000: "one lakh twenty-five thousand",
           10000000: "one crore", 0: "zero", 101: "one hundred one", 99: "ninety-nine",
           25_00_00_000: "twenty-five crore", 1_05_10_031: "one crore five lakh ten thousand thirty-one"},
    "hi": {4250: "चार हज़ार दो सौ पचास", 125000: "एक लाख पच्चीस हज़ार", 10000000: "एक करोड़",
           99: "निन्यानवे", 1999: "एक हज़ार नौ सौ निन्यानवे", 37: "सैंतीस"},
    "te": {4250: "నాలుగు వేల రెండు వందల యాభై", 125000: "ఒక లక్ష ఇరవై ఐదు వేలు",
           10000000: "ఒక కోటి", 100: "వంద", 150: "నూట యాభై", 2000: "రెండు వేలు",
           21: "ఇరవై ఒకటి", 300000: "మూడు లక్షలు"},
    "ta": {4250: "நான்காயிரத்து இருநூற்று ஐம்பது", 125000: "ஒரு லட்சத்து இருபத்து ஐந்து ஆயிரம்",
           10000000: "ஒரு கோடி", 100: "நூறு", 1000: "ஆயிரம்", 1500: "ஆயிரத்து ஐநூறு",
           45: "நாற்பத்து ஐந்து", 90: "தொண்ணூறு"},
}


@pytest.mark.parametrize("lang,n,expected", [(l, n, w) for l, c in CASES.items() for n, w in c.items()])
def test_number_to_words(lang, n, expected):
    assert number_to_words(n, lang) == expected


@pytest.mark.parametrize("lang", ["en", "hi", "te", "ta"])
def test_large_numbers_have_no_digits(lang):
    for n in (1, 19, 20, 99, 100, 999, 1001, 99_999, 1_00_000, 99_99_999, 1_00_00_000, 123_45_67_890):
        words = number_to_words(n, lang)
        assert words and not any(ch.isdigit() for ch in words), (n, words)


def test_rupees():
    assert rupees_to_words(4250.0, "en") == "four thousand two hundred fifty rupees"
    assert rupees_to_words(4249.6, "en") == "four thousand two hundred fifty rupees"
    assert rupees_to_words(1, "en") == "one rupee"
    assert rupees_to_words(4250, "hi") == "चार हज़ार दो सौ पचास रुपये"
    # Telugu uses the oblique form before a noun: వేల రూపాయలు, not వేలు రూపాయలు
    assert rupees_to_words(2000, "te") == "రెండు వేల రూపాయలు"
    assert rupees_to_words(125000, "te") == "ఒక లక్ష ఇరవై ఐదు వేల రూపాయలు"
    assert rupees_to_words(4250, "ta") == "நான்காயிரத்து இருநூற்று ஐம்பது ரூபாய்"


def test_quantity_and_digits():
    assert quantity_to_words(5.0, "en") == "five"
    assert quantity_to_words(2.5, "en") == "two point five"
    assert digits_to_words("0107", "en") == "zero one zero seven"


def test_dates():
    today = date(2026, 10, 22)
    assert when_to_words(date(2026, 10, 23), today, "en") == "tomorrow"
    assert when_to_words(date(2026, 10, 23), today, "te") == "రేపు"
    assert when_to_words(date(2026, 10, 24), today, "hi") == "परसों"
    assert when_to_words(date(2026, 10, 30), today, "en") == "on Friday, October thirty"
    assert date_to_words(date(2026, 10, 30), "hi") == "शुक्रवार, तीस अक्टूबर"
    assert when_to_words(date(2026, 10, 30), today, "ta").endswith("அன்று")
