"""اتصال MongoDB مشترك عبر كل الراوترات."""
import os

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "cinemora")

_client = AsyncIOMotorClient(MONGO_URL)
db = _client[DB_NAME]

# مجموعات (collections)
users_col = db["users"]
sessions_col = db["sessions"]
usage_col = db["usage"]
payment_transactions_col = db["payment_transactions"]
video_jobs_col = db["video_jobs"]
projects_col = db["projects"]
referrals_col = db["referrals"]
newsletter_col = db["newsletter_signups"]
