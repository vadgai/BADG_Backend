import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://vadg_db_user:Yh96u81FmZucN6p8@cluster0.zyu50c9.mongodb.net/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "vadg")

async def test():
    try:
        print(f"Connecting to MongoDB: {MONGO_URI}")
        client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB_NAME]
        await client.admin.command('ping')
        print("✅ Connection successful!")
        collections = await db.list_collection_names()
        print(f"Collections: {collections}")
        client.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
