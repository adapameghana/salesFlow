"""Numbers, amounts and dates as words for TTS in English, Hindi, Telugu and Tamil.

Uses the Indian numbering system (thousand, lakh, crore). TTS models read
digits unreliably in Indic languages, so everything spoken is spelled out.
"""
from __future__ import annotations

from datetime import date

LANGS = ("en", "hi", "te", "ta")

# ---------------------------------------------------------------- English
_EN_0_19 = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen",
]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# ---------------------------------------------------------------- Hindi (0-99 are irregular)
_HI_0_99 = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ "
    "दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस "
    "तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस "
    "चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास "
    "पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ "
    "साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर "
    "सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उनासी "
    "अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
    "नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे"
).split()
assert len(_HI_0_99) == 100

# ---------------------------------------------------------------- Telugu
_TE_0_19 = [
    "సున్నా", "ఒకటి", "రెండు", "మూడు", "నాలుగు", "ఐదు", "ఆరు", "ఏడు", "ఎనిమిది", "తొమ్మిది",
    "పది", "పదకొండు", "పన్నెండు", "పదమూడు", "పద్నాలుగు", "పదిహేను", "పదహారు", "పదిహేడు",
    "పద్దెనిమిది", "పందొమ్మిది",
]
_TE_TENS = ["", "", "ఇరవై", "ముప్పై", "నలభై", "యాభై", "అరవై", "డెబ్బై", "ఎనభై", "తొంభై"]

# ---------------------------------------------------------------- Tamil
_TA_0_19 = [
    "பூஜ்ஜியம்", "ஒன்று", "இரண்டு", "மூன்று", "நான்கு", "ஐந்து", "ஆறு", "ஏழு", "எட்டு", "ஒன்பது",
    "பத்து", "பதினொன்று", "பன்னிரண்டு", "பதின்மூன்று", "பதினான்கு", "பதினைந்து", "பதினாறு",
    "பதினேழு", "பதினெட்டு", "பத்தொன்பது",
]
_TA_TENS = ["", "", "இருபது", "முப்பது", "நாற்பது", "ஐம்பது", "அறுபது", "எழுபது", "எண்பது", "தொண்ணூறு"]
_TA_TENS_JOIN = ["", "", "இருபத்து", "முப்பத்து", "நாற்பத்து", "ஐம்பத்து", "அறுபத்து", "எழுபத்து",
                 "எண்பத்து", "தொண்ணூற்று"]
_TA_HUNDREDS = ["", "நூறு", "இருநூறு", "முன்னூறு", "நானூறு", "ஐநூறு", "அறுநூறு", "எழுநூறு",
                "எண்ணூறு", "தொள்ளாயிரம்"]
_TA_HUNDREDS_JOIN = ["", "நூற்று", "இருநூற்று", "முன்னூற்று", "நானூற்று", "ஐநூற்று", "அறுநூற்று",
                     "எழுநூற்று", "எண்ணூற்று", "தொள்ளாயிரத்து"]
_TA_THOUSANDS = {1: "ஆயிரம்", 2: "இரண்டாயிரம்", 3: "மூவாயிரம்", 4: "நான்காயிரம்", 5: "ஐந்தாயிரம்",
                 6: "ஆறாயிரம்", 7: "ஏழாயிரம்", 8: "எட்டாயிரம்", 9: "ஒன்பதாயிரம்", 10: "பத்தாயிரம்"}


def _split_indian(n: int) -> tuple[int, int, int, int, int]:
    """n -> (crores, lakhs, thousands, hundreds, rest below 100)."""
    crores, n = divmod(n, 10_000_000)
    lakhs, n = divmod(n, 100_000)
    thousands, n = divmod(n, 1000)
    hundreds, rest = divmod(n, 100)
    return crores, lakhs, thousands, hundreds, rest


def _en(n: int) -> str:
    def below_100(k: int) -> str:
        if k < 20:
            return _EN_0_19[k]
        tens, ones = divmod(k, 10)
        return _EN_TENS[tens] + (f"-{_EN_0_19[ones]}" if ones else "")

    if n == 0:
        return "zero"
    c, l, t, h, r = _split_indian(n)
    parts = []
    if c:
        parts.append(f"{_en(c)} crore")
    if l:
        parts.append(f"{below_100(l)} lakh")
    if t:
        parts.append(f"{below_100(t)} thousand")
    if h:
        parts.append(f"{_EN_0_19[h]} hundred")
    if r:
        parts.append(below_100(r))
    return " ".join(parts)


def _hi(n: int) -> str:
    if n == 0:
        return _HI_0_99[0]
    c, l, t, h, r = _split_indian(n)
    parts = []
    if c:
        parts.append(f"{_hi(c)} करोड़")
    if l:
        parts.append(f"{_HI_0_99[l]} लाख")
    if t:
        parts.append(f"{_HI_0_99[t]} हज़ार")
    if h:
        parts.append(f"{_HI_0_99[h]} सौ")
    if r:
        parts.append(_HI_0_99[r])
    return " ".join(parts)


def _te_below_100(k: int, attributive: bool = False) -> str:
    if k < 20:
        s = _TE_0_19[k]
    else:
        tens, ones = divmod(k, 10)
        s = _TE_TENS[tens] + (f" {_TE_0_19[ones]}" if ones else "")
    # "one" before a noun or scale word is ఒక, not ఒకటి (ఒక లక్ష, ఒక రూపాయి).
    if attributive and s.endswith("ఒకటి"):
        s = s[: -len("ఒకటి")] + "ఒక"
    return s


def _te(n: int, before_noun: bool = False) -> str:
    """Telugu. Scale words take the oblique form (వేల, వందల) when more follows,
    or when a noun such as రూపాయలు follows (before_noun)."""
    if n == 0:
        return _TE_0_19[0]
    c, l, t, h, r = _split_indian(n)
    groups = [(c, "crore"), (l, "lakh"), (t, "thousand"), (h, "hundred"), (r, "rest")]
    nonzero = [g for g in groups if g[0]]
    parts = []
    for i, (k, scale) in enumerate(nonzero):
        last = i == len(nonzero) - 1
        oblique = not last or before_noun
        if scale == "crore":
            parts.append("ఒక కోటి" if k == 1 else f"{_te(k, before_noun=True)} {'కోట్ల' if oblique else 'కోట్లు'}")
        elif scale == "lakh":
            parts.append("ఒక లక్ష" if k == 1 else f"{_te_below_100(k, True)} {'లక్షల' if oblique else 'లక్షలు'}")
        elif scale == "thousand":
            parts.append("వెయ్యి" if k == 1 else f"{_te_below_100(k, True)} {'వేల' if oblique else 'వేలు'}")
        elif scale == "hundred":
            if k == 1:
                parts.append("వంద" if last else "నూట")
            else:
                parts.append(f"{_TE_0_19[k]} {'వందల' if oblique else 'వందలు'}")
        else:
            parts.append(_te_below_100(k, attributive=before_noun))
    return " ".join(parts)


def _ta_below_100(k: int, attributive: bool = False) -> str:
    if k < 20:
        s = _TA_0_19[k]
    else:
        tens, ones = divmod(k, 10)
        s = f"{_TA_TENS_JOIN[tens]} {_TA_0_19[ones]}" if ones else _TA_TENS[tens]
    if attributive:  # ஒன்று -> ஒரு before a noun or scale word
        if s.endswith("பதினொன்று"):
            s = s[: -len("பதினொன்று")] + "பதினோரு"
        elif s.endswith("ஒன்று"):
            s = s[: -len("ஒன்று")] + "ஒரு"
    return s


def _ta(n: int, before_noun: bool = False) -> str:
    """Tamil. A scale word takes its joining form (ஆயிரத்து, லட்சத்து, நூற்று) when more follows."""
    if n == 0:
        return _TA_0_19[0]
    c, l, t, h, r = _split_indian(n)
    groups = [(c, "crore"), (l, "lakh"), (t, "thousand"), (h, "hundred"), (r, "rest")]
    nonzero = [g for g in groups if g[0]]
    parts = []
    for i, (k, scale) in enumerate(nonzero):
        join = i < len(nonzero) - 1
        if scale == "crore":
            base = "ஒரு கோடி" if k == 1 else f"{_ta(k, before_noun=True)} கோடி"
            parts.append(base + ("யே" if join else ""))
        elif scale == "lakh":
            base = "ஒரு லட்சம்" if k == 1 else f"{_ta_below_100(k, True)} லட்சம்"
            parts.append(base[:-2] + "த்து" if join else base)
        elif scale == "thousand":
            base = _TA_THOUSANDS.get(k) or f"{_ta_below_100(k, True)} ஆயிரம்"
            parts.append(base[:-2] + "த்து" if join else base)
        elif scale == "hundred":
            parts.append(_TA_HUNDREDS_JOIN[k] if join else _TA_HUNDREDS[k])
        else:
            parts.append(_ta_below_100(k, attributive=before_noun))
    return " ".join(parts)


def number_to_words(n: int, lang: str, before_noun: bool = False) -> str:
    """Spell a non-negative integer in the given language (Indian numbering)."""
    if n < 0:
        raise ValueError("negative numbers are not supported")
    if lang == "hi":
        return _hi(n)
    if lang == "te":
        return _te(n, before_noun)
    if lang == "ta":
        return _ta(n, before_noun)
    return _en(n)


_RUPEES = {"en": ("rupee", "rupees"), "hi": ("रुपया", "रुपये"), "te": ("రూపాయి", "రూపాయలు"),
           "ta": ("ரூபாய்", "ரூபாய்")}


def rupees_to_words(amount: float, lang: str) -> str:
    """4250.4 -> 'four thousand two hundred fifty rupees' (rounded to whole rupees)."""
    whole = int(round(float(amount) + 1e-9))
    singular, plural = _RUPEES.get(lang, _RUPEES["en"])
    return f"{number_to_words(whole, lang, before_noun=True)} {singular if whole == 1 else plural}"


_POINT = {"en": "point", "hi": "दशमलव", "te": "పాయింట్", "ta": "புள்ளி"}


def quantity_to_words(qty: float, lang: str) -> str:
    """Quantities can be fractional (2.5 boxes); never round them away."""
    q = float(qty)
    if q.is_integer():
        return number_to_words(int(q), lang, before_noun=True)
    whole, frac = f"{q:.3f}".rstrip("0").split(".")
    return " ".join([number_to_words(int(whole), lang), _POINT.get(lang, "point")]
                    + [number_to_words(int(d), lang) for d in frac])


def digits_to_words(digits: str, lang: str) -> str:
    """'0123' -> 'zero one two three' (for reading out IDs)."""
    return " ".join(number_to_words(int(d), lang) for d in digits if d.isdigit())


# ---------------------------------------------------------------- dates
_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
           "नवंबर", "दिसंबर"],
    "te": ["జనవరి", "ఫిబ్రవరి", "మార్చి", "ఏప్రిల్", "మే", "జూన్", "జూలై", "ఆగస్టు", "సెప్టెంబర్",
           "అక్టోబర్", "నవంబర్", "డిసెంబర్"],
    "ta": ["ஜனவரி", "பிப்ரவரி", "மார்ச்", "ஏப்ரல்", "மே", "ஜூன்", "ஜூலை", "ஆகஸ்ட்", "செப்டம்பர்",
           "அக்டோபர்", "நவம்பர்", "டிசம்பர்"],
}
_WEEKDAYS = {  # Monday first, like date.weekday()
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "te": ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"],
    "ta": ["திங்கள்கிழமை", "செவ்வாய்க்கிழமை", "புதன்கிழமை", "வியாழக்கிழமை", "வெள்ளிக்கிழமை",
           "சனிக்கிழமை", "ஞாயிற்றுக்கிழமை"],
}
# Relative day names, already phrased as "when" (no postposition needed).
_RELATIVE = {
    "en": {0: "today", 1: "tomorrow", 2: "the day after tomorrow"},
    "hi": {0: "आज", 1: "कल", 2: "परसों"},
    "te": {0: "ఈరోజు", 1: "రేపు", 2: "ఎల్లుండి"},
    "ta": {0: "இன்று", 1: "நாளை", 2: "நாளை மறுநாள்"},
}


def date_to_words(d: date, lang: str) -> str:
    """'Saturday, October twenty-four' style, in the target language."""
    lang = lang if lang in LANGS else "en"
    weekday = _WEEKDAYS[lang][d.weekday()]
    month = _MONTHS[lang][d.month - 1]
    day = number_to_words(d.day, lang)
    if lang == "hi":
        return f"{weekday}, {day} {month}"
    return f"{weekday}, {month} {day}"


def when_to_words(d: date, today: date, lang: str) -> str:
    """The date as an adverbial phrase: 'tomorrow', 'on Saturday, October twenty-four', 'कल', ..."""
    lang = lang if lang in LANGS else "en"
    delta = (d - today).days
    if delta in _RELATIVE[lang]:
        return _RELATIVE[lang][delta]
    words = date_to_words(d, lang)
    return {"en": f"on {words}", "hi": f"{words} को", "te": f"{words} న", "ta": f"{words} அன்று"}[lang]
