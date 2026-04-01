"""PayPal payment integration for PDFtoDeck."""

import httpx
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .config import (
    PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_BASE_URL, CREDIT_PACKAGES,
)
from . import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/paypal", tags=["paypal"])


# ─── Helpers ───

async def _get_access_token() -> str:
    """Get PayPal OAuth2 access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_BASE_URL}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            logger.error("PayPal auth failed: %s %s", resp.status_code, resp.text)
            raise HTTPException(500, "PayPal authentication failed")
        return resp.json()["access_token"]


async def _paypal_request(method: str, path: str, json_body: dict = None) -> dict:
    """Make authenticated PayPal API request."""
    token = await _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method,
            f"{PAYPAL_BASE_URL}{path}",
            headers=headers,
            json=json_body,
        )
        if resp.status_code not in (200, 201):
            logger.error("PayPal %s %s → %s: %s", method, path, resp.status_code, resp.text)
            raise HTTPException(500, f"PayPal request failed: {resp.status_code}")
        return resp.json()


# ─── Models ───

class CreateOrderRequest(BaseModel):
    package: str  # starter / standard / pro
    email: str    # user email


class CaptureOrderRequest(BaseModel):
    order_id: str  # PayPal order ID
    email: str


# ─── Routes ───

@router.post("/create-order")
async def create_order(req: CreateOrderRequest):
    """Create a PayPal order for a credit package."""
    pkg = CREDIT_PACKAGES.get(req.package)
    if not pkg:
        raise HTTPException(400, f"Unknown package: {req.package}")

    # Verify user exists
    user = await db.get_user(req.email)
    if not user:
        raise HTTPException(404, "User not found. Please sign in first.")

    # Create internal order record
    order_id = await db.create_credit_order(
        user_id=user["id"],
        package=req.package,
        credits=pkg["credits"],
        amount_cents=pkg["price_cents"],
    )

    # Price in dollars
    price_usd = f"{pkg['price_cents'] / 100:.2f}"

    # Create PayPal order
    paypal_order = await _paypal_request("POST", "/v2/checkout/orders", {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": order_id,
            "description": f"PDFtoDeck {pkg['label']} - {pkg['credits']} credits",
            "amount": {
                "currency_code": "USD",
                "value": price_usd,
            },
        }],
        "payment_source": {
            "paypal": {
                "experience_context": {
                    "payment_method_preference": "IMMEDIATE_PAYMENT_REQUIRED",
                    "brand_name": "PDFtoDeck",
                    "landing_page": "NO_PREFERENCE",
                    "user_action": "PAY_NOW",
                    "return_url": "https://pdf2deck.xyz/dashboard?payment=success",
                    "cancel_url": "https://pdf2deck.xyz/dashboard?payment=cancelled",
                }
            }
        }
    })

    paypal_order_id = paypal_order["id"]

    # Update internal order with PayPal order ID
    await db.update_credit_order(order_id, payment_id=paypal_order_id)

    # Find the approval link
    approve_url = None
    for link in paypal_order.get("links", []):
        if link["rel"] == "payer-action":
            approve_url = link["href"]
            break

    return {
        "order_id": paypal_order_id,
        "internal_order_id": order_id,
        "approve_url": approve_url,
    }


@router.post("/capture-order")
async def capture_order(req: CaptureOrderRequest):
    """Capture (finalize) a PayPal order after user approval."""
    # Capture payment
    result = await _paypal_request("POST", f"/v2/checkout/orders/{req.order_id}/capture")

    status = result.get("status")
    if status != "COMPLETED":
        logger.warning("PayPal capture status: %s for order %s", status, req.order_id)
        raise HTTPException(400, f"Payment not completed. Status: {status}")

    # Extract reference_id (our internal order_id)
    purchase_units = result.get("purchase_units", [])
    internal_order_id = None
    if purchase_units:
        internal_order_id = purchase_units[0].get("reference_id")

    # Find the order and add credits
    if internal_order_id:
        order = await db.get_credit_order(internal_order_id)
        if order and order["status"] != "completed":
            # Add credits to user
            await db.add_credits(req.email, order["credits"])
            # Mark order completed
            await db.update_credit_order(
                internal_order_id,
                status="completed",
                payment_method="paypal",
                payment_id=req.order_id,
            )
            logger.info(
                "Payment completed: user=%s pkg=%s credits=%d paypal_order=%s",
                req.email, order["package"], order["credits"], req.order_id,
            )
            return {
                "status": "success",
                "credits_added": order["credits"],
                "message": f"Successfully added {order['credits']} credits!",
            }

    raise HTTPException(400, "Could not process payment. Please contact support.")


@router.post("/webhook")
async def paypal_webhook(request: Request):
    """Handle PayPal webhook notifications (async backup)."""
    body = await request.json()
    event_type = body.get("event_type", "")

    logger.info("PayPal webhook: %s", event_type)

    if event_type == "CHECKOUT.ORDER.APPROVED":
        resource = body.get("resource", {})
        order_id = resource.get("id")
        logger.info("PayPal order approved via webhook: %s", order_id)
        # The capture will happen from frontend, this is just a backup log

    elif event_type == "PAYMENT.CAPTURE.COMPLETED":
        resource = body.get("resource", {})
        paypal_order_id = resource.get("supplementary_data", {}).get(
            "related_ids", {}
        ).get("order_id")
        amount = resource.get("amount", {})
        logger.info(
            "PayPal capture completed via webhook: order=%s amount=%s %s",
            paypal_order_id,
            amount.get("value"),
            amount.get("currency_code"),
        )

    # Always return 200 to acknowledge
    return {"status": "ok"}
