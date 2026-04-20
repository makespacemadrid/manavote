SUPPORTED_LANGUAGES = {"en", "es"}


def resolve_language(requested, fallback="en"):
    return requested if requested in SUPPORTED_LANGUAGES else fallback
