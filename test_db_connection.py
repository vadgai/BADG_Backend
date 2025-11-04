#!/usr/bin/env python3
"""
Test MongoDB connection script
"""
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://vadg_db_user:Yh96u81FmZucN6p8@cluster0.zyu50c9.mongodb.net/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "vadg")

async def test_connection():
    try:
        print(f"Connecting to MongoDB: {MONGO_URI}")
        client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB_NAME]

        # Test ping
        await client.admin.command('ping')
        print("✅ MongoDB connection successful!")

        # Test database access
        collections = await db.list_collection_names()
        print(f"✅ Database '{MONGO_DB_NAME}' accessible. Collections: {collections}")

        # Try to insert a test document
        test_doc = {"test": True, "timestamp": "2025-11-03"}
        result = await db.test_collection.insert_one(test_doc)
        print(f"✅ Test document inserted with ID: {result.inserted_id}")

        # Clean up
        await db.test_collection.delete_one({"_id": result.inserted_id})
        print("✅ Test document cleaned up")

        client.close()
        return True

    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_connection())
    exit(0 if success else 1)
