"""
BOQ AI Chat Client - Free rule-based assistant for BOQ/Tender queries.
Supports English and Bengali. No paid API required.
Optionally upgrades to OpenAI/Anthropic if API key is configured.
"""

import re
from typing import List, Dict, Any, Optional
from .config import settings


# ─── Knowledge Base ───────────────────────────────────────────────────────────

BOQ_KNOWLEDGE = {
    "zone": {
        "en": """Bangladesh tender zones (LGED/PWD):
• Zone A: Dhaka, Mymensingh divisions
• Zone B: Chattogram, Sylhet divisions  
• Zone C: Rajshahi, Rangpur divisions
• Zone D: Khulna, Barishal, Gopalganj divisions
Zone affects the SOR rate — always confirm your project district maps to the correct zone.""",
        "bn": """বাংলাদেশ টেন্ডার জোন (LGED/PWD):
• জোন A: ঢাকা, ময়মনসিংহ বিভাগ
• জোন B: চট্টগ্রাম, সিলেট বিভাগ
• জোন C: রাজশাহী, রংপুর বিভাগ
• জোন D: খুলনা, বরিশাল, গোপালগঞ্জ বিভাগ
জোন SOR রেটকে প্রভাবিত করে — সবসময় নিশ্চিত করুন আপনার জেলা সঠিক জোনে আছে।""",
    },
    "sor": {
        "en": """SOR (Schedule of Rates) is the official government rate list.
Agencies: BWDB (water/flood), LGED (rural development), PWD (public works).
• BWDB SOR: single rate per code (e.g. 04-120, 40-370-20)
• LGED/PWD SOR: zone-based rates (A/B/C/D columns)
If BOQ rate exceeds SOR by >10%, it's flagged as MISMATCH. 1-10% is VARIANCE.""",
        "bn": """SOR (শিডিউল অব রেটস) হলো সরকারি অফিসিয়াল রেট তালিকা।
সংস্থা: BWDB (পানি/বন্যা), LGED (গ্রামীণ উন্নয়ন), PWD (পূর্ত বিভাগ)।
• BWDB SOR: প্রতি কোডে একটি রেট (যেমন ০৪-১২০)
• LGED/PWD SOR: জোন ভিত্তিক রেট (A/B/C/D কলাম)
BOQ রেট SOR এর চেয়ে >১০% বেশি হলে MISMATCH। ১-১০% হলে VARIANCE।""",
    },
    "mismatch": {
        "en": """Rate Mismatch means the BOQ quoted rate differs from SOR by more than 10%.
Actions to take:
1. Verify correct zone was used for SOR lookup
2. Check if item code is correctly mapped
3. Review if description matches — similar items may have different codes
4. If genuinely higher, add justification note
5. Consult the latest SOR revision for your agency""",
        "bn": """রেট মিসম্যাচ মানে BOQ উদ্ধৃত রেট SOR থেকে ১০% এর বেশি ভিন্ন।
করণীয়:
১. সঠিক জোন ব্যবহার হয়েছে কিনা যাচাই করুন
২. আইটেম কোড সঠিকভাবে ম্যাপ হয়েছে কিনা পরীক্ষা করুন
৩. বিবরণ মিলছে কিনা দেখুন — একই রকম আইটেমের ভিন্ন কোড থাকতে পারে
৪. যদি সত্যিই বেশি হয়, জাস্টিফিকেশন নোট যোগ করুন
৫. আপনার সংস্থার সর্বশেষ SOR সংশোধনী পরামর্শ নিন""",
    },
    "boq": {
        "en": """BOQ (Bill of Quantities) is the itemized list of work with quantities and rates.
Structure: Item No | Code | Description | Qty | Unit | Rate | Amount
Upload formats: Excel (.xlsx) with 'boq' in filename, or PDF BOQ.
Tips:
• Ensure item codes follow agency format (e.g. 04-120 for BWDB)
• Use standard units: Nos, Sqm, Cum, Rmt, Kg, MT
• All amounts auto-calculated: Qty × SOR Rate""",
        "bn": """BOQ (বিল অব কোয়ান্টিটিজ) হলো কাজের আইটেম তালিকা পরিমাণ ও রেট সহ।
কাঠামো: আইটেম নং | কোড | বিবরণ | পরিমাণ | একক | রেট | পরিমাণ
আপলোড ফরম্যাট: 'boq' নামে Excel (.xlsx) অথবা PDF BOQ।
টিপস:
• আইটেম কোড সংস্থার ফরম্যাট অনুসরণ করুন (যেমন BWDB এর জন্য ০৪-১২০)
• স্ট্যান্ডার্ড একক ব্যবহার করুন: Nos, Sqm, Cum, Rmt, Kg, MT
• সব পরিমাণ স্বয়ংক্রিয়ভাবে হিসাব হয়: পরিমাণ × SOR রেট""",
    },
    "egp": {
        "en": """eGP (Electronic Government Procurement) is Bangladesh's online tender system.
Website: https://www.eprocure.gov.bd
Key fields: Tender ID, Closing Date, Opening Date
• Tender ID format: e.g. 552225
• Always match tender ID when uploading documents
• Documents exported from this system can be used for audit trail""",
        "bn": """eGP (ইলেকট্রনিক গভর্নমেন্ট প্রকিউরমেন্ট) বাংলাদেশের অনলাইন টেন্ডার সিস্টেম।
ওয়েবসাইট: https://www.eprocure.gov.bd
মূল ক্ষেত্র: টেন্ডার আইডি, সমাপ্তি তারিখ, উন্মোচন তারিখ
• টেন্ডার আইডি ফরম্যাট: যেমন ৫৫২২২৫
• ডকুমেন্ট আপলোড করার সময় সবসময় টেন্ডার আইডি মেলান""",
    },
    "export": {
        "en": """Export options available:
• Excel (.xlsx): Full BOQ diff with color coding (green=match, red=mismatch)
• PDF: Printable review sheet for site engineers
• DOCX: Word document for internal review and sign-off
• CSV: Raw data for further analysis in Excel/Sheets
Access exports from the Dashboard after running a BOQ comparison.""",
        "bn": """রপ্তানি বিকল্পসমূহ:
• Excel (.xlsx): রঙ কোডিং সহ পূর্ণ BOQ ডিফ (সবুজ=মিল, লাল=মিসম্যাচ)
• PDF: সাইট ইঞ্জিনিয়ারদের জন্য প্রিন্টযোগ্য রিভিউ শিট
• DOCX: অভ্যন্তরীণ পর্যালোচনার জন্য Word ডকুমেন্ট
• CSV: Excel/Sheets এ আরও বিশ্লেষণের জন্য কাঁচা ডেটা""",
    },
    "work_types": {
        "en": """Work type classification:
• Earthwork: excavation, filling, embankment, cutting
• Concrete: RCC, lean concrete, CC blocks, cement concrete
• Protection: revetment, block pitching, geo-bags, hard rock, boulder
• Finishing: plaster, tiles, painting, brick work
• Electrical: street light, cable, MCB, solar, pole
Summary sheet shows quantities aggregated by work type with unit conversions (cft→cum, sft→sqm).""",
        "bn": """কাজের ধরন শ্রেণিবিভাগ:
• মাটির কাজ: খনন, ভরাট, বাঁধ, কাটা
• কংক্রিট: RCC, লিন কংক্রিট, CC ব্লক
• সুরক্ষা: রিভেটমেন্ট, ব্লক পিচিং, জিও-ব্যাগ, পাথর
• ফিনিশিং: পলেস্তারা, টাইলস, পেইন্টিং, ইটের কাজ
• বৈদ্যুতিক: রাস্তার আলো, তার, MCB, সোলার""",
    },
}

GREETINGS = {
    "en": ["hello", "hi", "hey", "help", "start", "assist"],
    "bn": ["হ্যালো", "সালাম", "নমস্কার", "সাহায্য", "শুরু"],
}

GREETING_RESPONSE = {
    "en": """👋 Welcome to Procurement Flow Specialist BD Assistant!

I can help you with:
• **Zone & SOR rates** — understanding rate zones for BWDB/LGED/PWD
• **BOQ upload & parsing** — how to format your Excel/PDF BOQ
• **Rate mismatches** — what to do when rates don't match SOR
• **Export & reports** — Excel, PDF, DOCX export options
• **eGP system** — Bangladesh tender platform guidance
• **Work type classification** — earthwork, concrete, protection etc.

Ask me anything about your tender or BOQ! (Type in English or বাংলা)""",
    "bn": """👋 Procurement Flow Specialist BD সহকারীতে স্বাগতম!

আমি আপনাকে সাহায্য করতে পারি:
• **জোন ও SOR রেট** — BWDB/LGED/PWD রেট জোন বোঝা
• **BOQ আপলোড ও পার্সিং** — Excel/PDF BOQ ফরম্যাট করা
• **রেট মিসম্যাচ** — রেট SOR এর সাথে না মিললে কী করবেন
• **এক্সপোর্ট ও রিপোর্ট** — Excel, PDF, DOCX রপ্তানি
• **eGP সিস্টেম** — বাংলাদেশ টেন্ডার প্ল্যাটফর্ম গাইড

আপনার টেন্ডার বা BOQ সম্পর্কে যেকোনো প্রশ্ন করুন! (ইংরেজি বা বাংলায় লিখুন)""",
}


def detect_language(text: str) -> str:
    """Detect if text contains Bengali characters."""
    bengali_range = range(0x0980, 0x09FF)
    for char in text:
        if ord(char) in bengali_range:
            return "bn"
    return "en"


def find_topic(text: str, lang: str) -> Optional[str]:
    """Match text to a knowledge topic."""
    text_lower = text.lower()
    topic_keywords = {
        "zone": ["zone", "জোন", "district", "জেলা", "area", "এলাকা"],
        "sor": ["sor", "schedule of rate", "রেট শিডিউল", "rate schedule", "official rate", "সরকারি রেট"],
        "mismatch": ["mismatch", "মিসম্যাচ", "variance", "ভেরিয়েন্স", "differ", "ভিন্ন", "wrong rate", "ভুল রেট"],
        "boq": ["boq", "bill of quantities", "বিল অব", "upload", "আপলোড", "parse", "পার্স", "excel"],
        "egp": ["egp", "eprocure", "tender", "টেন্ডার", "tender id", "closing date", "procurement"],
        "export": ["export", "রপ্তানি", "download", "ডাউনলোড", "pdf", "xlsx", "docx", "csv", "report", "রিপোর্ট"],
        "work_types": ["work type", "কাজের ধরন", "earthwork", "মাটির কাজ", "concrete", "protection", "সুরক্ষা"],
    }
    for topic, keywords in topic_keywords.items():
        if any(kw in text_lower for kw in keywords):
            return topic
    return None


def is_greeting(text: str, lang: str) -> bool:
    text_lower = text.lower().strip()
    greetings = GREETINGS.get(lang, []) + GREETINGS.get("en", [])
    return any(g in text_lower for g in greetings) or len(text_lower.split()) <= 2


def rule_based_response(message: str, history: List[Dict], lang: str) -> str:
    """Generate a helpful response using the knowledge base."""
    if is_greeting(message, lang):
        return GREETING_RESPONSE.get(lang, GREETING_RESPONSE["en"])

    topic = find_topic(message, lang)
    if topic and topic in BOQ_KNOWLEDGE:
        return BOQ_KNOWLEDGE[topic].get(lang, BOQ_KNOWLEDGE[topic]["en"])

    # Context-aware fallback
    if lang == "bn":
        return f"""আপনার প্রশ্ন: "{message}"

আমি নিশ্চিত নই এই বিষয়ে। তবে আমি এগুলো সম্পর্কে সাহায্য করতে পারি:
• **জোন**: "zone কী?" বা "জোন A কোথায়?"
• **SOR রেট**: "SOR কী?" বা "রেট মিসম্যাচ কেন?"
• **BOQ আপলোড**: "কীভাবে Excel আপলোড করব?"
• **এক্সপোর্ট**: "PDF কীভাবে ডাউনলোড করব?"
• **eGP**: "টেন্ডার আইডি কোথায় পাব?"

আরও নির্দিষ্ট প্রশ্ন করুন!"""
    return f"""I received: "{message}"

I'm not sure about that specific query. I can help with:
• **Zones**: "What is Zone A?" or "Which zone is Dhaka?"
• **SOR Rates**: "What is SOR?" or "Why mismatch?"
• **BOQ Upload**: "How to upload Excel BOQ?"
• **Exports**: "How to download PDF report?"
• **eGP**: "What is the tender ID format?"

Try asking a more specific question!"""


class BOQChatClient:
    """
    Free rule-based Procurement Flow Specialist BD assistant.
    Falls back to OpenAI/Anthropic if API key is configured.
    """

    def __init__(self):
        self.use_openai = bool(settings.OPENAI_API_KEY)
        self.use_anthropic = bool(settings.ANTHROPIC_API_KEY)

    async def chat(
        self,
        user_id: str,
        messages: List[Dict[str, str]],
        language: str = "en",
    ) -> Dict[str, Any]:
        last_msg = messages[-1]["content"] if messages else ""
        lang = language if language in ("en", "bn") else detect_language(last_msg)

        # Try OpenAI if configured
        if self.use_openai:
            return await self._openai_chat(messages, lang)

        # Free rule-based response
        history = messages[:-1]
        response = rule_based_response(last_msg, history, lang)
        return {
            "success": True,
            "content": response,
            "tokens_used": 0,
            "engine": "rule-based (free)",
        }

    async def _openai_chat(self, messages: List[Dict], lang: str) -> Dict[str, Any]:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            system = (
                "You are a BOQ (Bill of Quantities) expert assistant for Bangladesh government tenders. "
                "You understand BWDB, LGED, PWD SOR rates, zone classifications, eGP system, "
                "and Bengali tender terminology. Be concise and practical."
            )
            if lang == "bn":
                system += " Respond in formal Bengali (বাংলা) using standard tender terminology."

            full_messages = [{"role": "system", "content": system}] + messages
            res = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=full_messages,
                max_tokens=600,
            )
            return {
                "success": True,
                "content": res.choices[0].message.content,
                "tokens_used": res.usage.total_tokens,
                "engine": "openai",
            }
        except Exception as e:
            # Fallback to rule-based
            last_msg = messages[-1]["content"] if messages else ""
            return {
                "success": True,
                "content": rule_based_response(last_msg, messages[:-1], lang),
                "tokens_used": 0,
                "engine": "rule-based (fallback)",
            }
