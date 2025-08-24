import json
from typing import List, Dict, Any, Optional
from .config import ADMIN_FILE

def read_admins() -> List[Dict[str, Any]]:
    if not ADMIN_FILE.exists():
        return []
    try:
        with ADMIN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("admins", [])
    except Exception:
        return []

def write_admins(admins: List[Dict[str, Any]]) -> None:
    tmp = ADMIN_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump({"admins": admins}, f, indent=2)
    tmp.replace(ADMIN_FILE)

def add_admin(chat_id: int, username: Optional[str]) -> bool:
    admins = read_admins()
    if any(a["chat_id"] == chat_id for a in admins):
        return False
    admins.append({"chat_id": chat_id, "username": username, "receive": False})
    write_admins(admins)
    return True

def get_receiving_admins() -> List[int]:
    return [a["chat_id"] for a in read_admins() if a.get("receive", False)]

def remove_admin(chat_id: int) -> bool:
    admins = read_admins()
    new_admins = [a for a in admins if a["chat_id"] != chat_id]
    if len(new_admins) == len(admins):
        return False
    return write_admins(new_admins)

def list_admin_chat_ids() -> List[int]:
    return [a["chat_id"] for a in read_admins()]
