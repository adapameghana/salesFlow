"""The prepare tool must produce exactly the sentences a call will ask the TTS for."""
from datetime import date

from voice_agent.brain import Brain
from voice_agent.models import CallContext, Classification, OrderItem
from voice_agent.phrases import LANGS, split_sentences, static_sentences
from voice_agent.prepare import order_sentences

TODAY = date(2026, 10, 22)


def ctx(lang):
    return CallContext(order_id=7, order_number="ORD-2026-0007", customer_name="Sri Sai Clinic", language=lang,
                       balance=4250.0, business_name="Dhanush Healthcare", today=TODAY,
                       items=[OrderItem("Nitrile gloves M", 5, "box")])


def spoken(brain, reply):
    return split_sentences(reply.text)


def test_call_sentences_are_all_prepared():
    for lang in LANGS:
        c = ctx(lang)
        prepared = set(order_sentences(c, days=7)) | set(static_sentences(lang))
        said = []
        b = Brain(c, lambda *a: Classification(intent="ask_details"))
        said += spoken(b, b.greeting())
        said += spoken(b, b.on_customer("details please"))
        b2 = Brain(c, lambda *a: Classification(intent="will_pay", promised_date=date(2026, 10, 25)))
        b2.greeting()
        said += spoken(b2, b2.on_customer("I will pay on Sunday"))
        missing = [s for s in said if s not in prepared]
        assert not missing, (lang, missing)


def test_no_duplicates_and_no_static_sentences():
    out = order_sentences(ctx("te"))
    assert len(out) == len(set(out))
    assert not set(out) & set(static_sentences("te"))
