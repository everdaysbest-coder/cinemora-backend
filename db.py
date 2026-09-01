"""
طبقة قاعدة بيانات تحاكي واجهة MongoDB (motor) لكنها تعمل فعليًا فوق
PostgreSQL باستخدام عمود JSONB — هذا يخلي كل كود الراوترات (auth.py,
payments.py, ...) يشتغل بدون أي تعديل تقريبًا رغم تغيير قاعدة البيانات
من Mongo إلى Postgres (بسبب مشاكل تسجيل حساب MongoDB Atlas من الموبايل).

كل "collection" هو جدول فيه عمود JSONB واحد اسمه doc، والفلترة تتم عبر
عامل الاحتواء @> (يدعم فقط تطابق قيم مباشر، وهو كل اللي تستخدمه الراوترات
هنا — لا يوجد أي استعلام Mongo متقدم مثل $gt في الكود الحالي).
"""

import json
import os
from datetime import datetime
from types import SimpleNamespace

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "")

_pool = None
_tables_ready = set()


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


def _dumps(obj) -> str:
    return json.dumps(obj, default=_json_default)


async def _get_pool():
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL غير مضبوط في متغيرات البيئة")
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    return _pool


class Cursor:
    def __init__(self, collection: "Collection", query: dict):
        self._col = collection
        self._query = query
        self._sort_field = None
        self._sort_dir = 1
        self._limit = None

    def sort(self, field, direction=1):
        self._sort_field = field
        self._sort_dir = direction
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def _rows(self):
        pool = await _get_pool()
        await self._col._ensure_table(pool)
        sql = f"SELECT doc FROM {self._col.table} WHERE doc @> $1::jsonb"
        params = [_dumps(self._query)]
        if self._sort_field:
            order = "DESC" if self._sort_dir == -1 else "ASC"
            if self._sort_field in ("likes", "referred_count"):
                sql += f" ORDER BY COALESCE((doc->>'{self._sort_field}')::numeric, 0) {order}"
            else:
                sql += f" ORDER BY (doc->>'{self._sort_field}') {order}"
        if self._limit:
            sql += f" LIMIT {int(self._limit)}"
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [json.loads(r["doc"]) for r in rows]

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for row in await self._rows():
            yield row


class Collection:
    def __init__(self, table: str):
        self.table = table

    async def _ensure_table(self, pool):
        if self.table in _tables_ready:
            return
        async with pool.acquire() as conn:
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self.table} "
                f"(row_id SERIAL PRIMARY KEY, doc JSONB NOT NULL)"
            )
            await conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.table}_doc ON {self.table} USING GIN (doc)"
            )
        _tables_ready.add(self.table)

    async def find_one(self, query: dict):
        pool = await _get_pool()
        await self._ensure_table(pool)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT doc FROM {self.table} WHERE doc @> $1::jsonb LIMIT 1", _dumps(query)
            )
        return json.loads(row["doc"]) if row else None

    async def insert_one(self, doc: dict):
        pool = await _get_pool()
        await self._ensure_table(pool)
        async with pool.acquire() as conn:
            await conn.execute(f"INSERT INTO {self.table}(doc) VALUES ($1::jsonb)", _dumps(doc))
        return SimpleNamespace(inserted_id=doc.get("_id"))

    async def update_one(self, query: dict, update: dict, upsert: bool = False):
        existing = await self.find_one(query)
        pool = await _get_pool()
        if existing is None:
            if not upsert:
                return SimpleNamespace(matched_count=0)
            new_doc = dict(query)
            new_doc.update(update.get("$setOnInsert", {}))
            new_doc.update(update.get("$set", {}))
            for k, v in update.get("$inc", {}).items():
                new_doc[k] = new_doc.get(k, 0) + v
            await self.insert_one(new_doc)
            return SimpleNamespace(matched_count=0, upserted_id=True)

        new_doc = dict(existing)
        new_doc.update(update.get("$set", {}))
        for k, v in update.get("$inc", {}).items():
            new_doc[k] = new_doc.get(k, 0) + v

        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {self.table} SET doc = $1::jsonb WHERE doc @> $2::jsonb",
                _dumps(new_doc),
                _dumps(query),
            )
        return SimpleNamespace(matched_count=1)

    async def delete_one(self, query: dict):
        pool = await _get_pool()
        await self._ensure_table(pool)
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {self.table} WHERE doc @> $1::jsonb", _dumps(query))

    async def count_documents(self, query: dict):
        pool = await _get_pool()
        await self._ensure_table(pool)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT COUNT(*) AS c FROM {self.table} WHERE doc @> $1::jsonb", _dumps(query)
            )
        return row["c"]

    def find(self, query: dict = None):
        return Cursor(self, query or {})


# نفس أسماء الـ collections المستخدمة بكل الراوترات — بدون أي تعديل هناك
users_col = Collection("users")
sessions_col = Collection("sessions")
usage_col = Collection("usage")
payment_transactions_col = Collection("payment_transactions")
video_jobs_col = Collection("video_jobs")
projects_col = Collection("projects")
referrals_col = Collection("referrals")
newsletter_col = Collection("newsletter_signups")
