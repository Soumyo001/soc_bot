from typing import List, Dict, Any, Optional
import json

def escape_md_fragment(text: str) -> str:
    """Escape for MarkdownV2, for dynamic fragments only (NOT whole message)."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text

def format_alert(summary: str, severity: int,
                 details: Optional[Dict[str, Any]] = None,
                 tags: Optional[List[str]] = None) -> str:
    sev = max(0, min(10, int(severity or 5)))
    icons = ["🟢","🟢","🟢","🟡","🟡","🟡","🟠","🟠","🔴","🔴","🔥"]
    # Escape only user-provided fields
    t = f"{icons[sev]} {escape_md_fragment(f"*{str(summary)}*")}"
    if tags:
        safe_tags = " ".join(f"{escape_md_fragment(f"#{str(x)}")}" for x in tags)
        t += f" \n{safe_tags}"
    if details is not None:
        pretty = json.dumps(details, indent=2, ensure_ascii=False)
        # Put raw JSON inside code block so we don't need to escape inside
        t += f"\n*Details:*\n```json\n{pretty}\n```"
    return t