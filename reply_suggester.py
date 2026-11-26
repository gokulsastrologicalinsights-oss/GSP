"""Context-aware local comment classifier and personalized reply generator.

Uses lightweight local NLP (no mandatory cloud AI or paid APIs) to classify
Tamil, Tanglish, and English comments and generate personalized, brand-aware
reply suggestions that always require human approval before publishing.
"""
import re
from typing import Dict, Optional

import nlp_detector

THREAT_KEYWORDS = {
    "kill", "murder", "attack", "bomb", "destroy you", "hurt you", "die",
    "police", "court", "sue you", "legal action", "defamation", "expose you",
    "கொலை", "அடிப்பேன்", "வழக்கு", "போலீஸ்",
}

GREETING_KEYWORDS = {
    "hi", "hello", "hey", "good morning", "good evening", "good afternoon",
    "vanakkam", "vanakam", "namaskaram", "kaalai vanakkam", "malai vanakkam",
    "வணக்கம்", "நமஸ்காரம்", "காலை வணக்கம்", "மாலை வணக்கம்",
}

ABUSIVE_KEYWORDS = {
    "idiot", "stupid", "moron", "fool", "loser", "shut up", "scammer", "fraud",
    "cheat", "cheater", "liar", "pathetic", "rubbish", "trash", "useless",
    "porukki", "thirudan", "thiruttu", "loosu", "mental", "naaye",
    "பொறுக்கி", "திருடன்", "முட்டாள்", "ஏமாற்றுக்காரன்", "போலி",
}

COMPLAINT_KEYWORDS = {
    "refund", "money back", "not working", "no response", "no reply", "delayed",
    "late", "wrong", "mistake", "issue", "problem", "complaint", "disappointed",
    "panam pochu", "reply illa", "thappu", "mosam",
    "பணம்", "பதில் இல்லை", "தவறு", "மோசம்", "புகார்", "பிரச்சனை",
}

NEGATIVE_KEYWORDS = {
    "bad", "worst", "terrible", "horrible", "hate", "boring", "waste",
    "not good", "not useful", "not helpful", "no good", "dislike",
    "nalla illa", "pidikkala", "waste",
    "நல்லா இல்ல", "பிடிக்கல", "வீண்", "பயனில்லை",
}


def _detect_brand(account_name: Optional[str], comment_text: str) -> str:
    combined = f"{account_name or ''} {comment_text or ''}".lower()
    if any(k in combined for k in ("vivaham", "matrimony", "marriage", "kalyanam", "thirumanam", "varan", "திருமணம்", "கல்யாணம்")):
        return "Gokul Vivaham"
    return "Gokul's Astrological Insights"


def classify_comment(comment_text: str) -> Dict[str, str]:
    """Classify comment into language, sentiment, and intent."""
    text = nlp_detector.normalize_text(comment_text)
    lower = text.lower()
    lang = nlp_detector.detect_language(text)
    if lang == "unsupported":
        lang = "en"

    # 1. Threatening / harmful
    if any(k in lower for k in THREAT_KEYWORDS):
        return {"language": lang, "sentiment": "threatening", "intent": "threatening"}

    # 2. Spam
    if any(p.search(text) for p in nlp_detector.SPAM_PATTERNS):
        return {"language": lang, "sentiment": "spam", "intent": "spam"}

    # 3. Abusive / Hostile
    if any(k in lower for k in ABUSIVE_KEYWORDS):
        return {"language": lang, "sentiment": "hostile", "intent": "abusive"}

    # 4. Complaint
    if any(k in lower for k in COMPLAINT_KEYWORDS):
        return {"language": lang, "sentiment": "negative", "intent": "complaint"}

    # 5. Negative feedback
    if any(k in lower for k in NEGATIVE_KEYWORDS) or any(e in text for e in nlp_detector.NEGATIVE_EMOJIS):
        return {"language": lang, "sentiment": "negative", "intent": "negative"}

    # 6. General inquiry (questions, astrology, matrimony, fees)
    has_question = "?" in text or any(
        re.search(rf"\b{re.escape(q)}\b", lower) if q.isascii() else q in lower
        for q in nlp_detector.QUESTION_WORDS
    )
    has_domain_inquiry = any(
        k in lower for k in (nlp_detector.ASTROLOGY_KEYWORDS | nlp_detector.MATRIMONY_KEYWORDS | nlp_detector.FEE_KEYWORDS)
    )
    if has_question or has_domain_inquiry:
        return {"language": lang, "sentiment": "neutral", "intent": "general_inquiry"}

    # 7. Greeting
    if any(
        re.search(rf"\b{re.escape(g)}\b", lower) if g.isascii() else g in lower
        for g in GREETING_KEYWORDS
    ) and len(lower.split()) <= 5:
        return {"language": lang, "sentiment": "positive", "intent": "greeting"}

    # 8. Positive / Appreciation
    praise_set = nlp_detector.TAMIL_PRAISE | nlp_detector.TANGLISH_PRAISE | nlp_detector.ENGLISH_PRAISE
    if any(k in lower for k in praise_set) or any(e in text for e in nlp_detector.POSITIVE_EMOJIS):
        return {"language": lang, "sentiment": "positive", "intent": "positive"}

    # 9. Neutral fallback
    return {"language": lang, "sentiment": "neutral", "intent": "neutral"}


def generate_reply_suggestion(
    comment_text: str,
    commenter_name: Optional[str] = None,
    account_name: Optional[str] = None,
    platform: Optional[str] = None,
    previous_context: Optional[str] = None,
) -> Dict[str, str]:
    """Generate a personalized, brand-aware reply suggestion for manual approval."""
    try:
        cls = classify_comment(comment_text)
        lang = cls["language"]
        sentiment = cls["sentiment"]
        intent = cls["intent"]
        brand = _detect_brand(account_name, comment_text)
        name = (commenter_name or "").strip().lstrip("@")
        greet_name = f" {name}" if name and len(name) <= 24 else ""
        has_prev = bool(previous_context and previous_context.strip())

        if intent == "spam":
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": "",
                "reason": "Spam detected (promotional links/phone/solicitation). Recommend no reply.",
                "generation_method": "local_contextual",
            }

        if intent == "threatening":
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": "",
                "reason": "Threatening or potentially harmful content. Flagged for manual review; do not engage automatically.",
                "generation_method": "local_contextual",
            }

        if intent == "abusive":
            if lang == "ta":
                reply = f"வணக்கம்{greet_name}. உங்கள் கருத்தை கவனத்தில் எடுத்துக்கொண்டோம். மரியாதையான உரையாடலை விரும்புகிறோம்; மேலும் விவரங்களுக்கு எங்கள் WhatsApp எண்ணில் தொடர்பு கொள்ளவும்."
            elif lang == "tanglish":
                reply = f"Vanakkam{greet_name}. Ungal karuththai gavanathil eduthukondom. Mariyathaiyana uraiyaadalai virumbugirom; melum vivarangaluku WhatsApp-il thodarbu kollavum."
            else:
                reply = f"Hello{greet_name}, thank you for sharing your thoughts. We value respectful conversation—if you have a specific concern, please reach out to us on WhatsApp so we can assist."
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": reply,
                "reason": "Abusive/hostile tone detected. Calm, respectful, non-confrontational response suggesting WhatsApp if needed.",
                "generation_method": "local_contextual",
            }

        if intent == "complaint":
            if lang == "ta":
                reply = f"வணக்கம்{greet_name}, உங்கள் சிரமத்திற்கு வருந்துகிறோம். உங்கள் விவரங்களை பாதுகாப்பாக சரிபார்க்க எங்கள் {brand} WhatsApp குழுவை தொடர்பு கொள்ளவும்."
            elif lang == "tanglish":
                reply = f"Vanakkam{greet_name}, ungalukku erpatta siramathukku varundhugirom. Ungal vivarangalai sariparkka {brand} WhatsApp-il message pannunga, udane help panrom."
            else:
                reply = f"Hello{greet_name}, we're sorry to hear about your experience. Please message {brand} on WhatsApp with your details so our team can look into this promptly."
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": reply,
                "reason": "Complaint detected. Empathetic, solution-oriented reply moving detailed resolution to WhatsApp without admitting unverified fault.",
                "generation_method": "local_contextual",
            }

        if intent == "negative":
            if lang == "ta":
                reply = f"வணக்கம்{greet_name}, உங்கள் நேர்மையான கருத்துக்கு நன்றி. எங்கள் {brand} சேவையை மேம்படுத்த இதை நிச்சயம் பயன்படுத்துவோம்."
            elif lang == "tanglish":
                reply = f"Vanakkam{greet_name}, ungal nermaiyana karuththukku nandri. {brand} sevaiyai mempaduththa idhai nichayam payanpaduthuvom."
            else:
                reply = f"Thank you for your honest feedback{greet_name}. We appreciate you sharing your perspective and will use it to improve {brand}."
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": reply,
                "reason": "Negative feedback detected. Understanding, professional, and non-defensive acknowledgment.",
                "generation_method": "local_contextual",
            }

        if intent == "general_inquiry":
            if lang == "ta":
                reply = f"வணக்கம்{greet_name}! {brand} குறித்த உங்கள் கேள்விக்கு நன்றி. தனிப்பட்ட வழிகாட்டுதலுக்கு எங்கள் WhatsApp எண்ணில் தொடர்பு கொள்ளவும்."
            elif lang == "tanglish":
                reply = f"Vanakkam{greet_name}! {brand} patriya ungal kelvikku nandri. Thani-patta vivarangaluku WhatsApp-il thodarbu kollunga."
            else:
                reply = f"Hello{greet_name}! Thanks for your question about {brand}. Feel free to reach out to us on WhatsApp for personalized details."
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": reply,
                "reason": "General/service inquiry detected. Friendly, informative response tailored to brand context.",
                "generation_method": "local_contextual",
            }

        if intent == "greeting":
            if lang == "ta":
                reply = f"வணக்கம்{greet_name}! {brand} பக்கத்திற்கு அன்புடன் வரவேற்கிறோம். 🙏"
            elif lang == "tanglish":
                reply = f"Vanakkam{greet_name}! {brand} pakkathirku anbudan varaverkirom! 🙏"
            else:
                reply = f"Hello{greet_name}! Warm welcome to {brand}. 🙏"
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": reply,
                "reason": "Greeting detected. Warm, welcoming reply in the commenter's language.",
                "generation_method": "local_contextual",
            }

        if intent in ("positive", "appreciation"):
            ctx_note = " தொடர்ந்த உரையாடலுக்கு நன்றி." if has_prev and lang == "ta" else ""
            if lang == "ta":
                reply = f"மிக்க நன்றி{greet_name}! {brand} மீதான உங்கள் அன்பும் ஆதரவும் எங்களுக்கு பெரிய ஊக்கம்.{ctx_note} 🙏✨"
            elif lang == "tanglish":
                reply = f"Romba nandri{greet_name}! {brand}-ku neenga tharum anbum support-um engalukku periya ookkam! 🙏✨"
            elif lang == "emoji":
                reply = f"Thank you so much{greet_name} for the love and support for {brand}! 🙏✨"
            else:
                reply = f"Thank you so much{greet_name} for your kind words and support for {brand}! 🙏✨"
            return {
                "language": lang,
                "sentiment": sentiment,
                "intent": intent,
                "suggested_reply": reply,
                "reason": "Positive/appreciation comment detected. Warm, personalized thank-you.",
                "generation_method": "local_contextual",
            }

        # Neutral
        if lang == "ta":
            reply = f"உங்கள் கருத்துக்கு நன்றி{greet_name}! {brand} உடன் தொடர்ந்து இணைந்திருங்கள். 😊"
        elif lang == "tanglish":
            reply = f"Ungal karuththukku nandri{greet_name}! {brand}-udan thodarndhu inaindhirungal. 😊"
        else:
            reply = f"Thank you for sharing your comment{greet_name}! Stay connected with {brand}. 😊"
        return {
            "language": lang,
            "sentiment": sentiment,
            "intent": intent,
            "suggested_reply": reply,
            "reason": "Neutral comment detected. Friendly, polite acknowledgment.",
            "generation_method": "local_contextual",
        }
    except Exception:
        return {
            "language": "en",
            "sentiment": "neutral",
            "intent": "neutral",
            "suggested_reply": "Thank you for your comment! Please reach out if you need any assistance.",
            "reason": "Fallback suggestion used because contextual generation encountered an error.",
            "generation_method": "fallback",
        }


def _extract_post_topic(post_caption: Optional[str]) -> str:
    """Extract a short, safe topic snippet from the post caption if available."""
    if not post_caption:
        return ""
    cleaned = re.sub(r"https?://\S+|#\S+", "", post_caption).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""
    first_sentence = re.split(r"[.!?\n]", cleaned)[0].strip()
    if len(first_sentence) > 60:
        first_sentence = first_sentence[:57].rstrip() + "..."
    return first_sentence


def _normalize_lang(lang: str) -> str:
    if lang in ("ta", "tanglish", "en"):
        return lang
    return "en"


def generate_three_level_suggestions(
    comment_text: str,
    commenter_name: Optional[str] = None,
    account_name: Optional[str] = None,
    platform: Optional[str] = None,
    post_caption: Optional[str] = None,
    previous_context: Optional[str] = None,
) -> Dict[str, object]:
    """Generate three genuinely distinct reply suggestions (Short, Medium, Detailed)
    personalized to the comment, post context, language, sentiment, intent, and brand.
    """
    cls = classify_comment(comment_text)
    raw_lang = cls["language"]
    lang = _normalize_lang(raw_lang)
    sentiment = cls["sentiment"]
    intent = cls["intent"]
    brand = _detect_brand(account_name, f"{comment_text or ''} {post_caption or ''}")
    name = (commenter_name or "").strip().lstrip("@")
    greet = f" {name}" if name and len(name) <= 24 else ""
    topic = _extract_post_topic(post_caption)
    has_prev = bool(previous_context and previous_context.strip())

    # Normalize intent aliases for display & routing
    intent_label_map = {
        "general_inquiry": "inquiry",
        "greeting": "positive",
    }
    normalized_intent = intent_label_map.get(intent, intent)
    if normalized_intent == "positive":
        lower_c = (comment_text or "").lower()
        if any(w in lower_c for w in ("thank", "thanks", "nandri", "nanri", "நன்றி", "appreciate", "helpful", "useful", "பயனுள்ள")):
            normalized_intent = "appreciation"

    if intent == "spam":
        return {
            "language": raw_lang,
            "sentiment": "spam",
            "intent": "spam",
            "short": "",
            "medium": "",
            "detailed": "",
            "recommend_no_reply": True,
            "manual_review_required": False,
            "reason": "Spam detected (promotional links, phone numbers, or solicitation). Recommended: No reply.",
            "generation_method": "local_contextual_3level",
        }

    if intent == "threatening":
        return {
            "language": raw_lang,
            "sentiment": "threatening",
            "intent": "threatening",
            "short": "",
            "medium": "",
            "detailed": "",
            "recommend_no_reply": True,
            "manual_review_required": True,
            "reason": "Threatening or potentially harmful content detected. Flagged for manual review.",
            "generation_method": "local_contextual_3level",
        }

    if intent == "abusive":
        if lang == "ta":
            short = f"வணக்கம்{greet}, உங்கள் கருத்தை பதிவு செய்ததற்கு நன்றி."
            medium = (
                f"வணக்கம்{greet}, உங்கள் கருத்தை நாங்கள் கவனத்தில் எடுத்துக்கொண்டோம். "
                f"மரியாதையான உரையாடலை {brand} எப்போதும் வரவேற்கிறது."
            )
            detailed = (
                f"வணக்கம்{greet}, உங்கள் கருத்தை பகிர்ந்ததற்கு நன்றி. "
                f"எங்கள் பக்கத்தில் அனைவருக்கும் மரியாதையான மற்றும் ஆரோக்கியமான உரையாடல் இருக்க வேண்டும் என விரும்புகிறோம். "
                f"உங்களுக்கு ஏதேனும் குறிப்பிட்ட உதவி தேவைப்பட்டால், தயவுசெய்து எங்கள் அதிகாரப்பூர்வ WhatsApp வழியாக தொடர்பு கொள்ளவும்."
            )
        elif lang == "tanglish":
            short = f"Vanakkam{greet}, ungal karuththai gavanathil eduthukondom."
            medium = (
                f"Vanakkam{greet}, ungal feedback-ai naangal kavanathil eduthukondom. "
                f"Mariyathaiyana uraiyaadalai {brand} eppodhum varaverkiradhu."
            )
            detailed = (
                f"Vanakkam{greet}, ungal karuththai pagirndhadharku nandri. "
                f"Engal community-il anaivarukkum mariyathaiyana matrum aarokkiyamana uraiyaadal irukka vendum ena virumbugirom. "
                f"Ungalukku ethavathu kurippitta udhavi thevaipattal, dayavuseidhu engal official WhatsApp moolam thodarbu kollavum."
            )
        else:
            short = f"Hello{greet}, thank you for sharing your perspective."
            medium = (
                f"Hello{greet}, we have noted your comment. "
                f"At {brand}, we value respectful and constructive conversation with our community."
            )
            detailed = (
                f"Hello{greet}, thank you for taking the time to comment. "
                f"While we welcome all feedback, we aim to keep our community space respectful for everyone. "
                f"If you have a specific concern you would like us to review, please message us directly on our official WhatsApp channel."
            )
        return {
            "language": raw_lang,
            "sentiment": sentiment,
            "intent": "abusive",
            "short": short,
            "medium": medium,
            "detailed": detailed,
            "recommend_no_reply": False,
            "manual_review_required": True,
            "reason": "Abusive or hostile language detected. Calm, respectful, non-confrontational suggestions generated for manual review.",
            "generation_method": "local_contextual_3level",
        }

    if intent == "complaint":
        topic_en = f" regarding \"{topic}\"" if topic else ""
        if lang == "ta":
            short = f"வணக்கம்{greet}, உங்கள் சிரமத்திற்கு வருந்துகிறோம்."
            medium = (
                f"வணக்கம்{greet}, உங்களுக்கு ஏற்பட்ட அனுபவத்திற்கு வருந்துகிறோம். "
                f"உங்கள் விவரங்களை சரிபார்க்க {brand} WhatsApp குழுவை தொடர்பு கொள்ளவும்."
            )
            detailed = (
                f"வணக்கம்{greet}, உங்கள் கருத்தை பகிர்ந்ததற்கு நன்றி, மேலும் உங்களுக்கு ஏற்பட்ட சிரமத்திற்கு வருந்துகிறோம். "
                f"இதை நாங்கள் தீவிரமாக கவனத்தில் எடுத்துக்கொள்கிறோம். "
                f"உங்கள் விவரங்களை பாதுகாப்பாக சரிபார்த்து உரிய வழிகாட்டுதல் வழங்க, எங்கள் {brand} WhatsApp எண்ணில் நேரடியாக செய்தி அனுப்பவும்."
            )
        elif lang == "tanglish":
            short = f"Vanakkam{greet}, ungalukku erpatta siramathukku varundhugirom."
            medium = (
                f"Vanakkam{greet}, ungal experience patri ketka varuthamaga ulladhu. "
                f"Ungal vivarangalai sariparkka {brand} WhatsApp-il message pannunga, udane paarkalaam."
            )
            detailed = (
                f"Vanakkam{greet}, ungal karuththai pagirndhadharku nandri, ungalukku erpatta siramathukku mannikkavum. "
                f"Idhai naangal gavanamaga eduthukolgirom. "
                f"Ungal vivarangalai paadhugaappaga saripaarkka, dayavuseidhu {brand} official WhatsApp-il direct-ah message anuppunga."
            )
        else:
            short = f"Hello{greet}, we're sorry to hear about your experience."
            medium = (
                f"Hello{greet}, thank you for bringing this to our attention{topic_en}. "
                f"We're sorry for any inconvenience and would like to look into this for you."
            )
            detailed = (
                f"Hello{greet}, we truly regret that your experience{topic_en} did not meet expectations. "
                f"Your feedback is important to {brand}, and we want to review the details carefully without making assumptions publicly. "
                f"Please send us a direct message on our official WhatsApp channel so our team can assist you properly."
            )
        return {
            "language": raw_lang,
            "sentiment": "negative",
            "intent": "complaint",
            "short": short,
            "medium": medium,
            "detailed": detailed,
            "recommend_no_reply": False,
            "manual_review_required": True,
            "reason": "Complaint detected. Empathetic, solution-oriented suggestions without unverified promises.",
            "generation_method": "local_contextual_3level",
        }

    if intent == "negative":
        if lang == "ta":
            short = f"வணக்கம்{greet}, உங்கள் நேர்மையான கருத்துக்கு நன்றி."
            medium = (
                f"வணக்கம்{greet}, உங்கள் கருத்தை பகிர்ந்ததற்கு மிக்க நன்றி. "
                f"எங்கள் {brand} பதிவுகளை மேலும் பயனுள்ளதாக மாற்ற இதை நிச்சயம் கருத்தில் கொள்வோம்."
            )
            detailed = (
                f"வணக்கம்{greet}, உங்கள் நேர்மையான பார்வையை பகிர்ந்ததற்கு நன்றி. "
                f"எங்கள் உள்ளடக்கமும் சேவையும் உங்களுக்கு இன்னும் பயனுள்ளதாக இருக்க வேண்டும் என்பதே {brand}-ன் நோக்கம். "
                f"எதை மேம்படுத்தலாம் என்ற உங்கள் ஆலோசனைகளையும் பகிர்ந்தால் எங்களுக்கு மிகவும் உதவியாக இருக்கும்."
            )
        elif lang == "tanglish":
            short = f"Vanakkam{greet}, ungal nermaiyana karuththukku nandri."
            medium = (
                f"Vanakkam{greet}, ungal feedback-ku mikka nandri. "
                f"{brand} content matrum sevaiyai melum sirappaga maatra idhai kandippaga payanpaduthuvom."
            )
            detailed = (
                f"Vanakkam{greet}, ungal nermaiyana karuththai pagirndhadharku romba nandri. "
                f"Engal pathivugal ungalukku unmaiyil payanulladhaga irukka vendum enbadhe {brand}-in nokkam. "
                f"Ethai mempaduthalaam endru ungalukku thonugiradho, adhaiyum pagirndhaal naangal kandippaga kavanippom."
            )
        else:
            short = f"Thank you for your honest feedback{greet}."
            medium = (
                f"Thank you for sharing your thoughts{greet}. "
                f"We value candid feedback and will keep this in mind as we improve {brand}."
            )
            detailed = (
                f"Hello{greet}, thank you for taking a moment to share your honest perspective. "
                f"At {brand}, we are always working to make our content and guidance clearer and more helpful. "
                f"If there is something specific you felt was missing, we'd appreciate hearing your suggestions."
            )
        return {
            "language": raw_lang,
            "sentiment": "negative",
            "intent": "negative",
            "short": short,
            "medium": medium,
            "detailed": detailed,
            "recommend_no_reply": False,
            "manual_review_required": True,
            "reason": "Negative feedback detected. Professional, non-defensive acknowledgment.",
            "generation_method": "local_contextual_3level",
        }

    if intent == "general_inquiry":
        topic_ref = f" ({topic})" if topic else ""
        if lang == "ta":
            short = f"வணக்கம்{greet}! உங்கள் கேள்விக்கு மிக்க நன்றி. 🙏"
            medium = (
                f"வணக்கம்{greet}! {brand} குறித்த உங்கள் கேள்விக்கு நன்றி{topic_ref}. "
                f"சரியான விவரங்களுக்கு எங்கள் WhatsApp எண்ணில் தொடர்பு கொள்ளவும்."
            )
            detailed = (
                f"வணக்கம்{greet}! இந்தப் பதிவு தொடர்பான உங்கள் ஆர்வத்திற்கும் கேள்விக்கும் மிக்க நன்றி. "
                f"ஒவ்வொருவருக்கும் தனிப்பட்ட விவரங்கள் மாறுபடும் என்பதால், பொது வெளியில் தவறான தகவல்களைத் தவிர்க்கிறோம். "
                f"தனிப்பட்ட வழிகாட்டுதலுக்கும் கட்டண விவரங்களுக்கும் எங்கள் {brand} WhatsApp குழுவை தொடர்பு கொள்ளுங்கள்."
            )
        elif lang == "tanglish":
            short = f"Vanakkam{greet}! Ungal kelvikku mikka nandri. 🙏"
            medium = (
                f"Vanakkam{greet}! {brand} patriya ungal kelvikku nandri{topic_ref}. "
                f"Thani-patta vivarangalukku engal WhatsApp-il thodarbu kollunga."
            )
            detailed = (
                f"Vanakkam{greet}! Indha post{topic_ref} patri ketta ungal kelvikku romba nandri. "
                f"Ovvoruvarukkum vivarangal verupadum enbadhaal, sariyana thagavalgalai thanipattamuraiyil pagirgirom. "
                f"Melum vivarangalukkum vazhikaattudhalukkum {brand} WhatsApp-il message pannunga, udane help panrom."
            )
        else:
            short = f"Hello{greet}! Thanks for asking—we'd be happy to help. 🙏"
            medium = (
                f"Hello{greet}! Thank you for your question about {brand}{topic_ref}. "
                f"Please message us on WhatsApp so we can share the exact details with you."
            )
            detailed = (
                f"Hello{greet}! Thank you for reaching out with your question{topic_ref}. "
                f"Because details can vary depending on your specific requirements, we prefer sharing personalized guidance directly rather than guessing in comments. "
                f"Feel free to connect with {brand} on WhatsApp and our team will be glad to assist you."
            )
        return {
            "language": raw_lang,
            "sentiment": "neutral",
            "intent": "inquiry",
            "short": short,
            "medium": medium,
            "detailed": detailed,
            "recommend_no_reply": False,
            "manual_review_required": False,
            "reason": "Inquiry detected. Helpful response guiding the commenter to personalized next steps.",
            "generation_method": "local_contextual_3level",
        }

    if intent in ("positive", "appreciation", "greeting"):
        prev_ta = " தொடர்ந்து இணைந்திருப்பதற்கு நன்றி." if has_prev else ""
        prev_en = " We appreciate your continued support." if has_prev else ""
        if lang == "ta":
            short = f"மிக்க நன்றி{greet}! உங்கள் அன்பான ஆதரவுக்கு நன்றிகள். 🙏✨"
            medium = (
                f"வணக்கம்{greet}! உங்கள் அன்பான கருத்துக்கு நெஞ்சார்ந்த நன்றி. "
                f"{brand} பதிவுகள் உங்களுக்கு பிடித்ததில் மகிழ்ச்சி.{prev_ta} 🙏"
            )
            detailed = (
                f"வணக்கம்{greet}! உங்கள் ஊக்கமளிக்கும் வார்த்தைகளுக்கும் அன்பிற்கும் மிக்க நன்றி. "
                f"இது போன்ற கருத்துகளே {brand} சார்பில் மேலும் பயனுள்ள மற்றும் தரமான பதிவுகளை உருவாக்க எங்களுக்கு பெரிய உத்வேகம் அளிக்கிறது.{prev_ta} "
                f"தொடர்ந்து எங்களுடன் இணைந்திருங்கள்! ✨🙏"
            )
        elif lang == "tanglish":
            short = f"Romba nandri{greet}! Ungal support-ku mikka nandri! 🙏✨"
            medium = (
                f"Vanakkam{greet}! Ungal anbaana karuththukku romba nandri. "
                f"{brand} post ungalukku pidichirukku-nu ketka romba santhosham! 🙏"
            )
            detailed = (
                f"Vanakkam{greet}! Ungal lovely feedback matrum support-ku manamarndha nandri. "
                f"Neenga tharum indha ookkam dhaan {brand}-la melum nalla matrum payanulla content podradhukku engalukku periya energy. "
                f"Thodarndhu engaludan inaindhirungal! ✨🙏"
            )
        else:
            short = f"Thank you so much{greet} for the kind support! 🙏✨"
            medium = (
                f"Hello{greet}! Thank you for your wonderful words and encouragement. "
                f"We're glad you enjoyed this {brand} post!{prev_en} 🙏"
            )
            detailed = (
                f"Hello{greet}! We truly appreciate you taking the time to leave such a thoughtful comment. "
                f"Support from community members like you motivates us at {brand} to keep sharing helpful and meaningful insights.{prev_en} "
                f"Stay connected with us for more updates! ✨🙏"
            )
        return {
            "language": raw_lang,
            "sentiment": "positive",
            "intent": normalized_intent,
            "short": short,
            "medium": medium,
            "detailed": detailed,
            "recommend_no_reply": False,
            "manual_review_required": False,
            "reason": f"{normalized_intent.capitalize()} comment detected. Warm, personalized 3-level suggestions.",
            "generation_method": "local_contextual_3level",
        }

    # Neutral fallback
    if lang == "ta":
        short = f"உங்கள் கருத்துக்கு நன்றி{greet}! 😊"
        medium = (
            f"வணக்கம்{greet}, உங்கள் கருத்தை பகிர்ந்ததற்கு நன்றி. "
            f"{brand} உடன் தொடர்ந்து இணைந்திருங்கள். 😊"
        )
        detailed = (
            f"வணக்கம்{greet}, எங்கள் பதிவில் உங்கள் கருத்தை பகிர்ந்ததற்கு மிக்க நன்றி. "
            f"சமூகத்தினரின் ஒவ்வொரு கருத்தும் எங்களுக்கு முக்கியமானது. "
            f"உங்களுக்கு ஏதேனும் கேள்விகள் இருந்தால் தயங்காமல் கேளுங்கள்! 🙏"
        )
    elif lang == "tanglish":
        short = f"Ungal karuththukku nandri{greet}! 😊"
        medium = (
            f"Vanakkam{greet}, ungal comment-ku nandri. "
            f"{brand}-udan thodarndhu inaindhirungal! 😊"
        )
        detailed = (
            f"Vanakkam{greet}, indha post-la ungal karuththai pagirndhadharku mikka nandri. "
            f"Engal community-oda ovvoru comment-um engalukku mukkiyam. "
            f"Ungalukku ethavathu kelvigal irundhaal thayangaamal kelunga! 🙏"
        )
    else:
        short = f"Thank you for sharing your comment{greet}! 😊"
        medium = (
            f"Hello{greet}, thanks for stopping by and leaving a comment. "
            f"Stay connected with {brand} for more updates! 😊"
        )
        detailed = (
            f"Hello{greet}, we appreciate you engaging with our post at {brand}. "
            f"Every comment helps us stay connected with our community. "
            f"If you have any questions or thoughts you'd like to explore further, feel free to let us know! 🙏"
        )
    return {
        "language": raw_lang,
        "sentiment": "neutral",
        "intent": "neutral",
        "short": short,
        "medium": medium,
        "detailed": detailed,
        "recommend_no_reply": False,
        "manual_review_required": False,
        "reason": "Neutral comment detected. Polite, engaging 3-level suggestions.",
        "generation_method": "local_contextual_3level",
    }
