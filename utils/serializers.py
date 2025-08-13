# utils/serializers.py
from bson import ObjectId

def str_id(obj_id):
    return str(obj_id) if isinstance(obj_id, ObjectId) else obj_id

def serialize_fiche(doc: dict) -> dict:
    if not doc:
        return {}
    doc["_id"] = str_id(doc.get("_id"))
    if "user_id" in doc:
        doc["user_id"] = str_id(doc.get("user_id"))
    return doc
