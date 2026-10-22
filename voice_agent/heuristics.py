"""Keyword-based intent and date understanding, used when Ollama is unavailable
or returns something invalid, and to fill a date the LLM missed.

Customers code-mix, so English keywords are checked in every language.
Matching rules (see _has): ASCII keywords match whole words; a single native-script
keyword matches the start of a word (Telugu/Tamil are agglutinative: రేపు -> రేపుకి);
multi-word native keywords match as substrings.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .models import Classification

_EN = {
    "wrong_number": ["wrong number", "not me", "no one by that name", "no such person",
                     "you have the wrong", "don't know you", "do not know you"],
    "not_interested": ["not interested", "don't call", "do not call", "stop calling",
                       "remove my number", "never call", "don't want to talk"],
    "dispute": ["dispute", "wrong amount", "wrong bill", "incorrect", "not correct", "didn't order",
                "did not order", "never ordered", "not ordered", "not received", "didn't receive",
                "did not receive", "never received", "damaged", "complaint", "defective",
                "already returned", "returned it"],
    "paid_claimed": ["already paid", "have paid", "i paid", "we paid", "paid it", "paid already",
                     "paid yesterday", "paid today", "paid on", "payment done", "payment is done",
                     "payment completed", "transferred", "sent the money", "sent money",
                     "made the payment", "cleared it", "already sent", "paid the amount"],
    "will_pay": ["will pay", "i'll pay", "ill pay", "we'll pay", "going to pay", "will transfer",
                 "will send", "will clear", "will do it", "will make the payment", "pay by",
                 "pay on", "pay tomorrow", "pay today", "pay next", "pay soon", "pay later",
                 "can pay", "shall pay"],
    "callback": ["call back", "call me back", "call later", "call me later", "busy", "driving",
                 "in a meeting", "call after", "talk later", "call tomorrow"],
    "ask_details": ["which order", "what order", "what is this", "what is it about", "how much",
                    "what amount", "details", "which amount", "what items", "what did i order",
                    "who is this", "who are you", "which bill"],
}

_NATIVE = {
    "hi": {
        "wrong_number": ["गलत नंबर", "ग़लत नंबर", "रॉन्ग नंबर", "galat number", "यहाँ कोई नहीं"],
        "not_interested": ["कॉल मत", "फोन मत", "फ़ोन मत", "दिलचस्पी नहीं", "call mat", "phone mat"],
        "dispute": ["गलत राशि", "गलत बिल", "गलत अमाउंट", "नहीं मिला", "नहीं मिली", "नहीं मिले",
                    "ऑर्डर नहीं किया", "शिकायत", "खराब", "वापस कर दिया", "nahi mila"],
        "paid_claimed": ["कर दिया", "कर दी", "दे दिया", "दे दी", "भेज दिया", "भेज दी", "कर चुका",
                         "कर चुकी", "कर चुके", "कर दिए", "दे दिए", "पेमेंट हो गया", "पेमेंट हो गई",
                         "भुगतान हो गया", "kar diya", "de diya", "bhej diya", "kar chuka", "ho gaya"],
        "will_pay": ["कर दूंगा", "कर दूँगा", "कर दूंगी", "कर दूँगी", "कर देंगे", "दे दूंगा", "दे दूँगा",
                     "दे दूंगी", "दे देंगे", "भेज दूंगा", "भेज दूँगा", "भेज देंगे", "करूंगा", "करूँगा",
                     "करूंगी", "करूँगी", "करेंगे", "दूंगा", "दूँगा", "दूंगी", "दूँगी", "देंगे",
                     "हो जाएगा", "हो जायेगा", "kar dunga", "de dunga", "karunga", "kar denge",
                     "de denge", "dunga", "dungi"],
        "callback": ["बाद में कॉल", "बाद में फोन", "बाद में फ़ोन", "बिज़ी", "बिजी", "baad mein call",
                     "मीटिंग में"],
        "ask_details": ["कौन सा ऑर्डर", "कौनसा ऑर्डर", "कितना", "कितने", "कितनी", "डिटेल", "विवरण",
                        "क्या ऑर्डर", "कौन बोल", "kitna", "kaun sa order"],
    },
    "te": {
        "wrong_number": ["రాంగ్ నంబర్", "తప్పు నంబర్", "రాంగ్ నెంబర్", "తప్పు నెంబర్"],
        "not_interested": ["కాల్ చేయకండి", "కాల్ చేయొద్దు", "ఫోన్ చేయకండి", "ఫోన్ చేయొద్దు",
                           "ఆసక్తి లేదు"],
        "dispute": ["రాలేదు", "అందలేదు", "తప్పు మొత్తం", "తప్పు బిల్", "ఆర్డర్ చేయలేదు", "ఫిర్యాదు",
                    "కంప్లైంట్", "పాడైపోయ", "రిటర్న్"],
        "paid_claimed": ["కట్టేశ", "కట్టేసా", "కట్టా", "చెల్లించేశ", "చెల్లించా", "పంపించేశ", "పంపా",
                         "పంపించా", "వేశా", "వేసేశ", "పే చేశ", "పే చేసా", "katesanu", "kattanu"],
        "will_pay": ["కడతా", "కట్టేస్తా", "కడతాం", "చెల్లిస్తా", "పంపిస్తా", "పంపుతా", "ఇస్తా",
                     "వేస్తా", "పే చేస్తా", "kadatanu", "kadtanu", "chestanu", "istanu"],
        "callback": ["తర్వాత కాల్", "తరువాత కాల్", "తర్వాత ఫోన్", "బిజీ", "డ్రైవింగ్"],
        "ask_details": ["ఏ ఆర్డర్", "ఎంత", "వివరాలు", "డీటెయిల్స్", "డిటైల్స్", "ఏమి ఆర్డర్", "ఎవరు"],
    },
    "ta": {
        "wrong_number": ["தவறான எண்", "ராங் நம்பர்", "தப்பான நம்பர்", "தவறான நம்பர்"],
        "not_interested": ["அழைக்க வேண்டாம்", "கால் பண்ணாதீங்க", "கால் பண்ண வேண்டாம்",
                           "விருப்பம் இல்லை", "போன் பண்ணாதீங்க"],
        "dispute": ["வரவில்லை", "கிடைக்கவில்லை", "கிடைக்கல", "தவறான தொகை", "தவறான பில்",
                    "ஆர்டர் செய்யவில்லை", "ஆர்டர் பண்ணல", "புகார்", "கம்ப்ளைன்ட்", "சேதம்", "ரிட்டர்ன்"],
        "paid_claimed": ["செலுத்திவிட்ட", "செலுத்திட்ட", "செலுத்தின", "கட்டிவிட்ட", "கட்டிட்ட",
                         "கட்டின", "அனுப்பிவிட்ட", "அனுப்பிட்ட", "அனுப்பின", "பண்ணிட்ட", "போட்டுட்ட",
                         "போட்டே"],
        "will_pay": ["செலுத்துவ", "செலுத்துகி", "செலுத்துறே", "செலுத்தறே", "கட்டுகி", "கட்டுவ",
                     "கட்டறே", "கட்டுறே", "கட்டிடுவ", "கட்டிடுறே", "அனுப்புகி", "அனுப்புவ",
                     "அனுப்பறே", "அனுப்புறே", "தருகி", "தருவ", "தரேன்", "பண்றே", "பண்ணுவ",
                     "பண்ணிடுறே", "பண்ணிடுவ"],
        "callback": ["பிறகு அழை", "அப்புறம் கால்", "பிறகு கால்", "பிஸி", "அப்புறம் பேச"],
        "ask_details": ["எந்த ஆர்டர்", "எவ்வளவு", "விவரம்", "விவரங்கள்", "டீடெயில்", "யார்", "என்ன ஆர்டர்"],
    },
}

# Checked in this order: the most consequential intents win ties.
_PRIORITY = ("wrong_number", "not_interested", "dispute", "paid_claimed", "will_pay", "callback",
             "ask_details")

_PAID_METHODS = {
    "UPI": ["upi", "gpay", "google pay", "phonepe", "phone pe", "paytm", "यूपीआई", "गूगल पे", "फोनपे",
            "फ़ोनपे", "फोन पे", "पेटीएम", "యూపీఐ", "గూగుల్ పే", "ఫోన్ పే", "ఫోన్‌పే", "పేటీఎం",
            "யுபிஐ", "கூகுள் பே", "போன் பே", "போன்பே", "பேடிஎம்", "ஜிபே"],
    "cash": ["cash", "कैश", "नकद", "క్యాష్", "నగదు", "கேஷ்", "ரொக்கம்", "ரொக்கமாக"],
    "cheque": ["cheque", "चेक", "చెక్కు", "చెక్", "காசோலை", "செக்"],
    "bank transfer": ["neft", "imps", "rtgs", "bank transfer", "bank", "बैंक", "బ్యాంక్", "பேங்க்", "வங்கி"],
    "card": ["card", "कार्ड", "కార్డ్", "கார்டு"],
    "online": ["online", "ऑनलाइन", "ఆన్‌లైన్", "ఆన్లైన్", "ஆன்லைன்"],
}

# Relative day words -> days from today.
_RELATIVE_DAYS = {
    0: ["today", "tonight", "this evening", "आज", "aaj", "ఈరోజు", "ఈ రోజు", "ఇవాళ", "ivala", "eeroju",
        "இன்று", "இன்னைக்கு", "indru", "innaiku"],
    1: ["tomorrow", "कल", "kal", "రేపు", "repu", "நாளை", "நாளைக்கு", "naalai", "nalai", "naalaikku"],
    2: ["day after tomorrow", "परसों", "parso", "parson", "ఎల్లుండి", "ellundi", "நாளை மறுநாள்",
        "நாளன்னைக்கு", "naalai marunaal"],
    7: ["next week", "अगले हफ्ते", "अगले हफ़्ते", "agle hafte", "వచ్చే వారం", "அடுத்த வாரம்"],
}
_MONTH_END = ["month end", "end of the month", "end of month", "महीने के अंत", "महीने के आखिर",
              "महीने के लास्ट", "నెలాఖరు", "నెల చివర", "மாத இறுதி", "மாசக் கடைசி", "மாச கடைசி"]
_WEEKDAY_WORDS = [  # Monday first
    ["monday", "सोमवार", "somvar", "సోమవార", "திங்கள்"],
    ["tuesday", "मंगलवार", "mangalvar", "మంగళవార", "செவ்வாய்"],
    ["wednesday", "बुधवार", "budhvar", "బుధవార", "புதன்"],
    ["thursday", "गुरुवार", "guruvar", "గురువార", "வியாழ"],
    ["friday", "शुक्रवार", "shukravar", "శుక్రవార", "வெள்ளி"],
    ["saturday", "शनिवार", "shanivar", "శనివార", "சனி"],
    ["sunday", "रविवार", "ravivar", "ఆదివార", "ஞாயிறு", "ஞாயிற்று"],
]
_MONTH_WORDS = [
    ["january", "jan", "जनवरी", "జనవరి", "ஜனவரி"],
    ["february", "feb", "फ़रवरी", "फरवरी", "ఫిబ్రవరి", "பிப்ரவரி"],
    ["march", "mar", "मार्च", "మార్చి", "மார்ச்"],
    ["april", "apr", "अप्रैल", "ఏప్రిల్", "ஏப்ரல்"],
    ["may", "मई", "మే", "மே"],
    ["june", "jun", "जून", "జూన్", "ஜூன்"],
    ["july", "jul", "जुलाई", "జూలై", "ஜூலை"],
    ["august", "aug", "अगस्त", "ఆగస్టు", "ஆகஸ்ட்"],
    ["september", "sep", "sept", "सितंबर", "సెప్టెంబర్", "செப்டம்பர்"],
    ["october", "oct", "अक्टूबर", "అక్టోబర్", "அக்டோபர்"],
    ["november", "nov", "नवंबर", "నవంబర్", "நவம்பர்"],
    ["december", "dec", "दिसंबर", "డిసెంబర్", "டிசம்பர்"],
]
_SMALL_NUMBERS = {  # "in two days"
    1: ["one", "a", "एक", "ek", "ఒక", "ఒకటి", "ஒரு", "ஒன்று"],
    2: ["two", "couple of", "दो", "do", "రెండు", "இரண்டு", "ரெண்டு"],
    3: ["three", "तीन", "teen", "మూడు", "மூன்று"],
    4: ["four", "चार", "char", "నాలుగు", "நான்கு", "நாலு"],
    5: ["five", "पांच", "पाँच", "paanch", "ఐదు", "ஐந்து", "அஞ்சு"],
    7: ["seven", "सात", "saat", "ఏడు", "ஏழு"],
    10: ["ten", "दस", "das", "పది", "பத்து"],
}
_DAY_UNITS = ["days", "day", "दिन", "din", "రోజు", "రోజుల", "நாள்", "நாட்கள்", "நாளில்"]
_TOKEN_SPLIT = re.compile(r"[\s,.!?।;:\"'()\-]+")


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def _has(text: str, keywords: list[str]) -> bool:
    tokens = _TOKEN_SPLIT.split(text)
    for kw in keywords:
        if kw.isascii():
            if re.search(rf"(?<![a-z']){re.escape(kw)}(?![a-z])", text):
                return True
        elif " " in kw:
            if kw in text:
                return True
        elif any(tok.startswith(kw) for tok in tokens):
            return True
    return False


def _keywords(intent: str, lang: str) -> list[str]:
    return _EN[intent] + _NATIVE.get(lang, {}).get(intent, [])


def find_paid_method(text: str) -> str | None:
    t = _norm(text)
    for method, words in _PAID_METHODS.items():
        if _has(t, words):
            return method
    return None


def _next_weekday(today: date, weekday: int) -> date:
    """The next such weekday strictly after today ('Friday' said on a Friday means next week)."""
    return today + timedelta(days=(weekday - today.weekday() - 1) % 7 + 1)


def find_date(text: str, today: date) -> date | None:
    """Resolve a payment date mentioned in the text, relative to today. None if no date found."""
    t = _norm(text)
    # Longest phrases first so "day after tomorrow" is not read as "tomorrow".
    for days in (2, 7, 1, 0):
        if _has(t, _RELATIVE_DAYS[days]):
            return today + timedelta(days=days)
    if _has(t, _MONTH_END):
        return today.replace(day=calendar.monthrange(today.year, today.month)[1])
    for wd, words in enumerate(_WEEKDAY_WORDS):
        if _has(t, words):
            return _next_weekday(today, wd)
    # "in 3 days", "मैं दो दिन में", "రెండు రోజుల్లో"
    m = re.search(r"(\d{1,2})\s*(?:" + "|".join(map(re.escape, _DAY_UNITS)) + ")", t)
    if m and 0 < int(m.group(1)) <= 60:
        return today + timedelta(days=int(m.group(1)))
    for n, words in _SMALL_NUMBERS.items():
        for w in words:
            for unit in _DAY_UNITS:
                if _has(t, [f"{w} {unit}"]):
                    return today + timedelta(days=n)
    # "25th", "25 tarikh", "25 తేదీ", "25 October"
    month_alt = "|".join(re.escape(w) for words in _MONTH_WORDS for w in words)
    m = re.search(r"(?<!\d)(\d{1,2})\s*(st|nd|rd|th|tarikh|तारीख|तारीख़|తేదీ|తేదిన|தேதி|"
                  + month_alt + r")", t)
    if not m:
        m2 = re.search(r"(" + month_alt + r")\s*(\d{1,2})(?!\d)", t)
        day_s, month_word = (m2.group(2), m2.group(1)) if m2 else (None, None)
    else:
        day_s, month_word = m.group(1), m.group(2)
    if day_s:
        day = int(day_s)
        month = next((i + 1 for i, words in enumerate(_MONTH_WORDS) if month_word in words), None)
        return _resolve_day(today, day, month)
    return None


def _resolve_day(today: date, day: int, month: int | None) -> date | None:
    """A day already past this month means next month; a past month means next year."""
    if not 1 <= day <= 31:
        return None
    year = today.year
    if month is None:
        month = today.month
        if day < today.day:
            month += 1
            if month > 12:
                month, year = 1, year + 1
    elif (month, day) < (today.month, today.day):
        year += 1
    try:
        return date(year, month, day)
    except ValueError:
        return None


def classify_heuristic(text: str, lang: str, today: date, expecting: str = "payment_answer"
                       ) -> Classification:
    t = _norm(text)
    matched = {i for i in _PRIORITY if _has(t, _keywords(i, lang))}
    method = find_paid_method(t)
    when = find_date(t, today)
    found = next((i for i in _PRIORITY if i in matched), None)
    if found == "will_pay" and "callback" in matched and when is None:
        found = "callback"  # "busy now, I'll pay" without a date: let the team call back
    if found is None:
        if expecting == "paid_details":
            found = "paid_claimed"  # any answer to "how did you pay" keeps the paid claim
        elif when is not None:
            found = "will_pay"  # a bare date in reply to "when will you pay"
        else:
            found = "other"
    return Classification(intent=found, promised_date=when if found == "will_pay" else None,
                          paid_method=method, note=text.strip()[:200], source="heuristic")
