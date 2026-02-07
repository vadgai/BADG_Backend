"""
Disease Usage Aggregator
Tracks per-disease statistics and trends
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from collections import defaultdict

from .models import DiseaseUsageDocument
from database.connection import get_database, is_database_available


async def aggregate_disease_usage(
    disease_name: str,
    date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Aggregate disease usage statistics for a specific disease and date.
    
    Args:
        disease_name: Disease name
        date: Date in YYYY-MM-DD format (defaults to today)
        
    Returns:
        Aggregated statistics
    """
    if date is None:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    if not is_database_available():
        return {"error": "Database not available"}
    
    db = get_database()
    if db is None:
        return {"error": "Database not available"}
    
    # Get accuracy logs for this disease
    accuracy_logs_collection = db.accuracy_logs
    model_logs_collection = db.model_logs
    
    # Query accuracy logs
    accuracy_query = {
        "predicted_disease": disease_name,
        "timestamp": {
            "$gte": datetime.strptime(date, "%Y-%m-%d"),
            "$lt": datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)
        }
    }
    
    accuracy_logs = []
    async for log in accuracy_logs_collection.find(accuracy_query):
        accuracy_logs.append(log)
    
    # Count predictions and confirmations
    prediction_count = len(accuracy_logs)
    confirmation_count = len([log for log in accuracy_logs if log.get("confirmed_disease")])
    
    # Calculate accuracy metrics
    confirmed_logs = [log for log in accuracy_logs if log.get("confirmed_disease")]
    correct_count = len([log for log in confirmed_logs if log.get("is_correct", False)])
    accuracy_rate = correct_count / confirmation_count if confirmation_count > 0 else None
    
    # Calculate average confidence
    confidence_scores = [log.get("confidence_score") for log in accuracy_logs if log.get("confidence_score")]
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else None
    
    # Outcome distribution
    outcome_distribution = defaultdict(int)
    for log in confirmed_logs:
        bucket = log.get("accuracy_bucket", "unknown")
        outcome_distribution[bucket] += 1
    
    # Update or create disease usage document
    disease_usage_collection = db.disease_usage
    
    existing = await disease_usage_collection.find_one({
        "disease_name": disease_name,
        "date": date
    })
    
    disease_usage = DiseaseUsageDocument(
        disease_name=disease_name,
        date=date,
        prediction_count=prediction_count,
        confirmation_count=confirmation_count,
        accuracy_rate=accuracy_rate,
        avg_confidence=avg_confidence,
        outcome_distribution=dict(outcome_distribution)
    )
    
    if existing:
        await disease_usage_collection.update_one(
            {"disease_name": disease_name, "date": date},
            {"$set": disease_usage.dict()}
        )
    else:
        await disease_usage_collection.insert_one(disease_usage.dict())
    
    return disease_usage.dict()


async def get_disease_trends(
    disease_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "daily"  # daily, weekly, monthly
) -> Dict[str, Any]:
    """
    Get disease usage trends over time.
    
    Args:
        disease_name: Disease name
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        granularity: Time granularity (daily, weekly, monthly)
        
    Returns:
        Trend data with time series
    """
    if not is_database_available():
        return {"error": "Database not available"}
    
    db = get_database()
    if db is None:
        return {"error": "Database not available"}
    
    if start_date is None:
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
    
    disease_usage_collection = db.disease_usage
    
    query = {
        "disease_name": disease_name,
        "date": {
            "$gte": start_date,
            "$lte": end_date
        }
    }
    
    trends = []
    async for doc in disease_usage_collection.find(query).sort("date", 1):
        trends.append({
            "date": doc.get("date"),
            "prediction_count": doc.get("prediction_count", 0),
            "confirmation_count": doc.get("confirmation_count", 0),
            "accuracy_rate": doc.get("accuracy_rate"),
            "avg_confidence": doc.get("avg_confidence"),
        })
    
    return {
        "disease_name": disease_name,
        "period": {
            "start_date": start_date,
            "end_date": end_date,
            "granularity": granularity
        },
        "trends": trends,
        "total_predictions": sum(t.get("prediction_count", 0) for t in trends),
        "total_confirmations": sum(t.get("confirmation_count", 0) for t in trends),
    }


async def get_top_diseases(
    limit: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get top diseases by prediction count.
    
    Args:
        limit: Number of top diseases to return
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        
    Returns:
        List of top diseases with statistics
    """
    if not is_database_available():
        return []
    
    db = get_database()
    if db is None:
        return []
    
    if start_date is None:
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
    
    disease_usage_collection = db.disease_usage
    
    # Aggregate by disease name
    pipeline = [
        {
            "$match": {
                "date": {"$gte": start_date, "$lte": end_date}
            }
        },
        {
            "$group": {
                "_id": "$disease_name",
                "total_predictions": {"$sum": "$prediction_count"},
                "total_confirmations": {"$sum": "$confirmation_count"},
                "avg_accuracy": {"$avg": "$accuracy_rate"},
                "avg_confidence": {"$avg": "$avg_confidence"},
            }
        },
        {
            "$sort": {"total_predictions": -1}
        },
        {
            "$limit": limit
        }
    ]
    
    top_diseases = []
    async for result in disease_usage_collection.aggregate(pipeline):
        top_diseases.append({
            "disease_name": result["_id"],
            "total_predictions": result.get("total_predictions", 0),
            "total_confirmations": result.get("total_confirmations", 0),
            "avg_accuracy": result.get("avg_accuracy"),
            "avg_confidence": result.get("avg_confidence"),
        })
    
    return top_diseases

