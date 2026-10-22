from datetime import date

import pytest

from voice_agent.heuristics import classify_heuristic, find_date, find_paid_method

TODAY = date(2026, 10, 22)  # Thursday

# (lang, utterance, expected intent, expected promised_date or None)
UTTERANCES = [
    ("en", "I will pay tomorrow", "will_pay", date(2026, 10, 23)),
    ("en", "I already paid through GPay", "paid_claimed", None),
    ("en", "Which order is this? How much?", "ask_details", None),
    ("en", "I'm driving, call me later", "callback", None),
    ("en", "I never received the goods", "dispute", None),
    ("en", "Sorry, wrong number", "wrong_number", None),
    ("en", "Not interested, don't call again", "not_interested", None),
    ("en", "hmm okay", "other", None),
    ("en", "on Friday", "will_pay", date(2026, 10, 23)),
    ("hi", "मैं कल पेमेंट कर दूंगा", "will_pay", date(2026, 10, 23)),
    ("hi", "मैंने पेमेंट कर दिया है", "paid_claimed", None),
    ("hi", "कौन सा ऑर्डर? कितना बाकी है?", "ask_details", None),
    ("hi", "अभी बिज़ी हूँ, बाद में कॉल कीजिए", "callback", None),
    ("hi", "सामान नहीं मिला", "dispute", None),
    ("hi", "यह गलत नंबर है", "wrong_number", None),
    ("hi", "मुझे कॉल मत करो", "not_interested", None),
    ("hi", "परसों दे दूंगा", "will_pay", date(2026, 10, 24)),
    ("te", "రేపు కడతాను", "will_pay", date(2026, 10, 23)),
    ("te", "నేను ఇప్పటికే ఫోన్ పే లో కట్టేశాను", "paid_claimed", None),
    ("te", "ఏ ఆర్డర్? ఎంత?", "ask_details", None),
    ("te", "ఇప్పుడు బిజీ, తర్వాత కాల్ చేయండి", "callback", None),
    ("te", "సరుకు రాలేదు", "dispute", None),
    ("te", "ఇది రాంగ్ నంబర్", "wrong_number", None),
    ("te", "నాకు కాల్ చేయకండి", "not_interested", None),
    ("te", "శుక్రవారం చెల్లిస్తాను", "will_pay", date(2026, 10, 23)),
    ("ta", "நாளைக்கு கட்டுகிறேன்", "will_pay", date(2026, 10, 23)),
    ("ta", "நான் ஏற்கனவே கட்டிவிட்டேன்", "paid_claimed", None),
    ("ta", "எந்த ஆர்டர்? எவ்வளவு?", "ask_details", None),
    ("ta", "இப்போ பிஸி, பிறகு கால் பண்ணுங்க", "callback", None),
    ("ta", "பொருள் வரவில்லை", "dispute", None),
    ("ta", "இது தவறான எண்", "wrong_number", None),
    ("ta", "என்னை அழைக்க வேண்டாம்", "not_interested", None),
    ("ta", "சனிக்கிழமை செலுத்துவேன்", "will_pay", date(2026, 10, 24)),
]


@pytest.mark.parametrize("lang,text,intent,when", UTTERANCES)
def test_classify(lang, text, intent, when):
    c = classify_heuristic(text, lang, TODAY)
    assert c.intent == intent, text
    assert c.promised_date == when, text


def test_paid_details_defaults_to_paid():
    assert classify_heuristic("yesterday evening", "en", TODAY, "paid_details").intent == "paid_claimed"


def test_dates():
    assert find_date("day after tomorrow", TODAY) == date(2026, 10, 24)
    assert find_date("next week", TODAY) == date(2026, 10, 29)
    assert find_date("by month end", TODAY) == date(2026, 10, 31)
    assert find_date("on the 25th", TODAY) == date(2026, 10, 25)
    assert find_date("on the 5th", TODAY) == date(2026, 11, 5)  # already past this month
    assert find_date("5 November", TODAY) == date(2026, 11, 5)
    assert find_date("in 3 days", TODAY) == date(2026, 10, 25)
    assert find_date("Thursday", TODAY) == date(2026, 10, 29)  # same weekday means next week
    assert find_date("naalai", TODAY) == date(2026, 10, 23)
    assert find_date("repu", TODAY) == date(2026, 10, 23)
    assert find_date("I paid 4250", TODAY) is None
    # "kal" inside another Hindi word must not match
    assert find_date("निकल गया", TODAY) is None


def test_paid_method():
    assert find_paid_method("paid by UPI") == "UPI"
    assert find_paid_method("నగదు ఇచ్చాను") == "cash"
    assert find_paid_method("காசோலை கொடுத்தேன்") == "cheque"
    assert find_paid_method("nothing here") is None


def test_parser_date_beats_llm_date(monkeypatch):
    """Regression: qwen2.5:1.5b turned 'Friday' (today Thursday 2026-10-22) into Monday the 26th."""
    from datetime import date
    from voice_agent import llm
    from voice_agent.models import CallContext
    monkeypatch.setattr(llm, "_call_ollama", lambda *a, **k: {"intent": "will_pay", "promised_date": "2026-10-26"})
    ctx = CallContext(order_id=1, order_number="X", customer_name="", language="en", balance=1.0,
                      business_name="", today=date(2026, 10, 22))
    c = llm.OllamaClassifier("http://x", "m")("I will pay the amount on Friday.", ctx, "payment_answer")
    assert c.promised_date == date(2026, 10, 23)
