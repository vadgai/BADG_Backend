"""
In-memory storage for admin data when MongoDB is not available
"""

from typing import List, Dict, Any
from datetime import datetime

# Global in-memory storage
in_memory_visits: List[Dict[str, Any]] = []
in_memory_reports: List[Dict[str, Any]] = []
in_memory_contacts: List[Dict[str, Any]] = []


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
