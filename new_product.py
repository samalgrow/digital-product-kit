#!/usr/bin/env python3
"""Put a digital product on sale on its own domain, in one command.

  ./new_product.py --name "The Houseplant Handbook" --price 19 \\
      --file handbook.pdf --domain houseplanthandbook.com --seller "Maya Green"

What it does:
  1. Buys the domain at GoDaddy if you don't own it yet (with --buy)
  2. Creates the product and price in Stripe
  3. Points the domain at this server (GoDaddy or Cloudflare DNS)
  4. Sets up order email from orders@<domain> with Resend
  5. Writes the sales page and thank-you page
  6. Configures nginx and gets an HTTPS certificate
Safe to run again: it updates what exists instead of making duplicates.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from kit.common import ENV, FILES_DIR, ROOT, HttpError, db, get_setting, http, set_setting, stripe
from kit.dns import provider_for

PORT = ENV.get("PORT", "8750")
GREEN, DIM, BOLD, RESET = "\033[32m", "\033[2m", "\033[1m", "\033[0m"


def step(text):
    print(f"\n{BOLD}{text}{RESET}")


def done(text):
    print(f"  {GREEN}✓{RESET} {text}")


def sudo(*cmd, stdin=None):
    subprocess.run(["sudo", *cmd], input=stdin, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def check_env():
    # "sk_test_..." and "you@example.com" are the placeholders from .env.example.
    missing = [k for k in ("STRIPE_SECRET_KEY", "RESEND_API_KEY", "SUPPORT_EMAIL")
               if not ENV.get(k) or "..." in ENV[k] or ENV[k].endswith("@example.com")]
    if missing:
        sys.exit(f"Missing in .env: {', '.join(missing)}. Run: nano .env")


# ------------------------------------------------------------------ Stripe


def stripe_product(args, slug, cents):
    found = stripe("GET", "/v1/products/search",
                   {"query": f"metadata['product_slug']:'{slug}'"})["data"]
    if found:
        product = stripe("POST", f"/v1/products/{found[0]['id']}",
                         {"name": args.name, "active": "true"})
    else:
        product = stripe("POST", "/v1/products", {"name": args.name,
                                                   "metadata[product_slug]": slug})
    prices = stripe("GET", "/v1/prices", {"product": product["id"], "active": "true"})["data"]
    price = next((p for p in prices if p["unit_amount"] == cents
                  and p["currency"] == args.currency), None)
    if not price:
        price = stripe("POST", "/v1/prices", {"product": product["id"], "unit_amount": cents,
                                              "currency": args.currency})
    return product["id"], price["id"]


def stripe_webhook(conn, domain):
    """One webhook per Stripe mode (test/live) is enough for every product."""
    mode = "test" if "_test_" in ENV["STRIPE_SECRET_KEY"] else "live"
    if get_setting(conn, f"webhook_secret_{mode}"):
        return "already set up"
    endpoint = stripe("POST", "/v1/webhook_endpoints", {
        "url": f"https://{domain}/webhook",
        "enabled_events[0]": "checkout.session.completed",
        "enabled_events[1]": "checkout.session.async_payment_succeeded",
        "description": "digital-product-kit",
    })
    set_setting(conn, f"webhook_secret_{mode}", endpoint["secret"])
    return f"https://{domain}/webhook"


# ------------------------------------------------------------------ domain, DNS + email


def money(amount):
    return f"${amount['value'] / 100:.2f}" if amount["currencyCode"] == "USD" \
        else f"{amount['value'] / 100:.2f} {amount['currencyCode']}"


def ensure_domain(args, domain, provider_name, dns):
    """Returns a line for the log. Buys the domain only with --buy and a yes."""
    if provider_name != "GoDaddy":
        if args.buy:
            sys.exit("Buying a domain only works with GoDaddy. Set GODADDY_TOKEN in .env.")
        return f"{domain} is in your Cloudflare account"
    if dns.owns():
        return f"{domain} is already yours"
    quote = dns.quote()
    if not quote:
        sys.exit(f"{domain} is taken. Pick another name.")
    price, renews = money(quote["price"]), money(quote["renewalPrice"])
    if not args.buy:
        sys.exit(f"{domain} is not in your GoDaddy account. It's available for {price} "
                 f"(renews at {renews}/year). Run again with --buy to buy it.")
    agreements = ", ".join(a["url"] for a in quote["requiredAgreements"])
    print(f"  {domain} costs {price} for the first year, then {renews}/year.")
    print(f"  {DIM}Buying accepts GoDaddy's terms: {agreements}{RESET}")
    if not args.yes:
        answer = input("  Buy it with the card on your GoDaddy account? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            sys.exit("Stopped. Nothing was bought.")
    agreed_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    dns.register(quote, agreed_at)
    return f"bought {domain} for {price}"



def resend_domain(domain):
    headers = {"Authorization": f"Bearer {ENV['RESEND_API_KEY']}"}
    existing = [d for d in http("GET", "https://api.resend.com/domains", headers=headers)["data"]
                if d["name"] == domain]
    created = existing[0] if existing else http(
        "POST", "https://api.resend.com/domains", headers=headers, json_body={"name": domain})
    detail = http("GET", f"https://api.resend.com/domains/{created['id']}", headers=headers)
    return detail["id"], detail["status"], detail["records"], headers


def wait_for_resend(domain_id, headers, minutes=5):
    http("POST", f"https://api.resend.com/domains/{domain_id}/verify", headers=headers)
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        status = http("GET", f"https://api.resend.com/domains/{domain_id}", headers=headers)["status"]
        if status == "verified":
            return True
        time.sleep(10)
    return False


# ------------------------------------------------------------------ web


def write_pages(args, domain, webroot):
    fill = {
        "{{TITLE}}": escape(args.name),
        "{{DESCRIPTION}}": escape(args.description),
        "{{PRICE}}": escape(format_price(args.price, args.currency)),
        "{{SELLER}}": escape(args.seller),
        "{{SUPPORT_EMAIL}}": escape(ENV["SUPPORT_EMAIL"]),
        "{{COVER}}": f'<img class="cover" src="/cover{Path(args.cover).suffix}" alt="">'
                     if args.cover else "",
    }
    sudo("mkdir", "-p", webroot)
    for name in ("index.html", "thank-you.html"):
        html = (ROOT / "templates" / name).read_text()
        for key, val in fill.items():
            html = html.replace(key, val)
        sudo("tee", f"{webroot}/{name}", stdin=html.encode())
    if args.cover:
        sudo("cp", args.cover, f"{webroot}/cover{Path(args.cover).suffix}")


def nginx_config(domain, webroot, https):
    proxy = f"""
    location ~ ^/(checkout|webhook|order-link|downloads/) {{
        proxy_pass http://127.0.0.1:{PORT};
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }}

    location / {{
        try_files $uri $uri/ =404;
    }}"""
    acme = f"location /.well-known/acme-challenge/ {{ root {webroot}; }}"
    if not https:
        return f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain} www.{domain};
    root {webroot};
    {acme}
{proxy}
}}
"""
    return f"""server {{
    listen 80;
    listen [::]:80;
    server_name {domain} www.{domain};
    {acme}
    location / {{ return 301 https://{domain}$request_uri; }}
}}

server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {domain} www.{domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    root {webroot};
{proxy}
}}
"""


def install_nginx(domain, conf):
    path = f"/etc/nginx/sites-available/{domain}"
    sudo("tee", path, stdin=conf.encode())
    sudo("ln", "-sf", path, f"/etc/nginx/sites-enabled/{domain}")
    sudo("nginx", "-t")
    sudo("systemctl", "reload", "nginx")


def get_certificate(domain, webroot):
    if subprocess.run(["sudo", "test", "-e", f"/etc/letsencrypt/live/{domain}"]).returncode == 0:
        return "already have one"
    # Fresh DNS can take a minute to reach Let's Encrypt, so try a few times.
    for attempt in range(6):
        try:
            sudo("certbot", "certonly", "--webroot", "-w", webroot, "-d", domain,
                 "-d", f"www.{domain}", "--non-interactive", "--agree-tos",
                 "-m", ENV["SUPPORT_EMAIL"])
            return "issued"
        except subprocess.CalledProcessError as err:
            if attempt == 5:
                sys.exit(f"certbot failed:\n{err.stderr.decode()}")
            print(f"  {DIM}waiting for DNS to spread, retrying in 30s{RESET}")
            time.sleep(30)


# ------------------------------------------------------------------ main


def format_price(price, currency):
    symbol = {"usd": "$", "gbp": "£", "eur": "€"}.get(currency, "")
    amount = f"{price:.2f}".removesuffix(".00")
    return f"{symbol}{amount}" if symbol else f"{amount} {currency.upper()}"


def main():
    ap = argparse.ArgumentParser(description="Put a digital product on sale on its own domain.")
    ap.add_argument("--name", required=True, help="product title")
    ap.add_argument("--price", required=True, type=float, help="e.g. 19 or 19.99")
    ap.add_argument("--file", required=True, action="append", dest="files",
                    help="file the buyer gets (repeat for more than one)")
    ap.add_argument("--domain", required=True, help="e.g. houseplanthandbook.com")
    ap.add_argument("--seller", required=True, help="your name, shown on the page and emails")
    ap.add_argument("--description", default="", help="one or two lines for the sales page")
    ap.add_argument("--cover", help="cover image for the sales page")
    ap.add_argument("--currency", default="usd")
    ap.add_argument("--server-ip", help="defaults to this server's public IP")
    ap.add_argument("--buy", action="store_true",
                    help="buy the domain at GoDaddy if you don't own it yet")
    ap.add_argument("--yes", action="store_true", help="don't ask before buying the domain")
    args = ap.parse_args()
    check_env()

    domain = args.domain.lower().removeprefix("www.")
    if not re.fullmatch(r"([a-z0-9-]+\.)+[a-z]{2,}", domain):
        sys.exit(f"That doesn't look like a domain: {args.domain} (example: houseplanthandbook.com)")
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    cents = round(args.price * 100)
    webroot = f"/var/www/{domain}"
    for f in args.files + ([args.cover] if args.cover else []):
        if not Path(f).is_file():
            sys.exit(f"Not a file: {f}")

    print(f"{BOLD}Setting up {args.name} on {domain}{RESET}")

    step("1. Domain")
    provider_name, dns = provider_for(domain)
    done(ensure_domain(args, domain, provider_name, dns))

    step("2. Files")
    dest = FILES_DIR / slug
    db().close()  # creates data/ owner-only before the files go in
    dest.mkdir(parents=True, exist_ok=True)
    names = []
    for f in args.files:
        shutil.copy2(f, dest / Path(f).name)
        names.append(Path(f).name)
        done(f"{Path(f).name} stored")

    step("3. Stripe")
    product_id, price_id = stripe_product(args, slug, cents)
    done(f"product {product_id}")
    done(f"price {format_price(args.price, args.currency)} ({price_id})")
    with db() as conn:
        done(f"webhook {stripe_webhook(conn, domain)}")
        conn.execute(
            "INSERT INTO products (slug, title, domain, seller_name, price_id, files) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(slug) DO UPDATE SET title = excluded.title, "
            "domain = excluded.domain, seller_name = excluded.seller_name, "
            "price_id = excluded.price_id, files = excluded.files",
            (slug, args.name, domain, args.seller, price_id, json.dumps(names)))

    step("4. DNS")
    ip = args.server_ip or http("GET", "https://api.ipify.org?format=json")["ip"]
    dns.set_record("A", "@", ip)
    done(f"{domain} -> {ip} ({provider_name})")
    dns.set_record("CNAME", "www", domain if provider_name == "Cloudflare" else "@")
    done(f"www.{domain} -> {domain}")

    step("5. Order email")
    resend_id, status, records, resend_headers = resend_domain(domain)
    for r in records:
        name = r["name"].removesuffix(f".{domain}")
        dns.set_record(r["type"], name, r["value"],
                       priority=int(r["priority"]) if r.get("priority") is not None else None)
        done(f"{r['type']} {name}")

    step("6. Sales page + HTTPS")
    write_pages(args, domain, webroot)
    done("pages written")
    install_nginx(domain, nginx_config(domain, webroot, https=False))
    done("nginx site added")
    done(f"certificate {get_certificate(domain, webroot)}")
    install_nginx(domain, nginx_config(domain, webroot, https=True))
    done("HTTPS on")
    # Picks up .env changes (keys added after install.sh, test -> live).
    sudo("systemctl", "restart", "digital-product-kit")
    done("checkout service restarted")

    step("7. Checking email sending")
    if status == "verified" or wait_for_resend(resend_id, resend_headers):
        done(f"orders@{domain} verified")
    else:
        print(f"  {DIM}Resend is still checking the records. Orders will email once it "
              f"shows 'verified' at resend.com/domains.{RESET}")

    mode = "TEST mode, pay with 4242 4242 4242 4242" if "_test_" in ENV["STRIPE_SECRET_KEY"] else "LIVE"
    print(f"\n{GREEN}{BOLD}Live: https://{domain}{RESET}  {DIM}({mode}){RESET}\n")


if __name__ == "__main__":
    try:
        main()
    except HttpError as err:
        sys.exit(str(err))
