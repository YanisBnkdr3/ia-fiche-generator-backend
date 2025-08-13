# db.py
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

client = None
db = None

async def connect_to_mongo():
    global client, db
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DB_NAME", "ia_fiche_generator")

    try:
        client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        await db.command("ping")  # Vérifie la connexion
        print("✅ Connecté à MongoDB Atlas")
    except Exception as e:
        print(f"❌ Erreur de connexion à MongoDB : {e}")
        raise e

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("🔌 Connexion MongoDB fermée")
        client = None

def get_db():
    from fastapi import HTTPException
    if db is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return db
