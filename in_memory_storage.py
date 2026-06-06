"""
In-memory storage for admin data when MongoDB is not available
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

# Global in-memory storage
in_memory_visits: List[Dict[str, Any]] = []
in_memory_reports: List[Dict[str, Any]] = []
in_memory_contacts: List[Dict[str, Any]] = []
in_memory_report_analyzer_submissions: List[Dict[str, Any]] = []
in_memory_career_applications: List[Dict[str, Any]] = []


async def store_visit_in_memory(visit_data: Dict[str, Any]):
    """Store visit data in memory"""
    visit_data["timestamp"] = datetime.utcnow()
    in_memory_visits.append(visit_data)


async def store_report_in_memory(report_data: Dict[str, Any]):
    """Store report data in memory"""
    report_data["timestamp"] = datetime.utcnow()
    in_memory_reports.append(report_data)


async def store_contact_in_memory(contact_data: Dict[str, Any]):
    """Store contact data in memory"""
    contact_data["timestamp"] = datetime.utcnow()
    in_memory_contacts.append(contact_data)


async def store_report_analyzer_submission_in_memory(submission_data: Dict[str, Any]):
    """Store report analyzer submission in memory"""
    import uuid
    submission_data.setdefault("_id", str(uuid.uuid4()))
    submission_data["timestamp"] = datetime.utcnow()
    in_memory_report_analyzer_submissions.insert(0, submission_data)


async def store_career_application_in_memory(application_data: Dict[str, Any]):
    """Store career application metadata in memory (resume not stored in memory blob)."""
    application_data["timestamp"] = datetime.utcnow()
    in_memory_career_applications.insert(0, application_data)


def get_report_analyzer_submissions_from_memory(skip: int = 0, limit: int = 20) -> Dict[str, Any]:
    """Get report analyzer submissions from memory"""
    total = len(in_memory_report_analyzer_submissions)
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "submissions": in_memory_report_analyzer_submissions[skip : skip + limit],
    }


def delete_report_from_memory(session_id: str) -> bool:
    """Delete a diagnosis report from memory by sessionId or session_id."""
    global in_memory_reports
    before = len(in_memory_reports)
    in_memory_reports = [
        item for item in in_memory_reports
        if item.get("sessionId") != session_id and item.get("session_id") != session_id
    ]
    return len(in_memory_reports) < before


def get_contact_by_id_from_memory(contact_id: str) -> Optional[Dict[str, Any]]:
    """Get a single contact submission from memory by id."""
    for contact in in_memory_contacts:
        if contact.get("id") == contact_id:
            return contact
    return None


def delete_report_analyzer_submission_from_memory(submission_id: str) -> bool:
    """Delete a report analyzer submission from memory by _id"""
    global in_memory_report_analyzer_submissions
    before = len(in_memory_report_analyzer_submissions)
    in_memory_report_analyzer_submissions = [
        item for item in in_memory_report_analyzer_submissions if item.get("_id") != submission_id
    ]
    return len(in_memory_report_analyzer_submissions) < before


def get_visits_from_memory(page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """Get visits from memory"""
    start = (page - 1) * limit
    end = start + limit
    return {
        "total": len(in_memory_visits),
        "page": page,
        "limit": limit,
        "visits": in_memory_visits[start:end]
    }


def get_reports_from_memory(page: int = 1, limit: int = 20) -> Dict[str, Any]:
    """Get reports from memory"""
    start = (page - 1) * limit
    end = start + limit
    return {
        "total": len(in_memory_reports),
        "page": page,
        "limit": limit,
        "reports": in_memory_reports[start:end]
    }


def get_contacts_from_memory(page: int = 1, limit: int = 20, form_type: str = None) -> Dict[str, Any]:
    """Get contacts from memory"""
    filtered_contacts = in_memory_contacts
    if form_type:
        filtered_contacts = [c for c in in_memory_contacts if c.get("form_type") == form_type]

    start = (page - 1) * limit
    end = start + limit
    return {
        "total": len(filtered_contacts),
        "page": page,
        "limit": limit,
        "contacts": filtered_contacts[start:end]
    }


def get_dashboard_stats_from_memory() -> Dict[str, Any]:
    """Get dashboard statistics from memory"""
    total_visits = len(in_memory_visits)
    total_reports = len(in_memory_reports)
    total_contacts = len(in_memory_contacts)

    # Calculate completion rate (simplified)
    completion_rate = 75.0  # Default completion rate

    return {
        "totalVisits": total_visits,
        "totalReports": total_reports,
        "totalContacts": total_contacts,
        "completionRate": completion_rate
    }
