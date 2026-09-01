"""
راوتر الدفع (Stripe)
======================
يطابق العقد الظاهر في test_stripe_payments.py:
- GET  /payments/packages           -> dict من 6 باقات (tier, amount, interval)
- POST /payments/checkout           -> {checkout_url, session_id} أو 400 لباقة غير صحيحة
- GET  /payments/status/{session_id}-> {session_id, status, payment_status, tier, interval} أو 404
- POST /payments/portal             -> {portal_url} (يتطلب تسجيل دخول)
- POST /payments/webhook            -> استقبال أحداث Stripe لتحديث الاشتراك فعليًا

⚠️ استخدمت مكتبة `stripe` الرسمية بدل حزمة `emergentintegrations` الخاصة
بمنصة Emergent (التي لم أستطع التأكد من توفرها/سلوكها الدقيق بدون اتصال شبكة).
النتيجة النهائية للمستخدم (checkout_url من stripe.com) متطابقة وظيفيًا.
"""

import os
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, HTTPException, Request

from db import payment_transactions_col, users_col
from deps import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = os.environ.get("STRIPE_API_KEY", "")
WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

PACKAGES = {
    "starter_monthly": {"tier": "starter", "amount": 4.99, "interval": "month"},
    "starter_yearly": {"tier": "starter", "amount": 35.90, "interval": "year"},
    "creator_monthly": {"tier": "creator", "amount": 12.99, "interval": "month"},
    "creator_yearly": {"tier": "creator", "amount": 93.50, "interval": "year"},
    "pro_monthly": {"tier": "pro", "amount": 29.00, "interval": "month"},
    "pro_yearly": {"tier": "pro", "amount": 208.80, "interval": "year"},
}


@router.get("/packages")
async def get_packages():
    return PACKAGES


@router.post("/checkout")
async def create_checkout(request: Request):
    body = await request.json()
    package_id = body.get("package_id")
    origin_url = body.get("origin_url", "")

    package = PACKAGES.get(package_id)
    if not package:
        raise HTTPException(status_code=400, detail=f"باقة غير معروفة: {package_id}")

    user = await get_current_user(request)

    try:
        checkout_session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "unit_amount": int(round(package["amount"] * 100)),
                        "recurring": {
                            "interval": "year" if package["interval"] == "year" else "month"
                        },
                        "product_data": {
                            "name": f"Cinemora {package['tier'].capitalize()} "
                            f"({package['interval']}ly)"
                        },
                    },
                    "quantity": 1,
                }
            ],
            success_url=f"{origin_url}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin_url}/pricing",
            customer_email=user["email"] if user else None,
            metadata={
                "package_id": package_id,
                "tier": package["tier"],
                "interval": package["interval"],
                "user_id": str(user["_id"]) if user else "",
            },
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await payment_transactions_col.insert_one(
        {
            "session_id": checkout_session.id,
            "package_id": package_id,
            "tier": package["tier"],
            "interval": package["interval"],
            "amount": package["amount"],
            "status": "initiated",
            "payment_status": "pending",
            "user_id": user["_id"] if user else None,
            "created_at": datetime.now(timezone.utc),
        }
    )

    return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}


@router.get("/status/{session_id}")
async def payment_status(session_id: str):
    record = await payment_transactions_col.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(status_code=404, detail="جلسة دفع غير موجودة")

    # مزامنة مع Stripe إن أمكن (لا يفشل الطلب إن تعذّر الاتصال)
    try:
        stripe_session = stripe.checkout.Session.retrieve(session_id)
        new_status = stripe_session.status  # open | complete | expired
        new_payment_status = stripe_session.payment_status  # paid | unpaid | no_payment_required
        if new_status != record["status"] or new_payment_status != record["payment_status"]:
            await payment_transactions_col.update_one(
                {"session_id": session_id},
                {"$set": {"status": new_status, "payment_status": new_payment_status}},
            )
            record["status"], record["payment_status"] = new_status, new_payment_status
            if new_payment_status == "paid" and record.get("user_id"):
                await users_col.update_one(
                    {"_id": record["user_id"]}, {"$set": {"tier": record["tier"]}}
                )
    except Exception:
        pass  # لا يوجد اتصال بـ Stripe (مثلاً بدون مفتاح صالح) — نعتمد على السجل المحلي

    return {
        "session_id": record["session_id"],
        "status": record["status"],
        "payment_status": record["payment_status"],
        "tier": record["tier"],
        "interval": record["interval"],
    }


@router.post("/portal")
async def create_portal_session(request: Request):
    body = await request.json()
    return_url = body.get("return_url", "")
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="غير مسجل الدخول")

    stripe_customer_id = user.get("stripe_customer_id")
    if not stripe_customer_id:
        raise HTTPException(status_code=400, detail="لا يوجد اشتراك دفع مرتبط بهذا الحساب")

    try:
        portal = stripe.billing_portal.Session.create(
            customer=stripe_customer_id, return_url=return_url
        )
    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"portal_url": portal.url}


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        if WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        else:
            import json

            event = json.loads(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"webhook غير صالح: {e}")

    event_type = event.get("type") if isinstance(event, dict) else event["type"]
    data_object = (event.get("data") if isinstance(event, dict) else event["data"])["object"]

    if event_type == "checkout.session.completed":
        session_id = data_object.get("id")
        customer_id = data_object.get("customer")
        record = await payment_transactions_col.find_one({"session_id": session_id})
        if record:
            await payment_transactions_col.update_one(
                {"session_id": session_id},
                {"$set": {"status": "complete", "payment_status": "paid"}},
            )
            if record.get("user_id"):
                update = {"tier": record["tier"]}
                if customer_id:
                    update["stripe_customer_id"] = customer_id
                await users_col.update_one({"_id": record["user_id"]}, {"$set": update})

    return {"received": True}
