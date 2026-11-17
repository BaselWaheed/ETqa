"""Language and direction for templates. Phase 1 has a handful of strings, so they live here rather than in
gettext catalogs (compiling .mo files needs GNU gettext, which is awkward on locked-down Windows machines)."""

STRINGS = {
    "en": {
        "sign_in": "Sign in", "username": "Username", "password": "Password",
        "tagline": "Answers from your QA documentation, with sources.",
        "sign_out": "Sign out", "your_collections": "Your collections",
        "no_collections": "No collections are shared with you yet. Ask an administrator to give your group access.",
        "read": "Read", "manage": "Manage", "role": "Role", "no_role": "No role assigned",
        "administration": "Administration",
        "later": "Ask questions in Chat, add files in Documents, and design tests in Test cases.",
        "switch_to": "العربية", "switch_code": "ar",
        "nav_home": "Home", "nav_chat": "Chat", "nav_documents": "Documents", "nav_testcases": "Test cases",
        "ask_placeholder": "Ask about your documentation. Arabic or English.", "ask": "Ask",
        "all_collections": "All my collections", "new_chat": "New chat", "history": "Recent chats",
        "unsaved_note": "Your chats are not saved. Refreshing the page ends this conversation.",
        "queued": "Queued", "position": "position", "searching": "Searching documents",
        "generating": "Writing the answer", "checking": "Draft, checking sources", "failed": "Failed",
        "retrying": "Retrying after an error", "cancel": "Cancel", "cancelled": "Cancelled",
        "ai_down": "The AI service is unavailable. Your request is queued and will run when it is back.",
        "sources": "Sources", "unsupported": "This answer has no valid source citations. Treat it as unverified.",
        "insufficient": "No supporting documentation found.", "helpful": "Helpful", "not_helpful": "Not helpful",
        "thanks": "Feedback saved.", "upload": "Upload", "collection": "Collection", "file": "File",
        "title_optional": "Title (optional)", "no_upload": "You cannot upload to any collection.",
        "doc_title": "Title", "status": "Status", "updated": "Updated", "actions": "Actions", "download": "Download",
        "reingest": "Process again", "archive": "Archive", "confirm_archive": "Archive this document?",
        "no_documents": "No documents yet.", "pending": "Waiting", "processing": "Processing", "ready": "Ready",
        "needs_review": "Needs review", "semantic_pending": "keyword search only until indexing finishes",
        "tc_source": "Requirements", "tc_document": "From a document", "tc_text": "Describe the requirement",
        "tc_instructions": "Extra instructions (optional)", "template": "Template", "generate": "Generate test cases",
        "fill_priority": "Fill priority and component", "sets": "Generated sets", "export": "Export to Excel",
        "cases": "cases", "assumption": "Assumption", "no_sets": "No test cases generated yet.",
        "choose_document": "Choose a document", "view": "View", "duplicates": "duplicates removed",
        "invalid": "invalid removed", "partial": "Partial", "running": "Running", "error": "Error",
    },
    "ar": {
        "sign_in": "تسجيل الدخول", "username": "اسم المستخدم", "password": "كلمة المرور",
        "tagline": "إجابات من وثائق ضمان الجودة الخاصة بك، مع ذكر المصادر.",
        "sign_out": "تسجيل الخروج", "your_collections": "مجموعاتك",
        "no_collections": "لم تتم مشاركة أي مجموعة معك بعد. اطلب من المسؤول منح مجموعتك صلاحية الوصول.",
        "read": "قراءة", "manage": "إدارة", "role": "الدور", "no_role": "لم يتم تعيين دور",
        "administration": "الإدارة",
        "later": "اطرح أسئلتك في المحادثة، وأضف الملفات في المستندات، وصمّم الاختبارات في حالات الاختبار.",
        "switch_to": "English", "switch_code": "en",
        "nav_home": "الرئيسية", "nav_chat": "المحادثة", "nav_documents": "المستندات", "nav_testcases": "حالات الاختبار",
        "ask_placeholder": "اسأل عن وثائقك بالعربية أو بالإنجليزية.", "ask": "اسأل",
        "all_collections": "كل مجموعاتي", "new_chat": "محادثة جديدة", "history": "المحادثات الأخيرة",
        "unsaved_note": "لا يتم حفظ محادثاتك. تحديث الصفحة يُنهي هذه المحادثة.",
        "queued": "في قائمة الانتظار", "position": "الترتيب", "searching": "جارٍ البحث في المستندات",
        "generating": "جارٍ كتابة الإجابة", "checking": "مسودة، جارٍ التحقق من المصادر", "failed": "تعذّر الإكمال",
        "retrying": "إعادة المحاولة بعد خطأ", "cancel": "إلغاء", "cancelled": "تم الإلغاء",
        "ai_down": "خدمة الذكاء الاصطناعي غير متاحة حاليًا. طلبك في قائمة الانتظار وسيُنفَّذ عند عودتها.",
        "sources": "المصادر", "unsupported": "هذه الإجابة بلا مصادر موثّقة. تعامل معها على أنها غير مؤكدة.",
        "insufficient": "لم يتم العثور على وثائق داعمة.", "helpful": "مفيدة", "not_helpful": "غير مفيدة",
        "thanks": "تم حفظ رأيك.", "upload": "رفع", "collection": "المجموعة", "file": "الملف",
        "title_optional": "العنوان (اختياري)", "no_upload": "لا يمكنك الرفع إلى أي مجموعة.",
        "doc_title": "العنوان", "status": "الحالة", "updated": "آخر تحديث", "actions": "إجراءات", "download": "تنزيل",
        "reingest": "إعادة المعالجة", "archive": "أرشفة", "confirm_archive": "هل تريد أرشفة هذا المستند؟",
        "no_documents": "لا توجد مستندات بعد.", "pending": "بانتظار المعالجة", "processing": "قيد المعالجة", "ready": "جاهز",
        "needs_review": "يحتاج إلى مراجعة", "semantic_pending": "البحث بالكلمات فقط حتى تكتمل الفهرسة",
        "tc_source": "المتطلبات", "tc_document": "من مستند", "tc_text": "صف المتطلب",
        "tc_instructions": "تعليمات إضافية (اختياري)", "template": "القالب", "generate": "إنشاء حالات الاختبار",
        "fill_priority": "تعبئة الأولوية والمكوّن", "sets": "المجموعات المُنشأة", "export": "تصدير إلى Excel",
        "cases": "حالة", "assumption": "افتراض", "no_sets": "لم يتم إنشاء حالات اختبار بعد.",
        "choose_document": "اختر مستندًا", "view": "عرض", "duplicates": "مكررة أُزيلت",
        "invalid": "غير صالحة أُزيلت", "partial": "جزئي", "running": "قيد التنفيذ", "error": "خطأ",
    },
}


def ui_language(request) -> dict:
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        lang = user.preferred_language
    else:
        lang = request.COOKIES.get("etqa_lang", "en")
    lang = lang if lang in STRINGS else "en"
    return {"ui_lang": lang, "ui_dir": "rtl" if lang == "ar" else "ltr", "t": STRINGS[lang]}
