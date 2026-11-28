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
    "🥰", "💖", "💕", "💐", "🌟", "🙌", "👌", "🤩", "🥳", "😇", "🫶",
    "😂", "🤣", "😄", "😁", "🎉", "🌺", "🕉️", "☀️", "💫", "🤗", "🧡", "💛", "💚", "💙", "💜"
}
FUNNY_EMOJIS = {"😂", "🤣", "😆", "😹", "😜", "🤪"}
FUNNY_KEYWORDS = {
    "haha", "hahaha", "hehe", "lol", "lmao", "rofl", "comedy", "funny",
    "hilarious", "joke", "sirippu", "kalakkal", "காமெடி", "சிரிப்பு", "செம காமெடி"
}
GREETING_KEYWORDS = {
    "hi", "hello", "hey", "good morning", "good evening", "good afternoon",
    "vanakkam", "vanakam", "namaskaram", "namaste", "kaalai vanakkam", "malai vanakkam",
    "வணக்கம்", "நமஸ்காரம்", "காலை வணக்கம்", "மாலை வணக்கம்"
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
    "அருமை", "அருமையான", "சூப்பர்", "வாழ்த்துகள்", "நன்றி", "மிக நன்று", "நல்ல பதிவு",
    "அற்புதம்", "செம்ம", "பிரமாதம்", "சிறப்பு", "தலைவா", "மிகவும் அருமை", "நல்லது",
    "நல்ல", "பயனுள்ள", "மகிழ்ச்சி", "தெளிவான"
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


def _clean_first_name(author_name: Optional[str]) -> str:
    raw = (author_name or "").strip().lstrip("@")
    if not raw or raw.lower() in ("facebook user", "instagram user", "youtube user", "user"):
        return ""
    first = raw.split()[0]
    if len(first) < 2 or len(first) > 20 or not re.search(r'[a-zA-Z\u0B80-\u0BFF]', first):
        return ""
    return first


def _extract_matching_emojis(text: str, limit: int = 3) -> str:
    found = [e for e in POSITIVE_EMOJIS if e in (text or "")]
    if not found:
        return "🙏✨"
    return "".join(found[:limit])


def generate_contextual_auto_reply(
    text: str,
    author_name: Optional[str] = None,
    lang: Optional[str] = None,
    intent: Optional[str] = None,
    has_sticker: bool = False,
) -> Tuple[str, str]:
    """Generate a natural, tone-matched, context-aware reply for safe comments.
    Returns (reply_text, detected_tone).
    """
    cleaned = normalize_text(text)
    lower = cleaned.lower()
    detected_lang = lang or detect_language(cleaned)
    if detected_lang not in ("ta", "tanglish", "en", "emoji"):
        detected_lang = "en"

    fname = _clean_first_name(author_name)
    name_prefix = f" {fname}" if fname else ""
    emojis = _extract_matching_emojis(cleaned)
    variant = (len(cleaned) + len(fname)) % 3

    # 1. Sticker-only or empty-text sticker
    if has_sticker and not cleaned:
        return (f"அன்பான ஸ்டிக்கருக்கு மிக்க நன்றி{name_prefix}! {emojis}✨" if fname else f"Love the sticker! Thank you so much! 🙏✨", "sticker")

    # 2. Funny / Playful tone
    is_funny = any(e in cleaned for e in FUNNY_EMOJIS) or any(
        kw in lower if TAMIL_CHAR_PATTERN.search(kw) else re.search(rf'\b{re.escape(kw)}\b', lower)
        for kw in FUNNY_KEYWORDS
    )
    if is_funny:
        if detected_lang == "ta":
            options = [
                f"ஹாஹா{name_prefix}! உங்கள் நகைச்சுவை உணர்வு சூப்பர் 😄 தொடர்ந்து சிரித்து மகிழுங்கள்! ✨",
                f"சிரிப்பும் மகிழ்ச்சியும் எப்போதும் இருக்கட்டும்{name_prefix}! 😂✨ அருமையான கமெண்ட்!",
                f"கலக்கலான கமெண்ட்{name_prefix}! 😄 உங்களுடன் இணைந்திருப்பதில் மகிழ்ச்சி! 🙌",
            ]
        elif detected_lang == "tanglish":
            options = [
                f"Haha{name_prefix}! Semma vibe-a irukkeenga 😂✨ Always stay happy and smiling!",
                f"Super comedy sense{name_prefix}! 😄🔥 Ungaloda positive energy romba pidichirukku!",
                f"Haha{name_prefix}, kalakkeeteenga! 😂🙌 Keep spreading smiles!",
            ]
        else:
            options = [
                f"Haha{name_prefix}, love your sense of humor! 😂✨ Glad this brought a smile to your day!",
                f"You made us smile too{name_prefix}! 😄✨ Thanks for the fun vibe!",
                f"Haha{name_prefix}, great energy! 😂🙌 Appreciate you hanging out with us!",
            ]
        return options[variant], "funny"

    # 3. Emoji-only appreciation
    if detected_lang == "emoji" or intent == "emoji_appreciation":
        options = [
            f"Thank you so much{name_prefix}! {emojis}✨",
            f"Sending lots of warmth right back{name_prefix}! {emojis}🙌",
            f"Appreciate the love{name_prefix}! {emojis}🌟",
        ]
        return options[variant], "emoji"

    # 4. Greeting
    is_greeting = intent == "greeting" or any(
        kw in lower if TAMIL_CHAR_PATTERN.search(kw) else re.search(rf'\b{re.escape(kw)}\b', lower)
        for kw in GREETING_KEYWORDS
    )
    if is_greeting and intent != "praise":
        if detected_lang == "ta":
            return f"வணக்கம்{name_prefix}! 🙏 உங்கள் நாட்கள் இனிமையாகவும் மகிழ்ச்சியாகவும் அமைய வாழ்த்துகள்! ✨", "greeting"
        if detected_lang == "tanglish":
            return f"Vanakkam{name_prefix}! 🙏 Ungal naal iniyathaaga amaiya vaalthukkal! ✨", "greeting"
        return f"Warm greetings{name_prefix}! 🙏 Wishing you a wonderful and blessed day ahead! ✨", "greeting"

    # 5. Context-aware praise / positive feedback
    mentions_video = any(w in lower for w in ("video", "post", "reel", "content", "பதிவு", "வீடியோ"))
    mentions_explain = any(w in lower for w in ("explain", "explanation", "clear", "voice", "informative", "useful", "helpful", "விளக்கம்", "பயனுள்ள"))
    mentions_energy = any(w in lower for w in ("super", "semma", "mass", "vera level", "veralevel", "awesome", "amazing", "fantastic", "சூப்பர்", "செம்ம", "அருமை", "அற்புதம்"))

    if detected_lang == "ta":
        if mentions_explain:
            options = [
                f"மிக்க மகிழ்ச்சி{name_prefix}! எங்கள் விளக்கம் உங்களுக்குத் தெளிவாகவும் பயனுள்ளதாகவும் இருந்ததில் சந்தோஷம். {emojis}",
                f"உங்கள் அன்பான பாராட்டுக்கு நன்றி{name_prefix}! பயனுள்ள தகவல்களைத் தொடர்ந்து பகிர்வோம். 🙏✨",
                f"நன்றி{name_prefix}! இது போன்ற கருத்துகள் எங்களுக்குப் பெரிய ஊக்கம் தருகின்றன. 🌟🙏",
            ]
        elif mentions_video:
            options = [
                f"மிக்க நன்றி{name_prefix}! இந்தப் பதிவு உங்களுக்குப் பிடித்ததில் மிகவும் மகிழ்ச்சி. {emojis}",
                f"உங்கள் நேரத்திற்கும் அன்பான கருத்திற்கும் நன்றி{name_prefix}! தொடர்ந்து இணைந்திருங்கள். 😊✨",
                f"அன்பான ஆதரவுக்கு நன்றி{name_prefix}! இன்னும் பல நல்ல பதிவுகள் காத்திருக்கின்றன. 🙏🌟",
            ]
        elif mentions_energy:
            options = [
                f"உங்கள் உற்சாகமான பாராட்டுக்கு மனமார்ந்த நன்றி{name_prefix}! {emojis}✨",
                f"மிகவும் மகிழ்ச்சி{name_prefix}! உங்கள் அன்பும் ஆதரவும் எப்போதும் எங்கள் பலம். 🙏💫",
                f"அருமையான வார்த்தைகள்{name_prefix}! தொடர்ந்து உங்கள் ஆதரவைத் தாருங்கள். 😊🌟",
            ]
        else:
            options = [
                f"உங்கள் இனிய கருத்துக்கு மனமார்ந்த நன்றி{name_prefix}! {emojis}",
                f"மிக்க நன்றி{name_prefix}! உங்கள் அன்பான ஆதரவு எங்களுக்குப் பெரிய மகிழ்ச்சி. 🙏✨",
                f"நன்றி{name_prefix}! தொடர்ந்து எங்களுடன் இணைந்திருங்கள். 😊🌟",
            ]
        return options[variant], "praise"

    if detected_lang == "tanglish":
        if mentions_explain:
            options = [
                f"Romba santhosham{name_prefix}! Explanation ungalukku clear-aa & useful-aa irunthathil mikka magizhchi! {emojis}",
                f"Thanks a lot{name_prefix}! Ungalukku helpful-aa irukkarathu kekka romba nalla irukku! 🙏✨",
                f"Mikka nandri{name_prefix}! Innum neraya useful info share panrom! 🌟",
            ]
        elif mentions_video:
            options = [
                f"Romba nandri{name_prefix}! Intha video ungalukku pidichathil romba santhosham! {emojis}",
                f"Super support{name_prefix}! Innum neraya nalla posts varuthu, stay tuned! 😊✨",
                f"Thanks{name_prefix}! Ungaloda anbaana feedback romba energy tharuthu! 🙏🔥",
            ]
        else:
            options = [
                f"Semma motivation{name_prefix}! Ungaloda anbaana support-ku romba nandri! {emojis}",
                f"Romba nandri{name_prefix}! Keep supporting us always! 🙏✨",
                f"Thanks a lot{name_prefix}! Ungaloda positive words romba happy-aa irukku! 😊🌟",
            ]
        return options[variant], "praise"

    # English
    if mentions_explain:
        options = [
            f"So glad to hear you found the explanation clear and helpful{name_prefix}! {emojis}",
            f"Thank you{name_prefix}! Sharing practical, helpful insights is our goal—glad it resonated! 🙏✨",
            f"Appreciate your kind words{name_prefix}! More helpful insights coming soon! 🌟",
        ]
    elif mentions_video:
        options = [
            f"Thank you so much{name_prefix}! Really glad you enjoyed this video! {emojis}",
            f"Thanks for watching and sharing your thoughts{name_prefix}! Stay tuned for more! 😊✨",
            f"Appreciate the love on this post{name_prefix}! Thanks for staying connected! 🙏🌟",
        ]
    elif mentions_energy:
        options = [
            f"Love the enthusiasm{name_prefix}! Thank you so much for the awesome support! {emojis}",
            f"You made our day{name_prefix}! Thanks for the amazing energy and encouragement! 🙏✨",
            f"Thank you{name_prefix}! Your excitement keeps us motivated to do our best! 🌟🔥",
        ]
    else:
        options = [
            f"Thank you so much for your kind words{name_prefix}! {emojis}",
            f"We truly appreciate your positive energy{name_prefix}! Thanks for staying connected! 😊✨",
            f"So grateful for your support{name_prefix}! Wishing you all the best! 🙏🌟",
        ]
    return options[variant], "praise"


def classify_for_auto_reply(
    text: str,
    author_name: Optional[str] = None,
    has_sticker: bool = False,
    last_template_id: Optional[str] = None,
) -> Tuple[str, str, Optional[str], str, Optional[str], Optional[str]]:
    """Extended classifier for live/auto-reply pipelines.
    - Keeps all safety & manual-review rules strict (abuse, complaints, negative, spam, enquiries, questions).
    - Also supports stickers, funny/playful comments, greetings, and context-aware personalized replies.
    """
    cleaned = normalize_text(text)
    if not cleaned and has_sticker:
        reply, _ = generate_contextual_auto_reply("", author_name=author_name, lang="emoji", intent="sticker", has_sticker=True)
        return ("emoji", "emoji_appreciation", reply, "reply_ready", "en_1", None)

    lang, intent, reply_text, action_status, template_id, reason = analyze_comment_detailed(cleaned, last_template_id)
    if action_status == "reply_ready":
        contextual_reply, tone = generate_contextual_auto_reply(
            cleaned, author_name=author_name, lang=lang, intent=intent, has_sticker=has_sticker
        )
        return (lang, intent, contextual_reply, "reply_ready", template_id, None)

    # Check if an 'uncertain' comment is actually a safe funny comment or greeting
    if action_status == "review_required" and reason == "uncertain_intent":
        lower = cleaned.lower()
        is_funny = any(e in cleaned for e in FUNNY_EMOJIS) or any(
            kw in lower if TAMIL_CHAR_PATTERN.search(kw) else re.search(rf'\b{re.escape(kw)}\b', lower)
            for kw in FUNNY_KEYWORDS
        )
        is_greeting = any(
            kw in lower if TAMIL_CHAR_PATTERN.search(kw) else re.search(rf'\b{re.escape(kw)}\b', lower)
            for kw in GREETING_KEYWORDS
        )
        if is_funny or is_greeting:
            sub_intent = "funny" if is_funny else "greeting"
            tpl_lang = "ta" if lang == "ta" else ("tanglish" if lang == "tanglish" else "en")
            tpl_id, _ = select_template(tpl_lang, cleaned, last_template_id)
            contextual_reply, _ = generate_contextual_auto_reply(
                cleaned, author_name=author_name, lang=lang, intent=sub_intent, has_sticker=has_sticker
            )
            return (lang, sub_intent, contextual_reply, "reply_ready", tpl_id, None)

    return (lang, intent, reply_text, action_status, template_id, reason)
