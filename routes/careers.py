"""
Careers application routes — job applications with resume upload
"""

import logging
import os
import uuid
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

import smtplib
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from in_memory_storage import store_career_application_in_memory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/careers", tags=["careers"])

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx"}
MAX_RESUME_SIZE = 5 * 1024 * 1024  # 5MB


def _send_career_application_email(
    name: str,
    email: str,
    job_title: str,
    notes: Optional[str],
    resume_bytes: bytes,
    resume_filename: str,
) -> bool:
    try:
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        sender_email = os.getenv("SENDER_EMAIL", "vadg.office@gmail.com")
        sender_password = os.getenv("SENDER_PASSWORD", "")
        recipients_str = os.getenv("RECIPIENT_EMAILS", "vadg.office@gmail.com,krishna@vadg.in")
        recipients = [e.strip() for e in recipients_str.split(",") if e.strip()]

        if not sender_password:
            logger.warning("Career application email skipped — SENDER_PASSWORD not set")
            return False

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = f"VADG Careers Application: {job_title} — {name}"

        body = f"""New career application via VADG website

Position: {job_title}
Name: {name}
Email: {email}

Notes / Questions:
{notes or 'None provided'}

Resume attached: {resume_filename}
---
Automated message from VADG careers page.
"""
        msg.attach(MIMEText(body, "plain"))

        attachment = MIMEApplication(resume_bytes, Name=resume_filename)
        attachment["Content-Disposition"] = f'attachment; filename="{resume_filename}"'
        msg.attach(attachment)

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipients, msg.as_string())
        server.quit()
        logger.info("Career application email sent for %s — %s", job_title, email)
        return True
    except Exception as exc:
        logger.error("Failed to send career application email: %s", exc)
        return False


@router.post("/apply")
async def submit_career_application(
    request: Request,
    name: str = Form(..., min_length=2, max_length=120),
    email: str = Form(..., max_length=254),
    job_title: str = Form(..., min_length=2, max_length=200),
    notes: Optional[str] = Form(None, max_length=3000),
    resume: UploadFile = File(...),
):
    """Submit a job application with resume file."""
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")

    if not resume.filename:
        raise HTTPException(status_code=400, detail="Resume file is required")

    ext = Path(resume.filename).suffix.lower()
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resume type. Allowed: {', '.join(sorted(ALLOWED_RESUME_EXTENSIONS))}",
        )

    content = await resume.read()
    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=400, detail="Resume must be 5MB or smaller")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Resume file is empty")

    application_id = str(uuid.uuid4())

    record = {
        "_id": application_id,
        "id": application_id,
        "name": name.strip(),
        "email": email.strip().lower(),
        "job_title": job_title.strip(),
        "notes": (notes or "").strip() or None,
        "resume_filename": resume.filename,
        "resume_size_bytes": len(content),
        "form_type": "careers_page",
        "timestamp": datetime.utcnow().isoformat(),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }

    await store_career_application_in_memory(record)
    email_sent = _send_career_application_email(
        name=record["name"],
        email=record["email"],
        job_title=record["job_title"],
        notes=record["notes"],
        resume_bytes=content,
        resume_filename=resume.filename,
    )

    return {
        "success": True,
        "message": "Thank you! Your application has been received. We'll review it and get back to you soon.",
        "application_id": application_id,
        "email_sent": email_sent,
    }
