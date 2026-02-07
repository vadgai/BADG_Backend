"""
Minimal startup test to verify container works
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """Test all critical imports"""
    try:
        logger.info("Testing FastAPI import...")
        from fastapi import FastAPI
        logger.info("✅ FastAPI imported")
        
        logger.info("Testing uvicorn import...")
        import uvicorn
        logger.info("✅ Uvicorn imported")
        
        logger.info("Testing Google AI import...")
        import google.generativeai as genai
        logger.info("✅ Google AI imported")
        
        logger.info("Testing MongoDB import...")
        from motor.motor_asyncio import AsyncIOMotorClient
        logger.info("✅ MongoDB motor imported")
        
        logger.info("Testing spacy import...")
        import spacy
        logger.info("✅ Spacy imported")
        
        logger.info("Testing spacy model...")
        try:
            nlp = spacy.load("en_core_web_sm")
            logger.info("✅ Spacy model loaded")
        except Exception as e:
            logger.warning(f"⚠️ Spacy model not loaded: {e}")
        
        logger.info("\n✅ ALL IMPORTS SUCCESSFUL!\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_environment():
    """Test environment variables"""
    logger.info("Testing environment variables...")
    port = os.getenv("PORT", "8080")
    logger.info(f"PORT: {port}")
    
    api_key = os.getenv("GOOGLE_API_KEY", "")
    logger.info(f"GOOGLE_API_KEY: {'Set ✅' if api_key else 'Not set ⚠️'}")
    
    mongo_uri = os.getenv("MONGO_URI", "")
    logger.info(f"MONGO_URI: {'Set ✅' if mongo_uri else 'Not set ⚠️'}")
    
    return True

if __name__ == "__main__":
    logger.info("="*60)
    logger.info("VADG Backend Startup Test")
    logger.info("="*60)
    
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("")
    
    env_ok = test_environment()
    imports_ok = test_imports()
    
    if env_ok and imports_ok:
        logger.info("✅ System is ready!")
        sys.exit(0)
    else:
        logger.error("❌ System is NOT ready!")
        sys.exit(1)



