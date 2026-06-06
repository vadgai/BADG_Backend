"""
Contact Form Routes
Handles contact form submissions and lead capture
"""

import logging
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends, Request
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Try to import database models, make them optional
try:
    from database.models import ContactSubmissionCreate, ContactSubmission
    MODELS_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Database models not available - creating dummy models")
    MODELS_AVAILABLE = False
    # Create Pydantic models for different form types
    class ContactPageSubmission(BaseModel):
        """Contact page form submission"""
        name: str
        email: EmailStr
        message: str
        phone: Optional[str] = None
        form_type: str = "contact_page"

    class PricingPageSubmission(BaseModel):
        """Pricing page contact sales form submission"""
        name: str  # This will be contactPerson
        email: EmailStr
        message: str
        phone: Optional[str] = None
        organizationName: Optional[str] = None
        preferredModel: Optional[str] = None
        form_type: str = "pricing_page"

    # Union type for both form types
    class ContactSubmissionCreate(BaseModel):
        name: str
        email: EmailStr
        message: str
        phone: Optional[str] = None
        organizationName: Optional[str] = None
        preferredModel: Optional[str] = None
        form_type: str = "contact_page"  # Default to contact page

    class ContactSubmission(ContactSubmissionCreate):
        timestamp: datetime = datetime.utcnow()
        ip_address: Optional[str] = None
        user_agent: Optional[str] = None
        email_sent: bool = False

# Try to import database connection functions
try:
    from database.connection import (
        get_contact_submissions_collection,
        is_database_available
    )
    DB_CONNECTION_AVAILABLE = True
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning("Database connection not available")
    DB_CONNECTION_AVAILABLE = False
    # Dummy functions
    def get_contact_submissions_collection():
        return None
    def is_database_available():
        return False

# Try to import rate limit middleware, make it optional
try:
    from middleware.rate_limit import rate_limit_middleware
except ImportError:
    # Create a dummy rate limit middleware if not available
    def rate_limit_middleware():
        def dummy_dependency():
            return None
        return dummy_dependency

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["contact"])


def send_contact_email(contact_data: ContactSubmissionCreate) -> bool:
    """
    Send contact form submission email to VADG team

    Args:
        contact_data: Contact form data

    Returns:
        bool: True if email sent successfully
    """
    try:
        import os

        # Email configuration from environment variables
        SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
        SENDER_EMAIL = os.getenv("SENDER_EMAIL", "vadg.office@gmail.com")
        SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "")
        RECIPIENT_EMAILS_STR = os.getenv("RECIPIENT_EMAILS", "vadg.office@gmail.com,krishna@vadg.in")
        RECIPIENT_EMAILS = [email.strip() for email in RECIPIENT_EMAILS_STR.split(",") if email.strip()]

        # Check if email is configured
        if not SENDER_PASSWORD:
            logger.warning("Email not configured - SENDER_PASSWORD not set")
            return False

        # Create message
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = ", ".join(RECIPIENT_EMAILS)

        # Set subject based on form type
        if getattr(contact_data, 'organizationName', None) or getattr(contact_data, 'preferredModel', None):
            msg['Subject'] = f"New Contact Sales Inquiry from {contact_data.name}"
        else:
            msg['Subject'] = f"New Contact Form Submission from {contact_data.name}"

        # Email body based on form type
        if getattr(contact_data, 'organizationName', None) or getattr(contact_data, 'preferredModel', None):
            # Pricing page contact sales form
            body = f"""
New Contact Sales Inquiry

Organization: {getattr(contact_data, 'organizationName', 'Not provided')}
Contact Person: {contact_data.name}
Email: {contact_data.email}
Phone: {contact_data.phone or 'Not provided'}
Preferred Model: {getattr(contact_data, 'preferredModel', 'Not specified')}

Message:
{contact_data.message}

---
This is an automated message from the VADG pricing page contact form.
Please respond within 48 hours as indicated on the website.
"""
        else:
            # Regular contact page form
            body = f"""
New Contact Form Submission

Name: {contact_data.name}
Email: {contact_data.email}
Phone: {contact_data.phone or 'Not provided'}

Message:
{contact_data.message}

---
This is an automated message from the VADG contact page.
Please respond within 48 hours as indicated on the website.
"""

        msg.attach(MIMEText(body, 'plain'))

        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, text)
        server.quit()
        logger.info(f"Contact email sent successfully to {RECIPIENT_EMAILS}")
        return True

    except Exception as e:
        logger.error(f"Failed to send contact email: {str(e)}")
        return False


@router.post("/contact")
async def submit_contact_form(
    contact_data: ContactSubmissionCreate,
    request: Request,
    _=Depends(rate_limit_middleware)
):
    """
    Submit contact form data and send notification email

    This endpoint:
    1. Validates the contact form data
    2. Stores the submission in database (if available)
    3. Sends notification email to VADG team
    4. Returns success response

    Args:
        contact_data: Contact form submission data
        request: FastAPI request object

    Returns:
        Success response with submission confirmation
    """
    logger.info(f"Contact form submission received from: {contact_data.email}")

    try:
        # Store in database if available
        if is_database_available():
            contact_collection = get_contact_submissions_collection()

            submission = ContactSubmission(
                **contact_data.dict(),
                timestamp=datetime.utcnow(),
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get('user-agent'),
                email_sent=False  # Will be updated after email send
            )

            await contact_collection.insert_one(submission.dict())
            logger.info(f"Contact submission stored in database for: {contact_data.email}")
        else:
            logger.warning("Database unavailable - storing contact submission in memory")
            from in_memory_storage import store_contact_in_memory
            import uuid
            await store_contact_in_memory({
                "_id": str(uuid.uuid4()),
                **contact_data.dict(),
                "timestamp": datetime.utcnow().isoformat(),
                "ip_address": request.client.host if request.client else None,
                "user_agent": request.headers.get('user-agent'),
                "email_sent": False,
            })

        # Send notification email
        email_sent = send_contact_email(contact_data)

        # Update email_sent status if database is available
        if is_database_available() and contact_collection:
            await contact_collection.update_one(
                {"email": contact_data.email, "timestamp": submission.timestamp},
                {"$set": {"email_sent": email_sent}}
            )

        return {
            "success": True,
            "message": "Thank you for your inquiry! We'll get back to you within 48 hours.",
            "email_sent": email_sent
        }

    except Exception as e:
        logger.error(f"Error processing contact form submission: {str(e)}")

        # Return success anyway (graceful degradation)
        # The email might still be sent even if database fails
        try:
            email_sent = send_contact_email(contact_data)
        except:
            email_sent = False

        return {
            "success": True,
            "message": "Thank you for your inquiry! We'll get back to you within 48 hours.",
            "email_sent": email_sent,
            "warning": "Database temporarily unavailable, but your message has been received"
        }


@router.get("/contact/health")
async def contact_health_check():
    """
    Health check for contact form functionality

    Returns:
        Health status of contact form endpoints
    """
    health_status = {
        "contact_endpoint": "available",
        "database": "available" if is_database_available() else "unavailable",
        "email_service": "configured" if os.getenv("SENDER_PASSWORD") else "not_configured",
        "timestamp": datetime.utcnow().isoformat()
    }

    # Get submission count if database is available
    if is_database_available():
        try:
            contact_collection = get_contact_submissions_collection()
            if contact_collection:
                health_status["submissions_count"] = await contact_collection.count_documents({})
        except:
            health_status["submissions_count"] = "error"

    return health_status