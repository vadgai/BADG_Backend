#!/usr/bin/env python3
"""
Local Development Server for VADG
This script runs the backend with minimal dependencies for local testing
"""

import os
import sys
import logging
from pathlib import Path

# Add the Backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Run the local development server"""
    try:
        # Try to import the simplified app first
        logger.info("🚀 Starting VADG Local Development Server...")
        
        # Set environment variables for local development
        os.environ.setdefault("GOOGLE_API_KEY", "your_gemini_api_key_here")
        os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173")
        
        # Import and run the simplified app
        from app_simple import app
        import uvicorn
        
        logger.info("✅ Simplified app loaded successfully")
        logger.info("🌐 Starting server on http://localhost:8000")
        logger.info("📚 API docs available at http://localhost:8000/docs")
        logger.info("🛑 Press Ctrl+C to stop the server")
        
        # Run the server
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
        
    except ImportError as e:
        logger.error(f"❌ Import error: {e}")
        logger.error("💡 Make sure you're in the Backend directory and all dependencies are installed")
        logger.error("💡 Try: pip install fastapi uvicorn google-generativeai python-dotenv")
        return 1
        
    except Exception as e:
        logger.error(f"❌ Error starting server: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
