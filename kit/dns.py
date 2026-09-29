"""Set DNS records at GoDaddy or Cloudflare (both expose set_record), and buy domains at GoDaddy."""

import time
import urllib.parse
import uuid

from kit.common import ENV, HttpError, http


class GoDaddy:
    API = "https://api.godaddy.com"

    def __init__(self, domain):
        self.domain = domain
        self.headers = {"Authorization": f"Bearer {ENV['GODADDY_TOKEN']}"}

    def owns(self):
        try:
            http("GET", f"{self.API}/v1/domains/{self.domain}", headers=self.headers)
            return True
        except HttpError as err:
            if err.status == 404:
                return False
            raise

    def quote(self):
        """Free price check. Returns the quote, or None if the name is taken."""
        q = http("POST", f"{self.API}/v3/domains/registration-quotes", headers=self.headers,
                 json_body={"domain": self.domain, "period": 1})
        return q if q.get("available") else None

    def register(self, quote, agreed_at):
        """Buy the domain with the card saved on the GoDaddy account, then wait for it."""
        body = {
            "quoteToken": quote["quoteToken"],
            "domain": self.domain,
            "period": 1,
            "consent": {
                "agreedAt": agreed_at,
                "agreementTypes": [a["agreementType"] for a in quote["requiredAgreements"]],
            },
        }
        if quote.get("fees"):
            body["consent"]["acknowledgedFees"] = [
                {"type": f["type"], "fee": f["fee"]} for f in quote["fees"]]
        # The same key on a retry returns the first attempt instead of charging twice.
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        reg = http("POST", f"{self.API}/v3/domains/registrations", headers=headers,
                   json_body=body)
        for _ in range(60):
            if reg["status"] in ("COMPLETED", "FAILED"):
                break
            time.sleep(5)
            reg = http("GET", f"{self.API}/v3/domains/registrations/{reg['registrationId']}",
                       headers=self.headers)
        if reg["status"] != "COMPLETED":
            raise SystemExit(f"GoDaddy did not finish registering {self.domain}: {reg}")

    def set_record(self, rtype, name, value, priority=None):
        """Replace every record of this type + name with this one value."""
        record = {"data": value, "ttl": 600}
        if priority is not None:
            record["priority"] = priority
        url = (f"{self.API}/v1/domains/{self.domain}/records/{rtype}/"
               f"{urllib.parse.quote(name, safe='')}")
        # A domain bought seconds ago can take a minute before its DNS zone exists.
        for attempt in range(12):
            try:
                return http("PUT", url, headers=self.headers, json_body=[record])
            except HttpError as err:
                if err.status not in (404, 422) or attempt == 11:
                    raise
                time.sleep(10)


class Cloudflare:
    API = "https://api.cloudflare.com/client/v4"

    def __init__(self, domain):
        self.domain = domain
        self.headers = {"Authorization": f"Bearer {ENV['CLOUDFLARE_API_TOKEN']}"}
        zones = http("GET", f"{self.API}/zones?name={domain}", headers=self.headers)["result"]
        if not zones:
            raise SystemExit(f"{domain} is not in this Cloudflare account.")
        self.zone = zones[0]["id"]

    def set_record(self, rtype, name, value, priority=None):
        fqdn = self.domain if name == "@" else f"{name}.{self.domain}"
        record = {"type": rtype, "name": fqdn, "content": value, "ttl": 1, "proxied": False}
        if priority is not None:
            record["priority"] = priority
        base = f"{self.API}/zones/{self.zone}/dns_records"
        query = urllib.parse.urlencode({"type": rtype, "name": fqdn})
        existing = http("GET", f"{base}?{query}", headers=self.headers)["result"]
        if existing:
            http("PUT", f"{base}/{existing[0]['id']}", headers=self.headers, json_body=record)
        else:
            http("POST", base, headers=self.headers, json_body=record)


def provider_for(domain):
    if ENV.get("CLOUDFLARE_API_TOKEN"):
        return "Cloudflare", Cloudflare(domain)
    if ENV.get("GODADDY_TOKEN"):
        return "GoDaddy", GoDaddy(domain)
    raise SystemExit("Add GoDaddy or Cloudflare keys to .env (see .env.example).")
