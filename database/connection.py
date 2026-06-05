"""
MongoDB Database Connection Module
Uses Motor for async MongoDB operations
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Try to import motor, but make it optional
try:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
    MOTOR_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Motor not available - database features will be disabled")
    MOTOR_AVAILABLE = False
    # Create dummy classes for type hints
    class AsyncIOMotorClient:
        pass
    class AsyncIOMotorDatabase:
        pass
    class ConnectionFailure(Exception):
        pass
    class ServerSelectionTimeoutError(Exception):
        pass

load_dotenv()
logger = logging.getLogger(__name__)

# MongoDB configuration
# IMPORTANT: Set MONGO_URI in environment variables for production
# Supports MONGO_URI or legacy MONGODB_URL from env.example
_raw_mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URL")
MONGO_URI = _raw_mongo_uri.strip() if _raw_mongo_uri else None
MONGO_DB_NAME = (os.getenv("MONGO_DB_NAME") or os.getenv("MONGODB_DATABASE") or "vadg").strip()
MONGO_MAX_POOL_SIZE = int(os.getenv("MONGO_MAX_POOL_SIZE", "50"))
MONGO_MIN_POOL_SIZE = int(os.getenv("MONGO_MIN_POOL_SIZE", "10"))

# Global database client
_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None
_db_available = False


async def connect_to_mongodb():
    """
    Connect to MongoDB with async Motor driver
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    global _client, _database, _db_available
    
    if not MOTOR_AVAILABLE:
        logger.warning("Motor not available - skipping MongoDB connection")
        _db_available = False
        return False
    
    if not MONGO_URI:
        logger.warning("MONGO_URI not set - skipping MongoDB connection")
        logger.info("System will continue with in-memory storage only")
        _db_available = False
        return False
    
    try:
        logger.info("Connecting to MongoDB...")
        
        # Create async MongoDB client
        _client = AsyncIOMotorClient(
            MONGO_URI,
            maxPoolSize=MONGO_MAX_POOL_SIZE,
            minPoolSize=MONGO_MIN_POOL_SIZE,
            serverSelectionTimeoutMS=5000,  # 5 second timeout
            connectTimeoutMS=10000,  # 10 second connection timeout
        )
        
        # Get database
        _database = _client[MONGO_DB_NAME]
        
        # Test connection with ping
        await _client.admin.command('ping')
        
        _db_available = True
        logger.info("✅ MongoDB connected successfully to database: %s", MONGO_DB_NAME)
        
        # Create indexes
        await create_indexes()
        
        return True
        
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        _db_available = False
        logger.error("❌ MongoDB connection failed: %s", str(e))
        logger.warning("System will continue with in-memory storage only")
        return False
    except Exception as e:
        _db_available = False
        logger.error("❌ Unexpected error connecting to MongoDB: %s", str(e))
        logger.warning("System will continue with in-memory storage only")
        return False


async def close_mongodb_connection():
    """Close MongoDB connection"""
    global _client, _database, _db_available
    
    if _client:
        _client.close()
        logger.info("MongoDB connection closed")
    
    _client = None
    _database = None
    _db_available = False


def get_database() -> Optional[AsyncIOMotorDatabase]:
    """
    Get MongoDB database instance
    
    Returns:
        AsyncIOMotorDatabase or None if not connected
    """
    return _database if _db_available else None


def is_database_available() -> bool:
    """Check if database is available"""
    return _db_available


async def create_indexes():
    """Create database indexes for better performance"""
    if _database is None:
        return
    
    try:
        # form_submissions indexes
        await _database.form_submissions.create_index("session_id", unique=True)
        await _database.form_submissions.create_index("timestamp")
        await _database.form_submissions.create_index([("timestamp", -1)])  # Descending for recent first
        
        # admin indexes
        await _database.admin.create_index("username", unique=True)
        
        # visit_logs indexes
        await _database.visit_logs.create_index("timestamp")
        await _database.visit_logs.create_index("page_name")
        await _database.visit_logs.create_index([("timestamp", -1)])

        # New analytics collections: visits and reports
        await _database.visits.create_index("timestamp")
        await _database.visits.create_index("page")
        await _database.visits.create_index("sessionId")
        await _database.visits.create_index("type")
        await _database.visits.create_index([("timestamp", -1)])
        # TTL index: auto-delete visits older than 30 days (30 * 24 * 60 * 60 = 2592000)
        await _database.visits.create_index("timestamp", expireAfterSeconds=2592000)

        await _database.reports.create_index("timestamp")
        await _database.reports.create_index("predictedDisease")
        await _database.reports.create_index([("timestamp", -1)])
        # TTL index: auto-delete reports older than 30 days
        await _database.reports.create_index("timestamp", expireAfterSeconds=2592000)

        # Partial reports collection for last-stage drop-offs
        await _database.partial_reports.create_index("createdAt")
        await _database.partial_reports.create_index("sessionId")
        await _database.partial_reports.create_index([("createdAt", -1)])
        # TTL index: auto-delete partial reports older than 30 days
        await _database.partial_reports.create_index("createdAt", expireAfterSeconds=2592000)
        
        # users indexes (temporary sessions)
        await _database.users.create_index("session_id", unique=True)
        await _database.users.create_index("last_activity")
        await _database.users.create_index(
            "last_activity",
            expireAfterSeconds=86400  # Auto-delete after 24 hours
        )

        # contact_submissions indexes
        await _database.contact_submissions.create_index("email")
        await _database.contact_submissions.create_index("timestamp")
        await _database.contact_submissions.create_index([("timestamp", -1)])  # Descending for recent first

        # report_analyzer_submissions indexes
        await _database.report_analyzer_submissions.create_index("timestamp")
        await _database.report_analyzer_submissions.create_index("patient_name")
        await _database.report_analyzer_submissions.create_index([("timestamp", -1)])
        await _database.report_analyzer_submissions.create_index(
            "timestamp", expireAfterSeconds=2592000
        )
        
        logger.info("✅ Database indexes created successfully")
        
    except Exception as e:
        logger.error("Error creating indexes: %s", str(e))


# Collection accessors
def get_form_submissions_collection():
    """Get form_submissions collection"""
    db = get_database()
    return db.form_submissions if db is not None else None


def get_admin_collection():
    """Get admin collection"""
    db = get_database()
    return db.admin if db is not None else None


def get_visit_logs_collection():
    """Get visit_logs collection"""
    db = get_database()
    return db.visit_logs if db is not None else None


def get_users_collection():
    """Get users (temporary sessions) collection"""
    db = get_database()
    return db.users if db is not None else None


def get_contact_submissions_collection():
    """Get contact_submissions collection"""
    db = get_database()
    return db.contact_submissions if db is not None else None


def get_reports_collection():
    """Get analytics reports collection"""
    db = get_database()
    return db.reports if db is not None else None


def get_visits_collection():
    """Get analytics visits collection"""
    db = get_database()
    return db.visits if db is not None else None


def get_partial_reports_collection():
    """Get partial reports collection"""
    db = get_database()
    return db.partial_reports if db is not None else None


def get_report_analyzer_submissions_collection():
    """Get report analyzer submissions collection"""
    db = get_database()
    return db.report_analyzer_submissions if db is not None else None

