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

        if intent == "positive":
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
