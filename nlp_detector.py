"""Deterministic Language and Intent Detector for Gokul Social Publisher.
Handles Tamil, English, Tanglish, and Emoji appreciation without external AI/LLMs.
"""
import re
import unicodedata
from typing import Tuple, Optional, Dict, List

# Tamil Unicode range: \u0B80 - \u0BFF
TAMIL_CHAR_PATTERN = re.compile(r'[\u0B80-\u0BFF]')

# Unsupported non-Latin, non-Tamil script ranges (Devanagari, Telugu, Kannada, Malayalam, Arabic, Cyrillic, CJK, etc.)
UNSUPPORTED_SCRIPT_PATTERN = re.compile(
    r'[\u0400-\u04FF\u0600-\u06FF\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F'
    r'\u0A80-\u0AFF\u0B00-\u0B7F\u0C00-\u0C7F\u0C80-\u0CFF\u0D00-\u0D7F'
    r'\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]'
)

POSITIVE_EMOJIS = {
    "❤️", "❤", "🙏", "👍", "🔥", "✨", "😍", "👏", "💯", "😊",
    "🥰", "💖", "💕", "💐", "🌟", "🙌", "👌", "🤩", "🥳", "😇", "🫶"
}
NEGATIVE_EMOJIS = {"😡", "🤬", "👎", "💔", "🤮", "💩", "😒", "😤"}

# Tanglish common keywords (Tamil transliterated into English script)
TANGLISH_MARKERS = {
    "vanakkam", "vanakam", "namaskaram", "kaalai", "malai",
    "super", "semma", "mass", "vera", "arputham", "nalla", "irukku", "iruku",
    "romba", "valthukkal", "vaalthukal", "nanri", "nandri", "thalaiva",
    "kalakkal", "kalakureenga", "attagasam", "sirappu", "thala", "anna", "akka",
    "eppadi", "epdi", "evvalavu", "evalo", "vilai", "enna", "enga", "yaar", "ethu",
    "kudu", "kudunga", "sollunga", "podunga", "parunga", "panna", "pannalama",
    "thaan", "illa", "illai", "porukki", "mosam", "thiruttu", "thirudan",
    "panam", "pochu", "thappu", "jathagam", "josiyam", "jothidam", "kalyanam",
    "thirumanam", "varan", "ah"
}

TANGLISH_PRAISE = {
    "super", "semma", "mass", "vera level", "veralevel", "arputham",
    "nalla irukku", "nalla iruku", "romba nalla", "valthukkal", "vaalthukal",
    "nanri", "nandri", "thalaiva", "mass bro", "super bro", "vera level bro",
    "kalakkal", "kalakureenga", "attagasam", "sirappu", "romba", "nalla"
}

ENGLISH_PRAISE = {
    "awesome", "great", "excellent", "amazing", "wonderful", "love it", "love this",
    "fantastic", "kudos", "brilliant", "nice post", "good job", "proud of you",
    "well done", "impressive", "keep it up", "congratulations", "congrats",
    "good", "nice", "useful", "very useful", "helpful", "informative", "thanks",
    "thank you", "good video", "nice video", "superb", "best"
}

TAMIL_PRAISE = {
    "அருமை", "சூப்பர்", "வாழ்த்துகள்", "நன்றி", "மிக நன்று", "நல்ல பதிவு",
    "அற்புதம்", "செம்ம", "பிரமாதம்", "சிறப்பு", "தலைவா", "மிகவும் அருமை", "நல்லது"
}

# Safety / Manual Review Keywords
ABUSE_COMPLAINT_KEYWORDS = {
    # English
    "scam", "fraud", "fake", "worst", "terrible", "horrible", "hate",
    "stupid", "idiot", "cheat", "cheating", "disappointed", "refund", "sucks",
    "rubbish", "not good", "not useful", "not helpful", "no good", "waste", "bad",
    "useless", "pathetic", "complaint", "problem", "issue",
    # Tanglish
    "porukki", "mosam", "thiruttu", "thirudan", "panam pochu", "thappu",
    # Tamil
    "மோசம்", "ஏமாற்று", "போலி", "வீண்", "குப்பை", "திருடன்", "பயனில்லை", "நல்லா இல்ல"
}

ASTROLOGY_KEYWORDS = {
    "astrology", "horoscope", "jathagam", "jothidam", "josiyam", "rasi",
    "nakshatra", "palan", "lagnam", "dasa", "bhukti", "dosham", "prediction",
    "ஜாதகம்", "ராசி", "நட்சத்திரம்", "ஜோதிடம்", "பலன்", "தோஷம்", "கிரகம்"
}

MATRIMONY_KEYWORDS = {
    "matrimony", "marriage", "bride", "groom", "kalyanam", "thirumanam",
    "alliance", "varan", "wedding", "partner",
    "பொண்ணு", "மாப்பிள்ளை", "திருமணம்", "கல்யாணம்", "வரன்"
}

FEE_KEYWORDS = {
    "fee", "fees", "price", "cost", "charge", "charges", "amount", "payment",
    "pay", "how much", "evvalavu", "evalo", "vilai", "consultation",
    "கட்டணம்", "விலை", "எவ்வளவு"
}

QUESTION_WORDS = {
    "how", "what", "when", "where", "why", "who", "which",
    "eppadi", "epdi", "enna", "enga", "yaar", "ethu",
    "எப்படி", "என்ன", "எங்கு", "யார்", "எது"
}

SPAM_PATTERNS = [
    re.compile(r'https?://\S+', re.IGNORECASE),
    re.compile(r'www\.\S+', re.IGNORECASE),
    re.compile(r'\b(whatsapp|telegram|earn money|click here|subscribe my|dm me for)\b', re.IGNORECASE),
    re.compile(r'\b\d{10,}\b')
]

# Exactly six approved automatic-reply templates (2 per language: Tamil, English, Tanglish)
APPROVED_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "ta": [
        {"id": "ta_1", "text": "மிக்க நன்றி! உங்கள் அன்பான ஆதரவுக்கு நெஞ்சார்ந்த நன்றிகள். 🙏"},
        {"id": "ta_2", "text": "உங்கள் கருத்துக்கு மிக்க நன்றி! தொடர்ந்து இணைந்திருங்கள். 😊✨"}
    ],
    "en": [
        {"id": "en_1", "text": "Thank you so much for your kind words and support! 🙏"},
        {"id": "en_2", "text": "We truly appreciate your positive feedback! Thank you for staying connected. 😊✨"}
    ],
    "tanglish": [
        {"id": "tanglish_1", "text": "Romba nanri! Ungaloda anbaana support-ku mikka nandri! 🙏"},
        {"id": "tanglish_2", "text": "Thank you so much for the lovely feedback! Keep supporting us! 😊✨"}
    ]
}


def normalize_text(text: str) -> str:
    """Normalizes Unicode text using NFC."""
    return unicodedata.normalize("NFC", text or "").strip()


def _is_emoji_only_appreciation(text: str) -> Tuple[bool, bool]:
    """Returns (is_emoji_only, is_positive_appreciation)."""
    # Strip whitespace and common punctuation
    stripped = re.sub(r'[\s\.,!?\-~]+', '', text)
    if not stripped:
        return (False, False)
    # If any alphanumeric or Tamil letter exists, it's not emoji-only
    if re.search(r'[a-zA-Z0-9\u0B80-\u0BFF]', stripped) or UNSUPPORTED_SCRIPT_PATTERN.search(stripped):
        return (False, False)

    has_positive = any(e in stripped for e in POSITIVE_EMOJIS)
    has_negative = any(e in stripped for e in NEGATIVE_EMOJIS)
    return (True, has_positive and not has_negative)


def detect_language(text: str) -> str:
    """Detects whether text is Tamil ('ta'), Tanglish ('tanglish'), English ('en'),
    'emoji', or 'unsupported'."""
    cleaned = normalize_text(text)
    if not cleaned:
        return "unknown"

    if UNSUPPORTED_SCRIPT_PATTERN.search(cleaned):
        return "unsupported"

    is_emoji_only, is_pos = _is_emoji_only_appreciation(cleaned)
    if is_emoji_only:
        return "emoji" if is_pos else "unsupported"

    lowered = cleaned.lower()

    # 1. Tamil script detection (including mixed Tamil-English)
    if TAMIL_CHAR_PATTERN.search(cleaned):
        return "ta"

    # 2. Tanglish keyword matching in Latin script
    words = set(re.findall(r'[a-zA-Z]+', lowered))
    if words.intersection(TANGLISH_MARKERS):
        return "tanglish"

    if re.search(r'[a-zA-Z]', cleaned):
        return "en"

    return "unsupported"


def select_template(lang: str, text: str, last_template_id: Optional[str] = None) -> Tuple[str, str]:
    """Selects one of the 6 approved templates, avoiding repeating last_template_id."""
    target_lang = "en" if lang == "emoji" else lang
    if target_lang not in APPROVED_TEMPLATES:
        target_lang = "en"

    candidates = APPROVED_TEMPLATES[target_lang]
    if last_template_id and len(candidates) > 1:
        filtered = [t for t in candidates if t["id"] != last_template_id]
        if filtered:
            chosen = filtered[len(text) % len(filtered)]
            return chosen["id"], chosen["text"]

    chosen = candidates[len(text) % len(candidates)]
    return chosen["id"], chosen["text"]


def analyze_comment_detailed(
    text: str, last_template_id: Optional[str] = None
) -> Tuple[str, str, Optional[str], str, Optional[str], Optional[str]]:
    """Analyzes comment text and returns:
    (language, intent, reply_text, action_status, template_id, reason)
    """
    cleaned = normalize_text(text)
    if not cleaned:
        return ("unknown", "empty", None, "skipped", None, "empty_comment")

    lang = detect_language(cleaned)
    if lang == "unsupported":
        return ("unsupported", "uncertain", None, "review_required", None, "unsupported_language")

    if lang == "emoji":
        tpl_id, reply = select_template("emoji", cleaned, last_template_id)
        return ("emoji", "emoji_appreciation", reply, "reply_ready", tpl_id, None)

    lower_text = cleaned.lower()
    words = set(re.findall(r'[a-zA-Z0-9\u0B80-\u0BFF]+', lower_text))

    # 1. Abuse / Complaints / Negative feedback (strict priority)
    if any(e in cleaned for e in NEGATIVE_EMOJIS) or any(
        kw in lower_text if (" " in kw or TAMIL_CHAR_PATTERN.search(kw)) else kw in words
        for kw in ABUSE_COMPLAINT_KEYWORDS
    ):
        return (lang, "complaint_or_abuse", None, "review_required", None, "complaint_or_abuse")

    # 2. Spam detection
    if any(p.search(cleaned) for p in SPAM_PATTERNS):
        return (lang, "spam", None, "review_required", None, "spam_detected")

    # 3. Sensitive / Specific Enquiries -> Manual Review
    if any(kw in lower_text if TAMIL_CHAR_PATTERN.search(kw) else kw in words for kw in ASTROLOGY_KEYWORDS):
        return (lang, "astrology_enquiry", None, "review_required", None, "astrology_enquiry")

    if any(kw in lower_text if TAMIL_CHAR_PATTERN.search(kw) else kw in words for kw in MATRIMONY_KEYWORDS):
        return (lang, "matrimony_enquiry", None, "review_required", None, "matrimony_enquiry")

    if any(kw in lower_text if (" " in kw or TAMIL_CHAR_PATTERN.search(kw)) else kw in words for kw in FEE_KEYWORDS):
        return (lang, "fee_enquiry", None, "review_required", None, "consultation_fee_enquiry")

    # 4. General Questions -> Manual Review
    if "?" in cleaned or any(kw in lower_text if TAMIL_CHAR_PATTERN.search(kw) else kw in words for kw in QUESTION_WORDS):
        return (lang, "question", None, "review_required", None, "question_requires_review")

    # 5. Positive Feedback and Praise (ONLY eligible text category)
    has_praise = False
    if lang == "ta":
        has_praise = any(p in lower_text for p in TAMIL_PRAISE)
    elif lang == "tanglish":
        has_praise = bool(words.intersection(TANGLISH_PRAISE)) or any(
            " " in p and p in lower_text for p in TANGLISH_PRAISE
        )
    else:
        praise_words = words - ({"good"} if any(g in lower_text for g in ("good morning", "good evening")) else set())
        has_praise = bool(praise_words.intersection(ENGLISH_PRAISE)) or any(
            " " in p and p in lower_text for p in ENGLISH_PRAISE
        )

    if has_praise:
        tpl_id, reply = select_template(lang, cleaned, last_template_id)
        return (lang, "praise", reply, "reply_ready", tpl_id, None)

    # 6. Everything else (greetings without praise, uncertain, unrelated) -> Manual Review
    return (lang, "uncertain", None, "review_required", None, "uncertain_intent")


def analyze_comment(text: str) -> Tuple[str, str, Optional[str], str]:
    """Backward-compatible wrapper returning (language, intent, reply_text, action_status)."""
    lang, intent, reply, status, _, _ = analyze_comment_detailed(text)
    return (lang, intent, reply, status)
