

def mask_username(username: str) -> str:
    """Public, privacy-preserving display name for live feeds: 'player' -> 'pl***r'."""
    if not username:
        return "***"
    if len(username) <= 3:
        return username[0] + "***"
    return f"{username[:2]}***{username[-1]}"
