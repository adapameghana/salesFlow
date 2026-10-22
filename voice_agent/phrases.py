"""Fixed agent phrases per language.

Placeholders are only ever filled from the call context (via brain.py), so the
agent can never invent amounts, dates or offers. Amounts and dates arrive
already spelled as words (numwords.py).
"""
from __future__ import annotations

import re
import string

PHRASES: dict[str, dict[str, str]] = {
    "en": {
        "greet": "Hello {name}, this is {business} calling about your order number {order}. "
                 "{amount} is still pending. When will you be able to make the payment?",
        "ask_when": "When will you be able to make the payment?",
        "ask_paid_how": "Thank you. How and when did you make the payment?",
        "paid_thanks": "Thank you for the payment. Our team will verify it and update your order.",
        "will_pay_confirm": "Thank you, we'll note that you'll pay {when}.",
        "ask_date": "Sure. On which date will you be able to pay?",
        "will_pay_no_date": "Thank you, we'll note that you will pay soon.",
        "details": "Your order number {order} has {items}. The pending amount is {amount}.",
        "callback": "Thank you. Our team will call you back shortly.",
        "wrong_number": "Sorry for the trouble. We will not call this number again.",
        "not_interested": "Sorry to have disturbed you. We will not call you again about this.",
        "reprompt": "Sorry, I couldn't hear you. When will you be able to make the payment?",
        "not_understood": "Sorry, I didn't catch that. When will you be able to make the payment?",
        "no_response": "We could not hear you, so we will try again later.",
        "time_up": "We have to end the call now. Our team will call you back if needed.",
        "goodbye": "Thank you, have a nice day. Goodbye.",
        "and": "and",
        "more_items": "other items",
    },
    "hi": {
        "greet": "नमस्ते {name} जी, मैं {business} से आपके ऑर्डर नंबर {order} के बारे में बात कर रही हूँ। "
                 "आपका {amount} का भुगतान अभी बाकी है। आप भुगतान कब तक कर पाएँगे?",
        "ask_when": "आप भुगतान कब तक कर पाएँगे?",
        "ask_paid_how": "धन्यवाद। आपने भुगतान कैसे और कब किया था?",
        "paid_thanks": "भुगतान के लिए धन्यवाद। हमारी टीम इसकी जाँच करके आपका ऑर्डर अपडेट कर देगी।",
        "will_pay_confirm": "धन्यवाद, हमने नोट कर लिया है कि आप {when} भुगतान करेंगे।",
        "ask_date": "ठीक है। आप किस तारीख तक भुगतान कर पाएँगे?",
        "will_pay_no_date": "धन्यवाद, हमने नोट कर लिया है कि आप जल्द ही भुगतान करेंगे।",
        "details": "आपके ऑर्डर नंबर {order} में {items} है। बाकी राशि {amount} है।",
        "callback": "धन्यवाद। हमारी टीम जल्द ही आपको वापस कॉल करेगी।",
        "wrong_number": "असुविधा के लिए क्षमा कीजिए। हम इस नंबर पर दोबारा कॉल नहीं करेंगे।",
        "not_interested": "परेशानी के लिए क्षमा कीजिए। हम इस बारे में आपको दोबारा कॉल नहीं करेंगे।",
        "reprompt": "माफ़ कीजिए, आपकी आवाज़ नहीं आई। आप भुगतान कब तक कर पाएँगे?",
        "not_understood": "माफ़ कीजिए, मैं समझ नहीं पाई। आप भुगतान कब तक कर पाएँगे?",
        "no_response": "आपकी आवाज़ नहीं आ रही है, हम बाद में फिर कॉल करेंगे।",
        "time_up": "अब हमें कॉल समाप्त करनी होगी। ज़रूरत होने पर हमारी टीम आपको वापस कॉल करेगी।",
        "goodbye": "धन्यवाद, आपका दिन शुभ हो। नमस्ते।",
        "and": "और",
        "more_items": "अन्य सामान",
    },
    "te": {
        "greet": "నమస్కారం {name} గారు, నేను {business} నుండి మీ ఆర్డర్ నంబర్ {order} గురించి మాట్లాడుతున్నాను. "
                 "మీరు ఇంకా {amount} చెల్లించవలసి ఉంది. మీరు ఎప్పుడు చెల్లించగలరు?",
        "ask_when": "మీరు ఎప్పుడు చెల్లించగలరు?",
        "ask_paid_how": "ధన్యవాదాలు. మీరు ఎలా, ఎప్పుడు చెల్లించారు?",
        "paid_thanks": "చెల్లింపుకు ధన్యవాదాలు. మా టీమ్ దాన్ని పరిశీలించి మీ ఆర్డర్‌ను అప్‌డేట్ చేస్తుంది.",
        "will_pay_confirm": "ధన్యవాదాలు, మీరు {when} చెల్లిస్తారని నోట్ చేసుకున్నాము.",
        "ask_date": "సరే. మీరు ఏ తేదీన చెల్లించగలరు?",
        "will_pay_no_date": "ధన్యవాదాలు, మీరు త్వరలో చెల్లిస్తారని నోట్ చేసుకున్నాము.",
        "details": "మీ ఆర్డర్ నంబర్ {order} లో {items} ఉన్నాయి. చెల్లించవలసిన మొత్తం {amount}.",
        "callback": "ధన్యవాదాలు. మా టీమ్ త్వరలో మీకు మళ్ళీ కాల్ చేస్తుంది.",
        "wrong_number": "ఇబ్బందికి క్షమించండి. ఈ నంబర్‌కు మళ్ళీ కాల్ చేయము.",
        "not_interested": "ఇబ్బంది కలిగించినందుకు క్షమించండి. దీని గురించి మీకు మళ్ళీ కాల్ చేయము.",
        "reprompt": "క్షమించండి, మీ మాట వినిపించలేదు. మీరు ఎప్పుడు చెల్లించగలరు?",
        "not_understood": "క్షమించండి, నాకు అర్థం కాలేదు. మీరు ఎప్పుడు చెల్లించగలరు?",
        "no_response": "మీ మాట వినిపించడం లేదు, మేము తర్వాత మళ్ళీ కాల్ చేస్తాము.",
        "time_up": "ఇప్పుడు కాల్ ముగించాలి. అవసరమైతే మా టీమ్ మీకు మళ్ళీ కాల్ చేస్తుంది.",
        "goodbye": "ధన్యవాదాలు, మీ రోజు శుభంగా గడవాలి. నమస్కారం.",
        "and": "మరియు",
        "more_items": "ఇతర వస్తువులు",
    },
    "ta": {
        "greet": "வணக்கம் {name}, நான் {business} இலிருந்து உங்கள் ஆர்டர் எண் {order} பற்றி பேசுகிறேன். "
                 "இன்னும் {amount} செலுத்த வேண்டியுள்ளது. நீங்கள் எப்போது பணம் செலுத்த முடியும்?",
        "ask_when": "நீங்கள் எப்போது பணம் செலுத்த முடியும்?",
        "ask_paid_how": "நன்றி. நீங்கள் எப்படி, எப்போது பணம் செலுத்தினீர்கள்?",
        "paid_thanks": "பணம் செலுத்தியதற்கு நன்றி. எங்கள் குழு அதைச் சரிபார்த்து உங்கள் ஆர்டரைப் புதுப்பிக்கும்.",
        "will_pay_confirm": "நன்றி, நீங்கள் {when} பணம் செலுத்துவீர்கள் என்று குறித்துக்கொண்டோம்.",
        "ask_date": "சரி. எந்த தேதியில் பணம் செலுத்த முடியும்?",
        "will_pay_no_date": "நன்றி, நீங்கள் விரைவில் பணம் செலுத்துவீர்கள் என்று குறித்துக்கொண்டோம்.",
        "details": "உங்கள் ஆர்டர் எண் {order} இல் {items} உள்ளன. செலுத்த வேண்டிய தொகை {amount}.",
        "callback": "நன்றி. எங்கள் குழு விரைவில் உங்களை மீண்டும் அழைக்கும்.",
        "wrong_number": "சிரமத்திற்கு மன்னிக்கவும். இந்த எண்ணுக்கு மீண்டும் அழைக்க மாட்டோம்.",
        "not_interested": "தொந்தரவுக்கு மன்னிக்கவும். இதைப் பற்றி மீண்டும் அழைக்க மாட்டோம்.",
        "reprompt": "மன்னிக்கவும், உங்கள் குரல் கேட்கவில்லை. நீங்கள் எப்போது பணம் செலுத்த முடியும்?",
        "not_understood": "மன்னிக்கவும், எனக்குப் புரியவில்லை. நீங்கள் எப்போது பணம் செலுத்த முடியும்?",
        "no_response": "உங்கள் குரல் கேட்கவில்லை, பிறகு மீண்டும் அழைக்கிறோம்.",
        "time_up": "இப்போது அழைப்பை முடிக்க வேண்டும். தேவைப்பட்டால் எங்கள் குழு மீண்டும் அழைக்கும்.",
        "goodbye": "நன்றி, இனிய நாளாக அமையட்டும். வணக்கம்.",
        "and": "மற்றும்",
        "more_items": "பிற பொருட்கள்",
    },
}

LANGS = tuple(PHRASES)
_FORMATTER = string.Formatter()
# Sentence ends: Latin punctuation and the Devanagari danda, followed by whitespace.
_SENTENCE_END = re.compile(r"(?<=[.?!।])\s+")


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "en").strip().lower()[:2]
    return lang if lang in PHRASES else "en"


def placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in _FORMATTER.parse(template) if field}


def render(key: str, lang: str, **values: str) -> str:
    """Fill a phrase. Missing values raise KeyError rather than leaving '{x}' in speech."""
    template = PHRASES[normalize_lang(lang)][key]
    missing = placeholders(template) - values.keys()
    if missing:
        raise KeyError(f"phrase {key!r} needs {sorted(missing)}")
    return template.format(**values)


def split_sentences(text: str) -> list[str]:
    """Split for incremental TTS: shorter chunks start playing sooner and cache better."""
    return [s.strip() for s in _SENTENCE_END.split(text.strip()) if s.strip()]


def static_sentences(lang: str) -> list[str]:
    """Every sentence that never changes (no placeholders), for pre-generating TTS."""
    out: list[str] = []
    for key, template in PHRASES[normalize_lang(lang)].items():
        if key in ("and", "more_items"):
            continue
        for sentence in split_sentences(template):
            if not placeholders(sentence) and sentence not in out:
                out.append(sentence)
    return out
