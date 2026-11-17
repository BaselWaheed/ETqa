"""Initial role defaults (architecture doc, section 6). Roles are Django groups; admins may change them later."""

ADMIN = "Admin"
REVIEWER = "Reviewer"
QA_ENGINEER = "QA Engineer"
VIEWER = "Viewer"
ROLES = [ADMIN, REVIEWER, QA_ENGINEER, VIEWER]

ROLE_CAPABILITIES: dict[str, set[str]] = {
    ADMIN: {
        "use_chat", "save_chat_history", "search_documents", "upload_documents", "delete_documents",
        "generate_test_cases", "export_excel", "give_feedback", "review_knowledge", "manage_users",
        "manage_collections", "configure_models", "view_audit", "manage_any_job",
    },
    REVIEWER: {
        "use_chat", "save_chat_history", "search_documents", "upload_documents", "generate_test_cases",
        "export_excel", "give_feedback", "review_knowledge",
    },
    # QA Engineers upload only where a collection grant gives their group "manage".
    QA_ENGINEER: {
        "use_chat", "save_chat_history", "search_documents", "generate_test_cases", "export_excel", "give_feedback",
    },
    # Viewers chat without saved history and cannot give feedback (decision log).
    VIEWER: {"use_chat", "search_documents"},
}

# Django model permissions the Admin role needs to use the admin site.
ADMIN_MODEL_PERMISSIONS = [
    ("accounts", "user", ("add", "change", "view")),
    ("auth", "group", ("add", "change", "view")),
    ("access", "collection", ("add", "change", "view")),
    ("access", "collectiongrant", ("add", "change", "delete", "view")),
]
