"""
Admin Insights API Routes
Phase 3: Deep insights endpoints for admin dashboard
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.responses import JSONResponse

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics import (
    calculate_funnel_metrics,
    FunnelStep,
    track_funnel_step,
    aggregate_disease_usage,
    get_disease_trends,
    get_top_diseases,
    aggregate_location_stats,
    get_location_stats,
    aggregate_device_stats,
    get_device_stats,
)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/insights", tags=["admin", "insights"])

# Try to import JWT auth for admin endpoints
try:
    from auth.jwt_auth import get_current_admin as get_jwt_admin
    JWT_AVAILABLE = True
except ImportError:
    logger.warning("JWT auth not available for admin insights")
    JWT_AVAILABLE = False
    def get_jwt_admin():
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="JWT auth not available")


# Funnel Analytics Endpoints

@router.get("/funnel")
async def get_funnel_analytics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get funnel analytics with step-by-step conversion tracking.
    
    Returns:
    - Total users entering each step
    - Drop-off percentages
    - Average time spent per step
    - Conversion rates between steps
    """
    try:
        # Check database availability
        from database.connection import is_database_available
        if not is_database_available():
            logger.info("Database not available - returning empty funnel metrics")
            return {
                "success": True,
                "data": {
                    "total_sessions": 0,
                    "total_completions": 0,
                    "overall_conversion_rate": 0,
                    "step_metrics": {},
                    "conversions": {}
                }
            }
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
        
        metrics = await calculate_funnel_metrics(start_dt, end_dt)
        
        return {
            "success": True,
            "data": metrics
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.error(f"Error getting funnel analytics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get funnel analytics: {str(e)}")


# Disease Usage Endpoints

@router.get("/diseases")
async def get_disease_usage(
    limit: int = Query(10, description="Number of top diseases to return"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get top diseases by prediction count with usage statistics.
    """
    try:
        # Check database availability
        from database.connection import is_database_available
        if not is_database_available():
            logger.info("Database not available - returning empty disease list")
            return {
                "success": True,
                "data": {
                    "top_diseases": [],
                    "count": 0
                }
            }
        
        top_diseases = await get_top_diseases(limit=limit, start_date=start_date, end_date=end_date)
        
        return {
            "success": True,
            "data": {
                "top_diseases": top_diseases or [],
                "count": len(top_diseases) if top_diseases else 0
            }
        }
    except Exception as e:
        logger.error(f"Error getting disease usage: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get disease usage: {str(e)}")


@router.get("/diseases/{disease_name}")
async def get_disease_details(
    disease_name: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    granularity: str = Query("daily", description="Time granularity (daily, weekly, monthly)"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get detailed disease statistics including trends.
    """
    try:
        # Check database availability
        from database.connection import is_database_available
        if not is_database_available():
            logger.info("Database not available - returning empty trends")
            return {
                "success": True,
                "data": {
                    "disease_name": disease_name,
                    "current_stats": {},
                    "trends": {
                        "disease_name": disease_name,
                        "period": {
                            "start_date": start_date or (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
                            "end_date": end_date or datetime.utcnow().strftime("%Y-%m-%d"),
                            "granularity": granularity
                        },
                        "trends": [],
                        "total_predictions": 0,
                        "total_confirmations": 0
                    }
                }
            }
        
        # Get trends
        trends = await get_disease_trends(
            disease_name=disease_name,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity
        )
        
        # Handle error response from get_disease_trends
        if isinstance(trends, dict) and trends.get("error"):
            logger.warning(f"Error getting trends: {trends.get('error')}")
            trends = {
                "disease_name": disease_name,
                "period": {
                    "start_date": start_date or (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d"),
                    "end_date": end_date or datetime.utcnow().strftime("%Y-%m-%d"),
                    "granularity": granularity
                },
                "trends": [],
                "total_predictions": 0,
                "total_confirmations": 0
            }
        
        # Get current day stats
        today = datetime.utcnow().strftime("%Y-%m-%d")
        current_stats = await aggregate_disease_usage(disease_name, today)
        
        # Handle error response from aggregate_disease_usage
        if isinstance(current_stats, dict) and current_stats.get("error"):
            current_stats = {}
        
        return {
            "success": True,
            "data": {
                "disease_name": disease_name,
                "current_stats": current_stats,
                "trends": trends
            }
        }
    except Exception as e:
        logger.error(f"Error getting disease details: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get disease details: {str(e)}")


# Location Analytics Endpoints

@router.get("/locations")
async def get_location_analytics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    group_by: str = Query("country", description="Grouping level (country, state, city)"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get location analytics with geographic usage patterns.
    """
    try:
        stats = await get_location_stats(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
        
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error getting location analytics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get location analytics: {str(e)}")


@router.get("/locations/{country}")
async def get_location_details(
    country: str,
    state: Optional[str] = Query(None, description="State/Province"),
    city: Optional[str] = Query(None, description="City"),
    date: Optional[str] = Query(None, description="Date (YYYY-MM-DD)"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get detailed location statistics for a specific location.
    """
    try:
        stats = await aggregate_location_stats(
            country=country,
            state=state,
            city=city,
            date=date
        )
        
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error getting location details: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get location details: {str(e)}")


# Device Analytics Endpoints

@router.get("/devices")
async def get_device_analytics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    group_by: str = Query("device_type", description="Grouping level (device_type, browser, os)"),
    current_admin=Depends(get_jwt_admin)
):
    """
    Get device analytics with browser, OS, and performance metrics.
    """
    try:
        stats = await get_device_stats(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
        
        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        logger.error(f"Error getting device analytics: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get device analytics: {str(e)}")

