"""The small web service that sits behind every product domain.

  POST /checkout                 start a Stripe Checkout for a product, redirect to it
  POST /webhook                  Stripe says "paid" -> save the order, email the link
  GET  /order-link?session_id=   thank-you page asks for the buyer's download link
  GET  /downloads/<token>        the buyer's download page
  GET  /downloads/<token>/<n>    one file
  GET  /health                   {"ok": true}

nginx serves the sales page itself and forwards these paths here.
"""

import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from html import escape

from flask import Flask, abort, redirect, request, send_from_directory

from kit.common import ENV, FILES_DIR, db, get_setting, http, stripe

app = Flask(__name__)


def stripe_mode():
    return "test" if "_test_" in ENV.get("STRIPE_SECRET_KEY", "") else "live"


def product_for_host(conn):
    host = request.host.split(":")[0].lower().removeprefix("www.")
    return conn.execute("SELECT * FROM products WHERE domain = ?", (host,)).fetchone()


@app.post("/checkout")
def checkout():
    with db() as conn:
        product = product_for_host(conn)
    if not product:
        abort(404)
    base = f"https://{product['domain']}"
    session = stripe("POST", "/v1/checkout/sessions", {
        "mode": "payment",
        "line_items[0][price]": product["price_id"],
        "line_items[0][quantity]": "1",
        "metadata[product_slug]": product["slug"],
        "success_url": base + "/thank-you.html?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": base + "/",
        "allow_promotion_codes": "true",
    })
    return redirect(session["url"], code=303)


def signature_ok(payload, header, secret):
    """Stripe's v1 webhook signature: HMAC-SHA256 of "<t>.<body>"."""
    if not header or not secret:
        return False
    parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
    timestamp = next((v for k, v in parts if k == "t"), None)
    sigs = [v for k, v in parts if k == "v1"]
    if not timestamp or not timestamp.isdigit() or abs(time.time() - int(timestamp)) > 300:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload,
                        hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in sigs)


def send_order_email(product, email, token):
    link = f"https://{product['domain']}/downloads/{token}"
    http("POST", "https://api.resend.com/emails",
         headers={"Authorization": f"Bearer {ENV['RESEND_API_KEY']}"},
         json_body={
             "from": f"{product['seller_name']} <orders@{product['domain']}>",
             "to": [email],
             "reply_to": ENV["SUPPORT_EMAIL"],
             "subject": f"Your copy of {product['title']} is ready",
             "text": (
                 f"Hi,\n\nThank you for your order. Your copy of {product['title']} "
                 f"is ready.\n\nDownload it here:\n{link}\n\n"
                 f"That link is yours, so save the files somewhere safe once you "
                 f"have them.\n\nIf anything doesn't work, just reply to this email.\n\n"
                 f"{product['seller_name']}"
             ),
         })


@app.post("/webhook")
def webhook():
    payload = request.get_data()
    with db() as conn:
        secret = get_setting(conn, f"webhook_secret_{stripe_mode()}")
    if not signature_ok(payload, request.headers.get("Stripe-Signature"), secret):
        abort(400)
    event = json.loads(payload)
    if event.get("type") not in ("checkout.session.completed",
                                 "checkout.session.async_payment_succeeded"):
        return {"received": True}

    session = event["data"]["object"]
    # Bank payments can "complete" before the money arrives. Deliver only once it's paid;
    # Stripe sends async_payment_succeeded when a delayed payment clears.
    if session.get("payment_status") != "paid":
        return {"received": True, "waiting_for_payment": True}
    slug = (session.get("metadata") or {}).get("product_slug")
    email = (session.get("customer_details") or {}).get("email")
    with db() as conn:
        product = conn.execute("SELECT * FROM products WHERE slug = ?", (slug,)).fetchone()
        # Payments for anything this kit didn't sell: acknowledge and ignore.
        if not product or not email:
            return {"received": True, "ignored": True}
        token = str(uuid.uuid4())
        cur = conn.execute(
            "INSERT INTO orders (token, email, slug, session_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(session_id) DO NOTHING", (token, email, slug, session["id"]))
        if cur.rowcount == 0:
            return {"received": True, "duplicate": True}

    try:
        send_order_email(product, email, token)
    except Exception:
        # The email is the product. Drop the order so Stripe's retry sends it again.
        app.logger.exception("order email failed for %s", session["id"])
        with db() as conn:
            conn.execute("DELETE FROM orders WHERE session_id = ?", (session["id"],))
        abort(500)
    return {"received": True}


@app.get("/order-link")
def order_link():
    """Lets the thank-you page show the download link straight away. Session ids
    are long and unguessable, and only orders from the last day are answered."""
    sid = request.args.get("session_id", "")
    if not re.fullmatch(r"cs_(live|test)_[A-Za-z0-9]{10,200}", sid):
        return {"ready": False}, 400
    with db() as conn:
        row = conn.execute(
            "SELECT o.token, p.domain FROM orders o JOIN products p ON p.slug = o.slug "
            "WHERE o.session_id = ? AND o.created_at > datetime('now', '-1 day')",
            (sid,)).fetchone()
    if not row:
        return {"ready": False}
    return {"ready": True, "url": f"https://{row['domain']}/downloads/{row['token']}"}


def load_order(token):
    try:
        uuid.UUID(token)
    except ValueError:
        abort(404)
    with db() as conn:
        order = conn.execute(
            "SELECT o.*, p.title, p.files, p.expiry_days FROM orders o "
            "JOIN products p ON p.slug = o.slug WHERE o.token = ?", (token,)).fetchone()
    if not order:
        abort(404)
    created = datetime.fromisoformat(order["created_at"]).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > created + timedelta(days=order["expiry_days"]):
        abort(410, "This download link has expired.")
    return order


PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} downloads</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 560px; margin: 64px auto;
         padding: 0 20px; color: #111; }}
  a.file {{ display: block; padding: 14px 18px; margin: 12px 0; background: #111;
            color: #fff; text-decoration: none; border-radius: 8px; }}
  p.note {{ color: #666; font-size: 14px; }}
</style></head><body>
<h1>{title}</h1>
<p>Your files are below. Click each one to download.</p>
{links}
<p class="note">Need help? Email {support}.</p>
</body></html>"""


@app.get("/downloads/<token>")
def download_page(token):
    order = load_order(token)
    links = "\n".join(
        f'<a class="file" href="/downloads/{token}/{i}">Download {escape(name)}</a>'
        for i, name in enumerate(json.loads(order["files"])))
    return PAGE.format(title=escape(order["title"]), links=links,
                       support=escape(ENV.get("SUPPORT_EMAIL", "")))


@app.get("/downloads/<token>/<int:n>")
def download_file(token, n):
    order = load_order(token)
    files = json.loads(order["files"])
    if not 0 <= n < len(files):
        abort(404)
    with db() as conn:
        conn.execute("UPDATE orders SET downloads = downloads + 1 WHERE token = ?", (token,))
    # The file name comes only from the database, never from the URL.
    return send_from_directory(FILES_DIR / order["slug"], files[n], as_attachment=True)


@app.get("/health")
def health():
    return {"ok": True}
