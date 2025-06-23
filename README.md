# Scan Status Dashboard

A web application to monitor and manage MongoDB scan jobs across multiple databases.

## Features

- View scan jobs by status (failed, completed, running, all)
- Restart failed scan jobs individually or in batch
- Search functionality for finding specific jobs
- Pagination for large job lists
- Filter jobs by tenant ID
- Real-time statistics and monitoring
- Responsive design for mobile and desktop

## API Endpoints

- `/api/failed-jobs` - Get all failed scan jobs
- `/api/completed-jobs` - Get all completed scan jobs
- `/api/running-jobs` - Get all running scan jobs
- `/api/all-jobs` - Get all scan jobs
- `/api/tenants` - Get all unique tenant IDs
- `/api/restart-job/{job_id}` - Restart a specific job
- `/api/restart-all-failed` - Restart all failed jobs
- `/health` - Health check endpoint

All job listing endpoints support the following query parameters:
- `page` - Page number (default: 1)
- `page_size` - Number of items per page (default: 10)
- `tenant` - Filter by tenant ID
- `search` - Search term to filter results

## Setup

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Set environment variables:
   - `MONGO_URI` - MongoDB connection string

4. Run the application:
   ```
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

## Technologies Used

- Backend: FastAPI, PyMongo
- Frontend: Alpine.js, Axios
- Database: MongoDB
- Styling: Custom CSS with responsive design

## Development

To run the application in development mode with auto-reload:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## License

MIT