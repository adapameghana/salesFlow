from datetime import date

import pytest

from voice_agent.brain import Brain, State, spoken_items, spoken_order_number
from voice_agent.heuristics import classify_heuristic
from voice_agent.models import Classification

from .conftest import TODAY, make_ctx

LANGS = ["en", "hi", "te", "ta"]


def heuristic(text, ctx, expecting):
    return classify_heuristic(text, ctx.language, ctx.today, expecting)


class Scripted:
    """Fake classifier: returns pre-set classifications in order, records calls."""

    def __init__(self, *results: Classification):
        self.results = list(results)
        self.calls = []

    def __call__(self, text, ctx, expecting):
        self.calls.append((text, expecting))
        return self.results.pop(0)


def C(intent, when=None, method=None):
    return Classification(intent=intent, promised_date=when, paid_method=method, note=f"said {intent}")


def no_placeholders(text):
    return "{" not in text and "}" not in text


# Native-language customer lines per intent (what Whisper would return).
LINES = {
    "en": {"will_pay": "I will pay tomorrow", "paid": "I already paid", "paid_how": "by UPI yesterday",
           "details": "which order is this?", "callback": "I am busy, call me later",
           "dispute": "I never received the goods", "wrong": "wrong number",
           "not_interested": "not interested, don't call", "will_pay_nodate": "I will pay",
           "date": "on Friday", "unclear": "hmm"},
    "hi": {"will_pay": "कल कर दूंगा", "paid": "पेमेंट कर दिया", "paid_how": "गूगल पे से",
           "details": "कौन सा ऑर्डर?", "callback": "बिज़ी हूँ, बाद में कॉल करना",
           "dispute": "सामान नहीं मिला", "wrong": "गलत नंबर है", "not_interested": "कॉल मत करो",
           "will_pay_nodate": "दे दूंगा", "date": "शुक्रवार को", "unclear": "हाँ"},
    "te": {"will_pay": "రేపు కడతాను", "paid": "కట్టేశాను", "paid_how": "ఫోన్ పే లో",
           "details": "ఏ ఆర్డర్?", "callback": "బిజీ, తర్వాత కాల్ చేయండి", "dispute": "సరుకు రాలేదు",
           "wrong": "రాంగ్ నంబర్", "not_interested": "కాల్ చేయకండి", "will_pay_nodate": "చెల్లిస్తాను",
           "date": "శుక్రవారం", "unclear": "అవును"},
    "ta": {"will_pay": "நாளைக்கு கட்டுகிறேன்", "paid": "கட்டிவிட்டேன்", "paid_how": "கூகுள் பே மூலம்",
           "details": "எந்த ஆர்டர்?", "callback": "பிஸி, பிறகு கால் பண்ணுங்க", "dispute": "பொருள் வரவில்லை",
           "wrong": "தவறான எண்", "not_interested": "அழைக்க வேண்டாம்", "will_pay_nodate": "செலுத்துவேன்",
           "date": "வெள்ளிக்கிழமை", "unclear": "ஆமாம்"},
}


def run(lang, *lines):
    brain = Brain(make_ctx(lang), heuristic)
    replies = [brain.greeting()]
    for line in lines:
        replies.append(brain.on_customer(line) if line is not None else brain.on_silence())
    for r in replies:
        assert no_placeholders(r.text)
    return brain, replies


@pytest.mark.parametrize("lang", LANGS)
def test_greeting_contains_amount_in_words(lang):
    brain = Brain(make_ctx(lang), heuristic)
    g = brain.greeting().text
    expected = {"en": "four thousand two hundred fifty rupees", "hi": "चार हज़ार दो सौ पचास रुपये",
                "te": "నాలుగు వేల రెండు వందల యాభై రూపాయలు",
                "ta": "நான்காயிரத்து இருநூற்று ஐம்பது ரூபாய்"}[lang]
    assert expected in g.lower() if lang == "en" else expected in g
    assert "Sri Sai Clinic" in g and "Dhanush Healthcare" in g
    assert not any(ch.isdigit() for ch in g)


@pytest.mark.parametrize("lang", LANGS)
def test_will_pay_with_date(lang):
    brain, replies = run(lang, LINES[lang]["will_pay"])
    assert brain.done and replies[-1].end and not replies[-1].interruptible
    assert brain.intent == "will_pay" and brain.promised_date == date(2026, 10, 23)
    assert {"en": "tomorrow", "hi": "कल", "te": "రేపు", "ta": "நாளை"}[lang] in replies[-1].text


@pytest.mark.parametrize("lang", LANGS)
def test_will_pay_asks_for_date_once(lang):
    brain, replies = run(lang, LINES[lang]["will_pay_nodate"], LINES[lang]["date"])
    assert brain.intent == "will_pay" and brain.promised_date == date(2026, 10, 23)
    assert brain.done


@pytest.mark.parametrize("lang", LANGS)
def test_will_pay_without_date_after_asking(lang):
    brain, _ = run(lang, LINES[lang]["will_pay_nodate"], LINES[lang]["unclear"])
    assert brain.done and brain.intent == "will_pay" and brain.promised_date is None


@pytest.mark.parametrize("lang", LANGS)
def test_paid_claimed_one_follow_up(lang):
    brain, replies = run(lang, LINES[lang]["paid"], LINES[lang]["paid_how"])
    assert not replies[1].end  # asked how/when
    assert brain.done and brain.intent == "paid_claimed" and brain.promised_date is None
    assert brain.paid_method == "UPI"


@pytest.mark.parametrize("lang", LANGS)
def test_ask_details_then_will_pay(lang):
    brain, replies = run(lang, LINES[lang]["details"], LINES[lang]["will_pay"])
    details = replies[1]
    assert not details.end
    assert "Nitrile gloves M" in details.text
    assert {"en": "five", "hi": "पाँच", "te": "ఐదు", "ta": "ஐந்து"}[lang] in details.text
    assert brain.done and brain.intent == "will_pay"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("key,intent", [("callback", "callback"), ("dispute", "dispute"),
                                        ("wrong", "wrong_number"), ("not_interested", "not_interested")])
def test_closing_intents(lang, key, intent):
    brain, replies = run(lang, LINES[lang][key])
    assert brain.done and brain.intent == intent and replies[-1].end


@pytest.mark.parametrize("lang", LANGS)
def test_other_gets_one_more_chance(lang):
    brain, replies = run(lang, LINES[lang]["unclear"], LINES[lang]["unclear"])
    assert not replies[1].end
    assert brain.done and brain.intent == "other"


@pytest.mark.parametrize("lang", LANGS)
def test_no_response(lang):
    brain, replies = run(lang, None, None)
    assert not replies[1].end  # reprompt
    assert replies[2].end and brain.intent == "no_response"


def test_silence_resets_after_speech():
    brain, replies = run("en", None, "which order?", None)
    assert not brain.done  # silence counter reset by the customer speaking


def test_turn_cap():
    clf = Scripted(*[C("ask_details")] * 4)
    brain = Brain(make_ctx("en"), clf, max_turns=4)
    brain.greeting()
    replies = [brain.on_customer(f"q{i}") for i in range(4)]
    assert [r.end for r in replies] == [False, False, False, True]
    assert brain.intent == "ask_details"


def test_scripted_flow_and_expectations():
    clf = Scripted(C("will_pay"), C("will_pay", date(2026, 10, 30)))
    brain = Brain(make_ctx("en"), clf)
    brain.greeting()
    assert brain.on_customer("I'll pay").text.startswith("Sure.")
    assert brain.state == State.DATE
    final = brain.on_customer("on the 30th")
    assert "on Friday, October thirty" in final.text
    assert [e for _, e in clf.calls] == ["payment_answer", "date"]
    out = brain.outcome()
    assert out.promised_date == date(2026, 10, 30)
    assert "2026-10-30" in out.summary


def test_paid_with_method_skips_follow_up():
    brain = Brain(make_ctx("en"), Scripted(C("paid_claimed", method="cash")))
    brain.greeting()
    assert brain.on_customer("paid cash").end
    assert "cash" in brain.summary()


def test_timeout_and_hangup():
    brain = Brain(make_ctx("en"), heuristic)
    brain.greeting()
    r = brain.on_timeout()
    assert r.end and brain.intent == "no_response" and "time limit" in brain.summary()
    brain2 = Brain(make_ctx("hi"), heuristic)
    brain2.greeting()
    brain2.on_customer("कौन सा ऑर्डर?")
    brain2.on_hangup()
    assert brain2.done and brain2.intent == "ask_details" and "hung up" in brain2.summary()


def test_missing_name_and_many_items():
    items = [{"name": f"Item {i}", "quantity": i + 1, "unit": "box"} for i in range(6)]
    ctx = make_ctx("te", customer_name="", items=items)
    g = Brain(ctx, heuristic).greeting().text
    assert "గారు" not in g and "  " not in g
    spoken = spoken_items(ctx)
    assert "Item 3" in spoken and "Item 4" not in spoken and "ఇతర వస్తువులు" in spoken


def test_spoken_order_number():
    assert spoken_order_number("ORD-2026-0007", "en") == "seven"
    assert spoken_order_number("ORD-2026-0123", "en") == "one two three"
    assert spoken_order_number("ABC", "en") == "ABC"
    assert TODAY.weekday() == 3
