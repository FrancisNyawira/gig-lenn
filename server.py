import os
import re
import json
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
import ipaddress
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "3000"))

DB_FILE = "gigscan.db"
VERSION = "7.0"
MAX_BODY_SIZE = 1_000_000
MAX_TEXT_LENGTH = 20_000


def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            url TEXT,
            description TEXT,
            payment TEXT,
            reason TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value, max_length=None):
    if value is None:
        return ""

    value = str(value)
    value = re.sub(r"\s+", " ", value).strip()

    if max_length is not None:
        value = value[:max_length]

    return value


def send_json(handler, status_code, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, PATCH, DELETE, OPTIONS",
    )
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        return None, "Invalid Content-Length header."

    if length < 0 or length > MAX_BODY_SIZE:
        return None, "Request body is too large."

    try:
        raw = handler.rfile.read(length)
        if not raw:
            return {}, None

        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None, "JSON body must be an object."

        return data, None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "Request body must contain valid JSON."
    except Exception:
        return None, "Could not read request body."


def analyze_text(text):
    text = clean_text(text, MAX_TEXT_LENGTH)
    lower = text.lower()

    score = 0
    signals = []
    categories = []

    def add_signal(signal_type, title, detail, weight, category):
        nonlocal score

        signals.append({
            "type": signal_type,
            "title": title,
            "detail": detail,
        })

        score += weight

        if category not in categories:
            categories.append(category)

    upfront_patterns = [
        r"\bpay\b.*\b(to )?(apply|start|activate|unlock|register|join)",
        r"\bpay\b.*\bfee\b",
        r"\bregistration fee\b",
        r"\bactivation fee\b",
        r"\bprocessing fee\b",
        r"\btraining fee\b",
        r"\bdeposit\b.*\bjob\b",
        r"\bdeposit\b.*\bwork\b",
        r"\bupfront\b.*\bpayment\b",
        r"\bpay first\b",
        r"\bpayment before\b.*\bjob\b",
        r"\bpay before\b.*\bwork\b",
    ]

    if any(re.search(pattern, lower) for pattern in upfront_patterns):
        add_signal(
            "upfront_fee",
            "Upfront payment requested",
            "The opportunity appears to require money before you can start or access the work.",
            32,
            "Payment",
        )

    job_fee_patterns = [
        r"\bjob fee\b",
        r"\bjob placement fee\b",
        r"\brecruitment fee\b",
        r"\bemployment fee\b",
        r"\bpay.*to get.*job\b",
        r"\bpay.*for.*job\b",
    ]

    if any(re.search(pattern, lower) for pattern in job_fee_patterns):
        add_signal(
            "job_fee",
            "Job-related fee detected",
            "A fee appears to be connected to getting or securing employment.",
            28,
            "Payment",
        )

    security_patterns = [
        r"\botp\b",
        r"\bone[- ]time password\b",
        r"\bmpesa pin\b",
        r"\bpin number\b",
        r"\bpassword\b.*\bsend\b",
        r"\bsend.*\bpassword\b",
        r"\bshare.*\bpin\b",
        r"\bshare.*\botp\b",
        r"\bverification code\b",
        r"\bsecurity code\b",
    ]

    if any(re.search(pattern, lower) for pattern in security_patterns):
        add_signal(
            "security",
            "Sensitive security information requested",
            "The message appears to request an OTP, PIN, password, verification code, or similar security credential.",
            45,
            "Security",
        )

    personal_patterns = [
        r"\bnational id\b",
        r"\bid number\b",
        r"\bpassport number\b",
        r"\bbank account\b",
        r"\bbank details\b",
        r"\bcard number\b",
        r"\bcredit card\b",
        r"\bdebit card\b",
        r"\bdate of birth\b",
        r"\bsocial security\b",
        r"\bcopy of your id\b",
        r"\bsend your id\b",
    ]

    if any(re.search(pattern, lower) for pattern in personal_patterns):
        add_signal(
            "personal_info",
            "Sensitive personal information requested",
            "The opportunity appears to request identity, banking, card, or other sensitive personal information.",
            25,
            "Personal Information",
        )

    messaging_patterns = [
        r"\bwhatsapp\b",
        r"\btelegram\b",
        r"\bcontact me on whatsapp\b",
        r"\bmessage me on telegram\b",
        r"\bjoin.*whatsapp.*group\b",
        r"\bjoin.*telegram.*group\b",
    ]

    if any(re.search(pattern, lower) for pattern in messaging_patterns):
        add_signal(
            "messaging",
            "Messaging-app recruitment detected",
            "The opportunity directs applicants to WhatsApp or Telegram for recruitment or communication.",
            10,
            "Recruitment",
        )

    pressure_patterns = [
        r"\burgent\b",
        r"\bact now\b",
        r"\blimited slots\b",
        r"\blimited places\b",
        r"\btoday only\b",
        r"\bexpires today\b",
        r"\bimmediately\b",
        r"\bwithin.*hours\b",
        r"\bdon't miss\b",
        r"\blast chance\b",
    ]

    if any(re.search(pattern, lower) for pattern in pressure_patterns):
        add_signal(
            "pressure",
            "Urgency or pressure detected",
            "The message uses urgency or scarcity to encourage a quick decision.",
            12,
            "Pressure",
        )

    guaranteed_patterns = [
        r"\bguaranteed income\b",
        r"\bguaranteed earnings\b",
        r"\bguaranteed profit\b",
        r"\bguaranteed money\b",
        r"\bguaranteed salary\b",
        r"\bearn guaranteed\b",
        r"\bguaranteed daily\b",
    ]

    if any(re.search(pattern, lower) for pattern in guaranteed_patterns):
        add_signal(
            "guaranteed_earnings",
            "Guaranteed earnings claim",
            "The opportunity appears to promise guaranteed income or profits.",
            24,
            "Earnings",
        )

    unrealistic_patterns = [
        r"\bearn\b.*\b\d{2,3}[,.]?\d*\b.*\bper day\b",
        r"\bmake\b.*\b\d{2,3}[,.]?\d*\b.*\bper day\b",
        r"\bearn\b.*\b\d{2,3}[,.]?\d*\b.*\bdaily\b",
        r"\bmake\b.*\b\d{2,3}[,.]?\d*\b.*\bdaily\b",
        r"\bthousands\b.*\bper day\b",
        r"\bmillions\b.*\bper month\b",
        r"\bget rich\b",
        r"\bquick money\b",
        r"\beasy money\b",
    ]

    if any(re.search(pattern, lower) for pattern in unrealistic_patterns):
        add_signal(
            "unrealistic",
            "Unusually high earnings claim",
            "The opportunity appears to advertise unusually high or easy earnings.",
            20,
            "Earnings",
        )

    recruitment_patterns = [
        r"\brecruit\b.*\bpeople\b",
        r"\brefer\b.*\bpeople\b",
        r"\binvite\b.*\bpeople\b",
        r"\bbring\b.*\bpeople\b",
        r"\bbuild your team\b",
        r"\bteam members\b.*\bcommission\b",
        r"\bcommission\b.*\brecruit\b",
        r"\bearn.*referral\b",
        r"\breferral bonus\b",
    ]

    if any(re.search(pattern, lower) for pattern in recruitment_patterns):
        add_signal(
            "recruitment",
            "Recruitment or referral-based earnings",
            "The opportunity appears to depend on recruiting or referring other people for earnings.",
            25,
            "Recruitment",
        )

    task_patterns = [
        r"\btask\b.*\bdeposit\b",
        r"\bcomplete tasks\b.*\bpay\b",
        r"\bboost\b.*\bproducts\b",
        r"\bproduct boosting\b",
        r"\border\b.*\breceive commission\b",
        r"\bcomplete.*orders\b.*\bcommission\b",
        r"\boptimization tasks\b",
        r"\bmerchant tasks\b",
    ]

    if any(re.search(pattern, lower) for pattern in task_patterns):
        add_signal(
            "task",
            "Task or product-boosting warning",
            "The description resembles task, order, optimization, or product-boosting work that may involve payments or deposits.",
            28,
            "Task Scheme",
        )

    crypto_patterns = [
        r"\bbitcoin\b",
        r"\bcrypto\b",
        r"\bcryptocurrency\b",
        r"\busdt\b",
        r"\beth\b",
        r"\bethereum\b",
        r"\bcrypto wallet\b",
        r"\bwallet address\b",
    ]

    if any(re.search(pattern, lower) for pattern in crypto_patterns):
        add_signal(
            "crypto",
            "Cryptocurrency payment detected",
            "The opportunity mentions cryptocurrency or crypto-wallet payments.",
            18,
            "Payment",
        )

    gift_patterns = [
        r"\bgift card\b",
        r"\bgift cards\b",
        r"\bairtime\b",
        r"\bairtime voucher\b",
        r"\bgoogle play card\b",
        r"\bapple gift card\b",
        r"\bvoucher code\b",
    ]

    if any(re.search(pattern, lower) for pattern in gift_patterns):
        add_signal(
            "gift",
            "Gift card or airtime payment requested",
            "The opportunity mentions gift cards, vouchers, or airtime as a form of payment.",
            32,
            "Payment",
        )

    easy_job_patterns = [
        r"\bno experience\b.*\bguaranteed\b",
        r"\bguaranteed job\b",
        r"\bguaranteed employment\b",
        r"\beasy job\b",
        r"\banyone can get hired\b",
        r"\bhired immediately\b",
        r"\binstant employment\b",
    ]

    if any(re.search(pattern, lower) for pattern in easy_job_patterns):
        add_signal(
            "easy_employment",
            "Easy or guaranteed employment claim",
            "The opportunity appears to promise unusually easy or guaranteed employment.",
            16,
            "Employment",
        )

    official_patterns = [
        r"\bgovernment\b",
        r"\bministry\b",
        r"\bcounty government\b",
        r"\bpolice\b",
        r"\bcentral bank\b",
        r"\bkenya revenue authority\b",
        r"\bofficial\b",
    ]

    payment_patterns = [
        r"\bpay\b",
        r"\bpayment\b",
        r"\bfee\b",
        r"\bdeposit\b",
        r"\bsend money\b",
    ]

    has_official = any(re.search(pattern, lower) for pattern in official_patterns)
    has_payment = any(re.search(pattern, lower) for pattern in payment_patterns)

    if has_official and has_payment:
        add_signal(
            "official_payment",
            "Official identity combined with payment request",
            "The message references an official institution while also requesting money or payment.",
            22,
            "Identity",
        )

    forwarding_patterns = [
        r"\breceive money\b.*\bsend\b",
        r"\bsend money\b.*\bto another\b",
        r"\bforward\b.*\bpayment\b",
        r"\btransfer money\b.*\bcommission\b",
        r"\buse your account\b.*\btransfer\b",
        r"\breceive.*commission.*send\b",
    ]

    if any(re.search(pattern, lower) for pattern in forwarding_patterns):
        add_signal(
            "money_forwarding",
            "Money transfer or forwarding request",
            "The opportunity appears to involve receiving, transferring, or forwarding money through your account.",
            35,
            "Financial Activity",
        )

    credential_patterns = [
        r"\blogin details\b",
        r"\blogin credentials\b",
        r"\baccount password\b",
        r"\busername and password\b",
        r"\bemail password\b",
        r"\baccess your account\b.*\bpassword\b",
    ]

    if any(re.search(pattern, lower) for pattern in credential_patterns):
        add_signal(
            "credentials",
            "Account credentials requested",
            "The opportunity appears to request login credentials or account access information.",
            45,
            "Security",
        )

    personal_payment_patterns = [
        r"\bsend.*to my mpesa\b",
        r"\bsend.*to my m-pesa\b",
        r"\bpay me via mpesa\b",
        r"\bpay me via m-pesa\b",
        r"\bsend money to my number\b",
        r"\bpay this number\b",
    ]

    if any(re.search(pattern, lower) for pattern in personal_payment_patterns):
        add_signal(
            "personal_payment",
            "Payment to a personal number requested",
            "The opportunity appears to request payment directly to a personal mobile-money number.",
            30,
            "Payment",
        )

    signal_types = {signal["type"] for signal in signals}

    combinations = [
        (
            {"upfront_fee", "messaging"},
            "upfront_messaging",
            "Multiple warning signs appear together",
            "An upfront payment request is combined with messaging-app recruitment.",
            12,
        ),
        (
            {"security", "personal_info"},
            "security_personal",
            "Multiple sensitive-information requests",
            "The opportunity appears to request more than one type of sensitive personal or security information.",
            12,
        ),
        (
            {"guaranteed_earnings", "recruitment"},
            "earnings_recruitment",
            "Earnings and recruitment claims combined",
            "Guaranteed earnings appear alongside recruitment or referral-based activity.",
            12,
        ),
        (
            {"task", "upfront_fee"},
            "task_payment",
            "Task work combined with upfront payment",
            "Task-based work appears to require payment or a deposit.",
            12,
        ),
        (
            {"crypto", "upfront_fee"},
            "crypto_payment",
            "Cryptocurrency and upfront payment combined",
            "Cryptocurrency activity appears alongside an upfront payment request.",
            8,
        ),
        (
            {"pressure", "upfront_fee"},
            "pressure_payment",
            "Pressure combined with payment request",
            "The opportunity appears to use urgency while also requesting payment.",
            8,
        ),
    ]

    for required, signal_type, title, detail, weight in combinations:
        if required.issubset(signal_types):
            add_signal(signal_type, title, detail, weight, "Combined Warning")

    score = max(0, min(100, score))
    risk = calculate_risk(score, signals, categories)

    return {
        "score": score,
        "signals": signals,
        "categories": categories,
        "risk": risk,
    }


def calculate_risk(score, signals=None, categories=None):
    if score >= 60:
        level = "HIGH RISK"
        risk_class = "high"
        message = "This opportunity contains several warning signs that deserve serious caution."
        explanation = "The scan found multiple indicators commonly associated with risky job or gig offers."
        action = "Do not send money or sensitive information until you independently verify the opportunity."
    elif score >= 25:
        level = "CAUTION"
        risk_class = "caution"
        message = "This opportunity contains warning signs that should be checked carefully."
        explanation = "The scan found one or more indicators that may require additional verification."
        action = "Verify the employer, website, payment requests, and contact details before proceeding."
    else:
        level = "NO OBVIOUS WARNING SIGNS"
        risk_class = "low"
        message = "The scan did not find obvious warning signs in the information provided."
        explanation = "No major indicators were detected by the current automated checks."
        action = "Still verify the opportunity independently before sharing sensitive information or making payments."

    return {
        "level": level,
        "class": risk_class,
        "message": message,
        "explanation": explanation,
        "action": action,
    }


def is_public_hostname(hostname):
    try:
        addresses = {ipaddress.ip_address(hostname)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(hostname, None)
            }
        except socket.gaierror:
            return False

    return all(
        not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
        and not address.is_multicast
        for address in addresses
    )


def inspect_website(url):
    result = {
        "url": url,
        "signals": [],
        "website": {},
        "analysis": None,
        "error": None,
    }

    try:
        parsed = urllib.parse.urlparse(url)

        if parsed.scheme not in ("http", "https"):
            url = "https://" + url
            parsed = urllib.parse.urlparse(url)

        hostname = parsed.hostname or ""
        if not hostname:
            result["error"] = "Invalid URL: hostname is missing."
            return result

        result["website"]["hostname"] = hostname
        result["website"]["https"] = parsed.scheme == "https"

        try:
            ipaddress.ip_address(hostname)
            result["signals"].append({
                "type": "ip_address",
                "title": "Website uses an IP address",
                "detail": "The link uses a numerical IP address instead of a normal domain name.",
            })
        except ValueError:
            pass

        if not is_public_hostname(hostname):
            result["error"] = "Private or unreachable hostnames are not allowed."
            return result

        if len(hostname) > 50:
            result["signals"].append({
                "type": "long_hostname",
                "title": "Unusually long website address",
                "detail": "The hostname is unusually long and should be checked carefully.",
            })

        if "xn--" in hostname.lower():
            result["signals"].append({
                "type": "punycode",
                "title": "Punycode domain detected",
                "detail": "The domain contains Punycode characters and should be independently verified.",
            })

        request = urllib.request.Request(
            url,
            headers={"User-Agent": "GigLenn/7.0 Website Inspector"},
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
                final_url = response.geturl()
                final_parsed = urllib.parse.urlparse(final_url)

                if final_parsed.hostname and not is_public_hostname(final_parsed.hostname):
                    result["error"] = "Redirected to a private or unreachable hostname."
                    return result

                raw = response.read(500000)
                charset = response.headers.get_content_charset() or "utf-8"
                page_text = raw.decode(charset, errors="ignore")

                result["website"]["status"] = status
                result["website"]["final_url"] = final_url

                title_match = re.search(
                    r"<title[^>]*>(.*?)</title>",
                    page_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                title = ""
                if title_match:
                    title = clean_text(re.sub("<[^>]+>", " ", title_match.group(1)))

                result["website"]["title"] = title

                visible_text = re.sub(
                    r"<script\b[^>]*>.*?</script>",
                    " ",
                    page_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                visible_text = re.sub(
                    r"<style\b[^>]*>.*?</style>",
                    " ",
                    visible_text,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                visible_text = clean_text(re.sub(r"<[^>]+>", " ", visible_text))

                result["website"]["text_preview"] = visible_text[:2000]
                result["analysis"] = analyze_text((title + " " + visible_text)[:MAX_TEXT_LENGTH])

        except urllib.error.HTTPError as error:
            result["website"]["status"] = error.code
            result["error"] = f"Website returned HTTP {error.code}."
        except urllib.error.URLError as error:
            result["error"] = f"Could not access website: {error.reason}"
        except Exception as error:
            result["error"] = f"Website inspection failed: {error}"

        if not result["website"].get("https", False):
            result["signals"].append({
                "type": "http",
                "title": "Website is not using HTTPS",
                "detail": "The submitted link does not use HTTPS.",
            })

        return result
    except Exception as error:
        result["error"] = str(error)
        return result


class GigLennHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PATCH, DELETE, OPTIONS",
        )
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            send_json(self, 200, {
                "name": "GigLenn",
                "version": VERSION,
                "status": "online",
            })
            return

        if path == "/analyze":
            text = params.get("text", [""])[0]
            if not text.strip():
                send_json(self, 400, {"error": "No text provided."})
                return

            analysis = analyze_text(text)
            send_json(self, 200, {"analysis": analysis, "risk": analysis["risk"]})
            return

        if path == "/check":
            url = params.get("url", [""])[0]
            if not url.strip():
                send_json(self, 400, {"error": "No URL provided."})
                return

            send_json(self, 200, inspect_website(url))
            return

        if path == "/reports":
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT * FROM reports ORDER BY id DESC"
                ).fetchall()
                reports = [dict(row) for row in rows]
            finally:
                conn.close()

            send_json(self, 200, {"reports": reports})
            return

        send_json(self, 404, {"error": "Endpoint not found."})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/reports":
            send_json(self, 404, {"error": "Endpoint not found."})
            return

        data, error = read_json(self)
        if error:
            send_json(self, 400, {"error": error})
            return

        title = clean_text(data.get("title", ""), 200)
        url = clean_text(data.get("url", ""), 2_000)
        description = clean_text(data.get("description", ""), 10_000)
        payment = clean_text(data.get("payment", ""), 2_000)
        reason = clean_text(data.get("reason", ""), 10_000)

        if not title or not description:
            send_json(self, 400, {"error": "Title and description are required."})
            return

        conn = get_db()
        try:
            cursor = conn.execute(
                """
                INSERT INTO reports (
                    title, url, description, payment, reason, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (title, url, description, payment, reason, "pending", now_iso()),
            )
            conn.commit()
            report_id = cursor.lastrowid
        finally:
            conn.close()

        send_json(self, 201, {
            "success": True,
            "id": report_id,
            "message": "Report submitted successfully.",
        })

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        match = re.match(r"^/reports/(\d+)$", parsed.path)
        if not match:
            send_json(self, 404, {"error": "Report not found."})
            return

        data, error = read_json(self)
        if error:
            send_json(self, 400, {"error": error})
            return

        status = clean_text(data.get("status", ""))
        if status not in ("pending", "reviewed", "resolved", "rejected"):
            send_json(self, 400, {"error": "Invalid status."})
            return

        report_id = int(match.group(1))
        conn = get_db()
        try:
            cursor = conn.execute(
                "UPDATE reports SET status = ? WHERE id = ?",
                (status, report_id),
            )
            conn.commit()
            updated = cursor.rowcount
        finally:
            conn.close()

        if not updated:
            send_json(self, 404, {"error": "Report not found."})
            return

        send_json(self, 200, {
            "success": True,
            "message": "Report updated successfully.",
        })

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/reports":
            conn = get_db()
            try:
                conn.execute("DELETE FROM reports")
                conn.commit()
            finally:
                conn.close()

            send_json(self, 200, {
                "success": True,
                "message": "All reports deleted.",
            })
            return

        match = re.match(r"^/reports/(\d+)$", parsed.path)
        if match:
            report_id = int(match.group(1))
            conn = get_db()
            try:
                cursor = conn.execute(
                    "DELETE FROM reports WHERE id = ?",
                    (report_id,),
                )
                conn.commit()
                deleted = cursor.rowcount
            finally:
                conn.close()

            if not deleted:
                send_json(self, 404, {"error": "Report not found."})
                return

            send_json(self, 200, {
                "success": True,
                "message": "Report deleted.",
            })
            return

        send_json(self, 404, {"error": "Endpoint not found."})


if __name__ == "__main__":
    init_db()

    server = HTTPServer((HOST, PORT), GigLennHandler)

    print("==========================================")
    print("GigLenn Backend v7.0")
    print("==========================================")
    print(f"Server: http://0.0.0.0:{PORT}")
    print(f"Database: {DB_FILE}")
    print("Status: ONLINE")
    print("==========================================")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nGigLenn backend stopped.")
    finally:
        server.server_close()
