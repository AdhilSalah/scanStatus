from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import MongoClient
from typing import List, Dict, Any, Optional
import httpx
import asyncio
from datetime import datetime
import os
from bson import ObjectId

# Pydantic models
class ScanJob(BaseModel):
    id: str
    database: str
    collection: str
    status: str
    tenant_id:str
    domain:str
    is_latest: bool
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    duration: Optional[int] = None
    documents_processed: Optional[int] = None

class RestartResponse(BaseModel):
    success: bool
    message: str
    restarted_jobs: int

# FastAPI app
app = FastAPI(title="Scan Job Manager", description="MongoDB Scan Job Management System")

# MongoDB connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27018")
client = MongoClient(MONGO_URI)

# HTTP client for external API calls
http_client = httpx.AsyncClient()

@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()

def serialize_mongo_doc(doc):
    """Convert MongoDB document to JSON serializable format"""
    if doc is None:
        return None
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == "_id":
                result["id"] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result
    return doc

async def get_scan_jobs_by_status(status_filter: str = None,search:str = None) -> List[ScanJob]:
    """Get scan jobs from all databases, optionally filtered by status"""
    jobs = []
    
    # Get all database names
    db_names = client.list_database_names()
    
    for db_name in db_names:
        # Skip system databases
        if db_name in ['admin', 'local', 'config']:
            continue
            
        try:
            db = client[db_name]
            
            # Check if scan_job collection exists
            if 'scan_job' in db.list_collection_names():
                collection = db['scan_job']
                
                # Build query based on status filter
                query = {"is_latest": True}
                if search:
                    query["$or"] = [
                        {"domain": {"$regex": search, "$options": "i"}},
                        {"tenant_id": {"$regex": search, "$options": "i"}},
                        {"error_message": {"$regex": search, "$options": "i"}}
                    ]
                if status_filter:
                    if status_filter == "failed":
                        query["status"] = "failed"
                    elif status_filter == "completed":
                        query["status"] = {"$in": ["completed", "success"]}
                    elif status_filter == "running":
                        query["status"] = {"$in": ["running", "in_progress"]}
                
                # Find jobs matching the criteria
                job_docs = collection.find(query).sort("created_at", -1)
                
                for doc in job_docs:
                    serialized_doc = serialize_mongo_doc(doc)
                    if serialized_doc:
                        # Calculate duration if we have both created_at and completed_at
                        duration = None
                        if (serialized_doc.get("created_at") and 
                            serialized_doc.get("completed_at")):
                            try:
                                created = datetime.fromisoformat(serialized_doc["created_at"].replace('Z', '+00:00'))
                                completed = datetime.fromisoformat(serialized_doc["completed_at"].replace('Z', '+00:00'))
                                duration = int((completed - created).total_seconds())
                            except:
                                pass
                        
                        scan_job = ScanJob(
                            id=serialized_doc.get("id", ""),
                            database=db_name,
                            collection="scan_job",
                            status=serialized_doc.get("status", "unknown"),
                            is_latest=serialized_doc.get("is_latest", False),
                            tenant_id=serialized_doc.get("tenant_id", ""),
                            domain=serialized_doc.get("domain", ""),
                            created_at=serialized_doc.get("created_at"),
                            completed_at=serialized_doc.get("completed_at"),
                            error_message=serialized_doc.get("error_message"),
                            duration=duration,
                            documents_processed=serialized_doc.get("documents_processed")
                        )
                        jobs.append(scan_job)
                        
        except Exception as e:
            print(f"Error accessing database {db_name}: {str(e)}")
            continue
    
    return jobs

async def restart_scan(job_id: str) -> bool:
    """Restart a scan by calling the external API"""
    try:
        response = await http_client.post("http://we.in.se/scan_all")
        return response.status_code == 200
    except Exception as e:
        print(f"Error restarting scan for job {job_id}: {str(e)}")
        return False

@app.get("/")
async def read_root():
    """Serve the main HTML page"""
    return HTMLResponse(content="""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Iris</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/alpinejs/3.13.3/cdn.min.js" defer></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/axios/1.6.2/axios.min.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #0f172a;
            min-height: 100vh;
            color: #ffffff;
            background-image: 
                radial-gradient(circle at 20% 80%, rgba(120, 119, 198, 0.3) 0%, transparent 50%),
                radial-gradient(circle at 80% 20%, rgba(255, 119, 198, 0.15) 0%, transparent 50%),
                radial-gradient(circle at 40% 40%, rgba(120, 200, 255, 0.1) 0%, transparent 50%);
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .header {
            text-align: center;
            margin-bottom: 3rem;
            animation: fadeInUp 0.8s ease-out;
        }
        
        .header h1 {
            font-size: 3rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6, #06b6d4);
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-size: 200% 200%;
            animation: gradientShift 3s ease-in-out infinite;
        }
        
        .header p {
            font-size: 1.1rem;
            opacity: 0.8;
            color: #cbd5e1;
        }
        
        .filter-tabs {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-bottom: 2rem;
            justify-content: center;
            animation: fadeInUp 0.8s ease-out 0.2s both;
        }
        
        .filter-tab {
            padding: 0.75rem 1.5rem;
            border: 2px solid rgba(148, 163, 184, 0.2);
            border-radius: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 0.9rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            position: relative;
            overflow: hidden;
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(15px);
            color: #cbd5e1;
        }
        
        .filter-tab.active {
            color: white;
            border-color: rgba(59, 130, 246, 0.5);
            background: rgba(59, 130, 246, 0.1);
        }
        
        .filter-tab:hover {
            transform: translateY(-2px);
            border-color: rgba(59, 130, 246, 0.3);
            background: rgba(51, 65, 85, 0.6);
        }
        
        .filter-tab .count {
            background: rgba(255, 255, 255, 0.2);
            padding: 0.25rem 0.5rem;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 700;
        }
        
        .filter-tab.active .count {
            background: rgba(255, 255, 255, 0.3);
        }
        
        .controls {
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
            flex-wrap: wrap;
            justify-content: center;
            align-items: center;
            animation: fadeInUp 0.8s ease-out 0.3s both;
        }
        
        .btn {
            padding: 0.875rem 1.75rem;
            border: none;
            border-radius: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            font-size: 0.95rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            position: relative;
            overflow: hidden;
        }
        
        .btn::before {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 100%;
            height: 100%;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
            transition: left 0.5s;
        }
        
        .btn:hover::before {
            left: 100%;
        }
        
        .btn-primary {
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            color: white;
            box-shadow: 0 8px 25px rgba(59, 130, 246, 0.3);
        }
        
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 35px rgba(59, 130, 246, 0.4);
        }
        
        .btn-danger {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
            box-shadow: 0 8px 25px rgba(239, 68, 68, 0.3);
        }
        
        .btn-danger:hover {
            transform: translateY(-2px);
            box-shadow: 0 12px 35px rgba(239, 68, 68, 0.4);
        }
        
        .btn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none !important;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
            animation: fadeInUp 0.8s ease-out 0.4s both;
        }
        
        .stat-card {
            background: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(20px);
            padding: 2rem;
            border-radius: 24px;
            text-align: center;
            border: 1px solid rgba(148, 163, 184, 0.1);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }
        
        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(139, 92, 246, 0.1));
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .stat-card:hover::before {
            opacity: 1;
        }
        
        .stat-card:hover {
            transform: translateY(-8px) scale(1.02);
            border-color: rgba(59, 130, 246, 0.3);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }
        
        .stat-card h3 {
            font-size: 3rem;
            font-weight: 700;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
            position: relative;
            z-index: 1;
        }
        
        .stat-card p {
            color: #94a3b8;
            font-weight: 500;
            font-size: 1rem;
            position: relative;
            z-index: 1;
        }
        
        .jobs-container {
            background: rgba(15, 23, 42, 0.8);
            backdrop-filter: blur(20px);
            border-radius: 32px;
            padding: 2.5rem;
            border: 1px solid rgba(148, 163, 184, 0.1);
            animation: fadeInUp 0.8s ease-out 0.6s both;
        }
        
        .jobs-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            flex-wrap: wrap;
            gap: 1rem;
        }
        
        .jobs-header h2 {
            font-size: 1.75rem;
            color: #ffffff;
            font-weight: 700;
        }
        
        .search-box {
            position: relative;
            max-width: 320px;
            width: 100%;
        }
        
        .search-box input {
            width: 100%;
            padding: 1rem 1.25rem 1rem 3rem;
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 16px;
            font-size: 0.95rem;
            transition: all 0.3s ease;
            background: rgba(30, 41, 59, 0.5);
            backdrop-filter: blur(10px);
            color: #ffffff;
        }
        
        .search-box input:focus {
            outline: none;
            border-color: #3b82f6;
            background: rgba(30, 41, 59, 0.8);
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        
        .search-box input::placeholder {
            color: #94a3b8;
        }
        
        .search-icon {
            position: absolute;
            left: 1.25rem;
            top: 50%;
            transform: translateY(-50%);
            color: #64748b;
            font-size: 1.1rem;
        }
        
        .jobs-grid {
            display: grid;
            gap: 1.5rem;
        }
        
        .job-card {
            background: rgba(30, 41, 59, 0.6);
            backdrop-filter: blur(15px);
            border-radius: 20px;
            padding: 2rem;
            border: 1px solid rgba(148, 163, 184, 0.1);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
            animation: slideInUp 0.6s ease-out;
        }
        
        .job-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
        }
        
        .job-card.status-failed::before {
            background: linear-gradient(90deg, #ef4444, #f59e0b, #ef4444);
            background-size: 200% 100%;
            animation: gradientSlide 2s linear infinite;
        }
        
        .job-card.status-completed::before {
            background: linear-gradient(90deg, #10b981, #059669);
        }
        
        .job-card.status-running::before {
            background: linear-gradient(90deg, #3b82f6, #1d4ed8);
            background-size: 200% 100%;
            animation: gradientSlide 2s linear infinite;
        }
        
        .job-card:hover {
            transform: translateY(-4px);
            border-color: rgba(59, 130, 246, 0.3);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.2);
        }
        
        .job-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
            gap: 1rem;
        }
        
        .job-info h3 {
            font-size: 1.25rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.25rem;
        }
        
        .job-info p {
            color: #94a3b8;
            font-size: 0.9rem;
        }
        
        .job-status {
            padding: 0.5rem 1rem;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .job-status.status-failed {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.3);
        }
        
        .job-status.status-completed {
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
        }
        
        .job-status.status-running {
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            color: white;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            animation: pulse 2s infinite;
        }
        
        .job-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        
        .detail-item {
            background: rgba(51, 65, 85, 0.4);
            backdrop-filter: blur(10px);
            padding: 1rem;
            border-radius: 16px;
            border: 1px solid rgba(148, 163, 184, 0.1);
            transition: all 0.3s ease;
        }
        
        .detail-item:hover {
            background: rgba(51, 65, 85, 0.6);
            transform: translateY(-2px);
        }
        
        .detail-label {
            font-size: 0.8rem;
            font-weight: 600;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }
        
        .detail-value {
            font-weight: 600;
            color: #ffffff;
            font-size: 0.95rem;
        }
        
        .job-actions {
            display: flex;
            gap: 0.75rem;
            flex-wrap: wrap;
        }
        
        .btn-sm {
            padding: 0.75rem 1.25rem;
            font-size: 0.85rem;
            border-radius: 12px;
        }
        
        .loading {
            text-align: center;
            padding: 3rem;
            color: #94a3b8;
        }
        
        .spinner {
            display: inline-block;
            width: 40px;
            height: 40px;
            border: 4px solid rgba(148, 163, 184, 0.2);
            border-top: 4px solid #3b82f6;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 1rem;
        }
        
        .empty-state {
            text-align: center;
            padding: 3rem;
            color: #94a3b8;
        }
        
        .empty-state h3 {
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
            color: #ffffff;
        }
        
        .toast {
            position: fixed;
            top: 2rem;
            right: 2rem;
            padding: 1.25rem 1.75rem;
            border-radius: 16px;
            color: white;
            font-weight: 600;
            z-index: 1000;
            transform: translateX(120%);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            backdrop-filter: blur(20px);
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
        }
        
        .toast.show {
            transform: translateX(0);
        }
        
        .toast.success {
            background: linear-gradient(135deg, #10b981, #059669);
            border-left: 4px solid #047857;
        }
        
        .toast.error {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            border-left: 4px solid #b91c1c;
        }

        .toast.info {
            background: linear-gradient(135deg, #3b82f6, #1d4ed8);
            border-left: 4px solid #1e40af;
        }

        @keyframes pulse {
            0%, 100% {
                box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            }
            50% {
                box-shadow: 0 4px 12px rgba(59, 130, 246, 0.6);
            }
        }

        @keyframes gradientShift {
            0%, 100% {
                background-position: 0% 50%;
            }
            50% {
                background-position: 100% 50%;
            }
        }

        @keyframes gradientSlide {
            0% {
                background-position: -200% 0;
            }
            100% {
                background-position: 200% 0;
            }
        }

        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(30px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes slideInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        @media (max-width: 768px) {
            .container {
                padding: 1rem;
            }
            
            .header h1 {
                font-size: 2.5rem;
            }
            
            .filter-tabs {
                justify-content: center;
            }
            
            .controls {
                justify-content: center;
            }
            
            .stats {
                grid-template-columns: 1fr;
            }
            
            .jobs-header {
                flex-direction: column;
                text-align: center;
            }
            
            .search-box {
                max-width: 100%;
            }

            .job-details {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container" x-data="scanJobManager()">
        <div class="header">
            <h1>🔍 Iris </h1>
        </div>
        
        <!-- Filter Tabs -->
        <div class="filter-tabs">
            <button 
                class="filter-tab" 
                :class="{ active: activeFilter === 'failed' }"
                @click="setActiveFilter('failed')"
            >
                <span>❌</span>
                <span>Failed</span>
                <span class="count" x-text="jobCounts.failed"></span>
            </button>
            <button 
                class="filter-tab" 
                :class="{ active: activeFilter === 'completed' }"
                @click="setActiveFilter('completed')"
            >
                <span>✅</span>
                <span>Completed</span>
                <span class="count" x-text="jobCounts.completed"></span>
            </button>
            <button 
                class="filter-tab" 
                :class="{ active: activeFilter === 'running' }"
                @click="setActiveFilter('running')"
            >
                <span>⏳</span>
                <span>Running</span>
                <span class="count" x-text="jobCounts.running"></span>
            </button>
            <button 
                class="filter-tab" 
                :class="{ active: activeFilter === 'all' }"
                @click="setActiveFilter('all')"
            >
                <span>📋</span>
                <span>All Jobs</span>
                <span class="count" x-text="jobCounts.all"></span>
            </button>
        </div>
        
        <div class="controls">
            <button @click="loadJobs()" class="btn btn-primary" :disabled="loading">
                <span x-show="!loading">🔄</span>
                <div x-show="loading" class="spinner" style="width: 16px; height: 16px; border-width: 2px;"></div>
                <span x-text="loading ? 'Refreshing...' : 'Refresh Jobs'"></span>
            </button>
            <button 
                x-show="activeFilter === 'failed'" 
                @click="restartAllFailed()" 
                class="btn btn-danger" 
                :disabled="loading || filteredJobs.length === 0"
            >
                <span>🚀</span> 
                <span x-text="`Restart All Failed (${jobCounts.failed})`"></span>
            </button>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <h3 x-text="jobCounts.all"></h3>
                <p>Total Jobs</p>
            </div>
            <div class="stat-card">
                <h3 x-text="uniqueDatabases"></h3>
                <p>Affected Databases</p>
            </div>
            <div class="stat-card">
                <h3 x-text="recentRestarts"></h3>
                <p>Recent Restarts</p>
            </div>
            <div class="stat-card">
                <h3 x-text="lastUpdated"></h3>
                <p>Last Updated</p>
            </div>
        </div>
        
        <div class="jobs-container">
            <div class="jobs-header">
                <h2 x-text="getFilterTitle()"></h2>
                <div class="search-box">
                    <div class="search-icon">🔍</div>
                    <input type="text" x-model="searchQuery" placeholder="Search jobs...">
                </div>
            </div>
            
            <div x-show="loading && allJobs.length === 0" class="loading">
                <div class="spinner"></div>
                <p>Loading scan jobs...</p>
            </div>
            
            <div x-show="!loading && filteredJobs.length === 0 && allJobs.length === 0" class="empty-state">
                <div x-text="getEmptyStateEmoji()" style="font-size: 4rem; margin-bottom: 1rem;"></div>
                <h3 x-text="getEmptyStateTitle()"></h3>
                <p x-text="getEmptyStateMessage()"></p>
            </div>
            
            <div x-show="!loading && filteredJobs.length === 0 && allJobs.length > 0" class="empty-state">
                <div style="font-size: 4rem; margin-bottom: 1rem;">🔍</div>
                <h3>No Results Found</h3>
                <p>Try adjusting your search terms or clear the search to see all jobs.</p>
            </div>
            
            <div x-show="!loading && filteredJobs.length > 0" class="jobs-grid">
                <template x-for="job in filteredJobs" :key="job.id">
                    <div class="job-card" :class="`status-${getJobStatusClass(job.status)}`">
                        <div class="job-header">
                            <div class="job-info">
                                <h3 x-text="job.database"></h3>
                                <p x-text="'Collection: ' + job.collection"></p>
                            </div>
                            <div class="job-status" :class="`status-${getJobStatusClass(job.status)}`">
                                <span x-text="getStatusIcon(job.status)"></span>
                                <span x-text="job.status"></span>
                            </div>
                        </div>
                        
                        <div class="job-details">
                            <div class="detail-item">
                                <div class="detail-label">Domain</div>
                                <div class="detail-value" x-text="job.domain"></div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Tenant ID</div>
                                <div class="detail-value" x-text="job.tenant_id"></div>
                            </div>
                            <div class="detail-item">
                                <div class="detail-label">Latest</div>
                                <div class="detail-value" x-text="job.is_latest ? 'Yes' : 'No'"></div>
                            </div>
                            <div class="detail-item" x-show="job.created_at">
                                <div class="detail-label">📅 Created</div>
                                <div class="detail-value" x-text="formatDate(job.created_at)"></div>
                            </div>
                            <div class="detail-item" x-show="job.completed_at">
                                <div class="detail-label">✅ Completed</div>
                                <div class="detail-value" x-text="formatDate(job.completed_at)"></div>
                            </div>
                            <div class="detail-item" x-show="job.duration">
                                <div class="detail-label">⏱️ Duration</div>
                                <div class="detail-value" x-text="formatDuration(job.duration)"></div>
                            </div>
                            <div class="detail-item" x-show="job.documents_processed">
                                <div class="detail-label">📄 Documents</div>
                                <div class="detail-value" x-text="formatNumber(job.documents_processed)"></div>
                            </div>
                            <div class="detail-item" x-show="job.error_message" style="grid-column: 1 / -1;">
                                <div class="detail-label">❌ Error</div>
                                <div class="detail-value" x-text="job.error_message" style="word-break: break-word;"></div>
                            </div>
                        </div>
                        
                        <div class="job-actions" x-show="job.status === 'failed'">
                            <button @click="restartJob(job)" class="btn btn-primary btn-sm" :disabled="loading">
                                <span x-show="!loading">🚀</span>
                                <div x-show="loading" class="spinner" style="width: 12px; height: 12px; border-width: 2px;"></div>
                                <span x-text="loading ? 'Restarting...' : 'Restart Scan'"></span>
                            </button>
                        </div>
                    </div>
                </template>
            </div>
        </div>
        
        <div class="toast" :class="[toastType, { show: showToast }]">
            <span x-text="toastMessage"></span>
        </div>
    </div>

    <script>
        function scanJobManager() {
            return {
                allJobs: [],
                searchQuery: '',
                loading: false,
                showToast: false,
                toastMessage: '',
                toastType: 'success',
                recentRestarts: 0,
                activeFilter: 'failed',
                
                init() {
                    this.loadJobs();
                    // Auto-refresh every 30 seconds
                    setInterval(() => {
                        if (!this.loading) {
                            this.loadJobs();
                        }
                    }, 30000);
                },
                
                get filteredJobs() {
                    let jobs = this.getJobsByFilter(this.activeFilter);
                    
                    if (!this.searchQuery) return jobs;
                    
                    const query = this.searchQuery.toLowerCase();
                    return jobs.filter(job => 
                        job.database.toLowerCase().includes(query) ||
                        job.collection.toLowerCase().includes(query) ||
                        job.id.toLowerCase().includes(query) ||
                        job.domain.toLowerCase().includes(query) ||
                        (job.error_message && job.error_message.toLowerCase().includes(query))
                    );
                },
                
                get jobCounts() {
                    return {
                        all: this.allJobs.length,
                        failed: this.getJobsByFilter('failed').length,
                        completed: this.getJobsByFilter('completed').length,
                        running: this.getJobsByFilter('running').length
                    };
                },
                
                get uniqueDatabases() {
                    return new Set(this.allJobs.map(job => job.database)).size;
                },
                
                get lastUpdated() {
                    return new Date().toLocaleTimeString('en-US', {
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                },
                
                getJobsByFilter(filter) {
                    switch (filter) {
                        case 'failed':
                            return this.allJobs.filter(job => job.status === 'failed');
                        case 'completed':
                            return this.allJobs.filter(job => job.status === 'completed' || job.status === 'success');
                        case 'running':
                            return this.allJobs.filter(job => job.status === 'running' || job.status === 'in_progress');
                        case 'all':
                        default:
                            return this.allJobs;
                    }
                },
                
                setActiveFilter(filter) {
                    this.activeFilter = filter;
                    this.searchQuery = ''; // Clear search when changing filters
                },
                
                getFilterTitle() {
                    switch (this.activeFilter) {
                        case 'failed':
                            return 'Failed Scan Jobs';
                        case 'completed':
                            return 'Completed Scan Jobs';
                        case 'running':
                            return 'Running Scan Jobs';
                        case 'all':
                        default:
                            return 'All Scan Jobs';
                    }
                },
                
                getEmptyStateEmoji() {
                    switch (this.activeFilter) {
                        case 'failed':
                            return '🎉';
                        case 'completed':
                            return '📋';
                        case 'running':
                            return '⏸️';
                        case 'all':
                        default:
                            return '📊';
                    }
                },
                
                getEmptyStateTitle() {
                    switch (this.activeFilter) {
                        case 'failed':
                            return 'No Failed Jobs Found!';
                        case 'completed':
                            return 'No Completed Jobs Yet';
                        case 'running':
                            return 'No Running Jobs';
                        case 'all':
                        default:
                            return 'No Jobs Found';
                    }
                },
                
                getEmptyStateMessage() {
                    switch (this.activeFilter) {
                        case 'failed':
                            return 'All your scan jobs are running smoothly.';
                        case 'completed':
                            return 'Completed scan jobs will appear here once they finish.';
                        case 'running':
                            return 'No scan jobs are currently in progress.';
                        case 'all':
                        default:
                            return 'No scan jobs have been created yet.';
                    }
                },
                
                getJobStatusClass(status) {
                    switch (status.toLowerCase()) {
                        case 'completed':
                        case 'success':
                            return 'completed';
                        case 'running':
                        case 'in_progress':
                            return 'running';
                        case 'failed':
                        default:
                            return 'failed';
                    }
                },
                
                getStatusIcon(status) {
                    switch (status.toLowerCase()) {
                        case 'completed':
                        case 'success':
                            return '✅';
                        case 'running':
                        case 'in_progress':
                            return '⏳';
                        case 'failed':
                        default:
                            return '❌';
                    }
                },
                
                async loadJobs() {
                    this.loading = true;
                    try {
                        const response = await axios.get('/api/all-jobs');
                        this.allJobs = response.data;
                        this.showToastMessage('Jobs loaded successfully', 'success');
                    } catch (error) {
                        console.error('Error loading jobs:', error);
                        this.showToastMessage('Failed to load jobs', 'error');
                    } finally {
                        this.loading = false;
                    }
                },
                
                async restartJob(job) {
                    this.loading = true;
                    try {
                        const response = await axios.post(`/api/restart-job/${job.id}`);
                        if (response.data.success) {
                            this.recentRestarts++;
                            this.showToastMessage(`Restarted scan for ${job.database}`, 'success');
                            // Remove the job from the list since it's been restarted
                            this.allJobs = this.allJobs.filter(j => j.id !== job.id);
                        } else {
                            this.showToastMessage(response.data.message, 'error');
                        }
                    } catch (error) {
                        console.error('Error restarting job:', error);
                        this.showToastMessage('Failed to restart job', 'error');
                    } finally {
                        this.loading = false;
                    }
                },
                
                async restartAllFailed() {
                    const failedJobs = this.getJobsByFilter('failed');
                    if (failedJobs.length === 0) return;
                    
                    this.loading = true;
                    try {
                        const response = await axios.post('/api/restart-all-failed');
                        if (response.data.success) {
                            this.recentRestarts += response.data.restarted_jobs;
                            this.showToastMessage(`Successfully restarted ${response.data.restarted_jobs} jobs`, 'success');
                            this.loadJobs(); // Reload to get updated list
                        } else {
                            this.showToastMessage(response.data.message, 'error');
                        }
                    } catch (error) {
                        console.error('Error restarting all jobs:', error);
                        this.showToastMessage('Failed to restart jobs', 'error');
                    } finally {
                        this.loading = false;
                    }
                },
                
                formatDate(dateString) {
                    if (!dateString) return 'N/A';
                    return new Date(dateString).toLocaleDateString('en-US', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit'
                    });
                },
                
                formatDuration(duration) {
                    if (!duration) return 'N/A';
                    const minutes = Math.floor(duration / 60);
                    const seconds = duration % 60;
                    return `${minutes}m ${seconds}s`;
                },
                
                formatNumber(num) {
                    if (!num) return 'N/A';
                    return num.toLocaleString();
                },
                
                showToastMessage(message, type = 'success') {
                    this.toastMessage = message;
                    this.toastType = type;
                    this.showToast = true;
                    setTimeout(() => {
                        this.showToast = false;
                    }, 4000);
                }
            }
        }
    </script>
</body>
</html>
    """)

# API Endpoints
@app.get("/api/failed-jobs")
async def get_failed_jobs():
    """Get all failed scan jobs"""
    jobs = await get_scan_jobs_by_status("failed")
    return jobs

@app.get("/api/completed-jobs")
async def get_completed_jobs():
    """Get all completed scan jobs"""
    jobs = await get_scan_jobs_by_status("completed")
    return jobs

@app.get("/api/running-jobs")
async def get_running_jobs():
    """Get all running scan jobs"""
    jobs = await get_scan_jobs_by_status("running")
    return jobs

@app.get("/api/all-jobs")
async def get_all_jobs(search: Optional[str] = None):
    """Get all scan jobs regardless of status, with optional search"""
    jobs = await get_scan_jobs_by_status(search=search)
    return jobs

@app.post("/api/restart-job/{job_id}")
async def restart_job(job_id: str):
    """Restart a specific scan job"""
    success = await restart_scan(job_id)
    return RestartResponse(
        success=success,
        message="Job restart initiated successfully" if success else "Failed to restart job",
        restarted_jobs=1 if success else 0
    )

@app.post("/api/restart-all-failed")
async def restart_all_failed_jobs():
    """Restart all failed scan jobs"""
    jobs = await get_scan_jobs_by_status("failed")
    
    if not jobs:
        return RestartResponse(
            success=True,
            message="No failed jobs to restart",
            restarted_jobs=0
        )
    
    # Restart all jobs concurrently
    tasks = [restart_scan(job.id) for job in jobs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful_restarts = sum(1 for result in results if result is True)
    
    return RestartResponse(
        success=successful_restarts > 0,
        message=f"Successfully restarted {successful_restarts} out of {len(jobs)} jobs",
        restarted_jobs=successful_restarts
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)