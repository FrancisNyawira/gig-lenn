import json
import re
import sqlite3
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HOST = "localhost"
PORT = 3000
DB_FILE = "GigLenn.db"
VERSION = "7.0"


# -----------------------------
# DATABASE
# -----------------------------

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            link TEXT,
            source TEXT,
            payment TEXT,
            amount TEXT,
            details TEXT,
            email TEXT,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# -----------------------------
# TEXT HELPERS
# -----------------------------

def clean_text(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def contains_any(text, patterns):
    text = text.lower()
    return any(pattern.lower() in text for pattern in patterns)


def add_signal(signals, signal_type, title, detail):
    for signal in signals:
        if signal["title"].lower() == title.lower():
            return False

    signals.append({
        "type": signal_type,
        "title": title,
        "detail": detail
    })

    return True


# -----------------------------
# SMART TEXT ANALYSIS
# -----------------------------

def analyze_text(text):
    text = clean_text(text)
    lower = text.lower()

    score = 0
    signals = []
    categories = []

    def add_category(category):
        if category not in categories:
            categories.append(category)

    def add_warning(points, signal_type, title, detail, category):
        nonlocal score

        added = add_signal(
            signals,
            signal_type,
            title,
            detail
        )

        if added:
            score += points
            add_category(category)

    # 1. Upfront payment
    if contains_any(lower, [
        "registration fee",
        "registration fees",
        "pay a registration",
        "pay registration",
        "joining fee",
        "joining fees",
        "activation fee",
        "activation fees",
        "deposit to start",
        "pay to start",
        "pay before you start",
        "fee before starting",
        "upfront fee",
        "upfront payment",
        "pay upfront"
    ]):
        add_warning(
            32,
            "financial",
            "Upfront payment requested",
            "The opportunity appears to require money before work begins.",
            "financial"
        )

    # 2. Job/application fee
    if contains_any(lower, [
        "job fee",
        "application fee",
        "pay to apply",
        "pay for the job",
        "employment fee",
        "processing fee",
        "training fee",
        "training fees",
        "interview fee",
        "placement fee",
        "recruitment fee"
    ]):
        add_warning(
            28,
            "financial",
            "Job-related fee requested",
            "A fee appears to be connected to applying, training, recruitment, or getting the job.",
            "financial"
        )

    # 3. OTP/PIN/password/security
    if contains_any(lower, [
        "otp",
        "one time password",
        "one-time password",
        "verification code",
        "security code",
        "mpesa pin",
        "m-pesa pin",
        "pin number",
        "password",
        "login password",
        "bank pin",
        "card pin",
        "cvv"
    ]):
        add_warning(
            45,
            "security",
            "Sensitive security information requested",
            "The opportunity appears to request a password, PIN, OTP, verification code, or similar security credential.",
            "security"
        )

    # 4. Personal information
    if contains_any(lower, [
        "send your id",
        "send id",
        "national id",
        "copy of your id",
        "passport copy",
        "passport number",
        "bank account",
        "bank details",
        "credit card",
        "debit card",
        "personal information",
        "sensitive information",
        "date of birth"
    ]):
        add_warning(
            25,
            "personal",
            "Sensitive personal information requested",
            "The opportunity appears to request personal or financial information that should be handled carefully.",
            "personal"
        )

    # 5. WhatsApp / Telegram recruitment
    if contains_any(lower, [
        "whatsapp",
        "whatsapp recruiter",
        "contact me on whatsapp",
        "telegram",
        "contact me on telegram",
        "message us on whatsapp"
    ]):
        add_warning(
            10,
            "communication",
            "Off-platform messaging used for recruitment",
            "Recruitment appears to rely on WhatsApp or Telegram rather than an independently verifiable company process.",
            "communication"
        )

    # 6. Urgency / pressure
    if contains_any(lower, [
        "limited slots",
        "limited slot",
        "act now",
        "apply now",
        "hurry",
        "urgent",
        "immediately",
        "today only",
        "last chance",
        "offer expires",
        "don't miss",
        "do not miss",
        "only a few slots",
        "start today"
    ]):
        add_warning(
            12,
            "pressure",
            "Urgency or pressure detected",
            "The wording creates pressure to act quickly or before the opportunity can be independently checked.",
            "pressure"
        )

    # 7. Guaranteed earnings
    if contains_any(lower, [
        "guaranteed income",
        "guaranteed earnings",
        "guaranteed salary",
        "guaranteed money",
        "guaranteed profit",
        "earn guaranteed",
        "100% guaranteed",
        "fixed guaranteed income"
    ]):
        add_warning(
            24,
            "earnings",
            "Guaranteed earnings claim",
            "The opportunity appears to promise guaranteed income or earnings.",
            "earnings"
        )

    # 8. Unrealistic earnings
    if contains_any(lower, [
        "earn 100,000",
        "earn ksh 100,000",
        "earn ksh100,000",
        "make 100,000",
        "earn 50,000",
        "earn ksh 50,000",
        "earn ksh50,000",
        "make 50,000",
        "earn 30,000",
        "earn ksh 30,000",
        "earn ksh30,000",
        "make 30,000",
        "thousands per day",
        "thousands daily",
        "easy money",
        "huge income",
        "massive income",
        "high income with no experience"
    ]):
        add_warning(
            20,
            "earnings",
            "Potentially unrealistic earnings claim",
            "The advertised earnings may be unusually high compared with the work described.",
            "earnings"
        )

    # 9. Recruitment / referral schemes
    if contains_any(lower, [
        "recruit others",
        "recruit people",
        "refer people",
        "referral bonus",
        "referral income",
        "earn by recruiting",
        "build your team",
        "team commission",
        "downline",
        "recruit members"
    ]):
        add_warning(
            25,
            "recruitment",
            "Recruitment-based earnings",
            "The opportunity appears to emphasize recruiting or referring other people for income.",
            "recruitment"
        )

    # 10. Task / product boosting
    if contains_any(lower, [
        "product boosting",
        "boost products",
        "task optimization",
        "optimization tasks",
        "complete tasks and recharge",
        "recharge your account",
        "top up your account",
        "order boosting",
        "merchant tasks",
        "complete orders",
        "commission tasks"
    ]):
        add_warning(
            28,
            "task",
            "Task or product-boosting pattern detected",
            "The description resembles task, order, product-boosting, or recharge-based work patterns that can involve financial risk.",
            "task"
        )

    # 11. Crypto
    if contains_any(lower, [
        "send bitcoin",
        "send crypto",
        "cryptocurrency payment",
        "crypto payment",
        "usdt",
        "btc payment",
        "ethereum payment",
        "wallet address",
        "crypto wallet"
    ]):
        add_warning(
            18,
            "financial",
            "Cryptocurrency payment involved",
            "The opportunity appears to involve cryptocurrency payments or transfers.",
            "financial"
        )

    # 12. Gift cards / airtime
    if contains_any(lower, [
        "gift card",
        "gift cards",
        "airtime voucher",
        "airtime",
        "buy airtime",
        "send airtime",
        "voucher code",
        "itunes card",
        "google play card"
    ]):
        add_warning(
            32,
            "financial",
            "Gift card or airtime payment involved",
            "The opportunity appears to request payment through gift cards, airtime, or vouchers.",
            "financial"
        )

    # 13. Easy employment
    if contains_any(lower, [
        "no experience needed",
        "no experience required",
        "anyone can do it",
        "anyone can apply",
        "easy job",
        "easy work",
        "work from home easily",
        "instant employment",
        "get hired immediately",
        "hired today",
        "start immediately"
    ]):
        add_warning(
            16,
            "employment",
            "Easy or immediate employment claim",
            "The opportunity appears to promise unusually easy or immediate employment.",
            "employment"
        )

    # 14. Fake official identity + payment
    if (
        contains_any(lower, [
            "government",
            "ministry",
            "county government",
            "police",
            "bank",
            "safaricom",
            "official"
        ])
        and
        contains_any(lower, [
            "pay",
            "fee",
            "deposit",
            "send money",
            "payment"
        ])
    ):
        add_warning(
            22,
            "identity",
            "Official identity combined with payment request",
            "The opportunity appears to use an official organisation or brand identity while also requesting money.",
            "identity"
        )

    # 15. Money forwarding
    if contains_any(lower, [
        "receive money and send it",
        "receive money then send",
        "forward money",
        "transfer money for us",
        "receive payments for us",
        "use your account to receive",
        "money transfer job",
        "cash transfer job"
    ]):
        add_warning(
            35,
            "financial",
            "Money transfer activity requested",
            "The opportunity appears to ask you to receive, transfer, or forward money on someone else's behalf.",
            "financial"
        )

    # 16. Credentials
    if contains_any(lower, [
        "login details",
        "login credentials",
        "username and password",
        "account password",
        "email password",
        "social media password",
        "give us access to your account"
    ]):
        add_warning(
            45,
            "security",
            "Account credentials requested",
            "The opportunity appears to request login credentials or access to an account.",
            "security"
        )

    # 17. Personal payment account
    if contains_any(lower, [
        "send to my mpesa",
        "send to my m-pesa",
        "pay my mpesa",
        "pay my m-pesa",
        "send money to my number",
        "send payment to my number",
        "send to my personal account",
        "pay me directly"
    ]):
        add_warning(
            30,
            "financial",
            "Personal payment account requested",
            "The opportunity appears to request payment to a personal account or mobile-money number.",
            "financial"
        )

    # -----------------------------
    # COMBINATION WARNINGS
    # -----------------------------

    financial = "financial" in categories
    recruitment = "recruitment" in categories
    earnings = "earnings" in categories
    pressure = "pressure" in categories
    security = "security" in categories
    communication = "communication" in categories

    if financial and recruitment:
        add_warning(
            12,
            "combination",
            "Payment and recruitment warnings combined",
            "Payment requests combined with recruitment activity create an additional warning pattern.",
            "combination"
        )

    if financial and earnings:
        add_warning(
            12,
            "combination",
            "Payment and earnings warnings combined",
            "Money is requested while the opportunity also promotes earnings.",
            "combination"
        )

    if financial and pressure:
        add_warning(
            12,
            "combination",
            "Payment and urgency warnings combined",
            "A payment request combined with pressure to act quickly increases the concern.",
            "combination"
        )

    if security and financial:
        add_warning(
            12,
            "combination",
            "Financial and security warnings combined",
            "The opportunity involves both money-related and sensitive security concerns.",
            "combination"
        )

    if financial and communication:
        add_warning(
            8,
            "combination",
            "Payment and off-platform messaging combined",
            "A payment request combined with off-platform recruitment creates an additional warning pattern.",
            "combination"
        )

    if len(categories) >= 3:
        add_warning(
            8,
            "combination",
            "Multiple warning categories detected",
            "Several different warning categories were detected in the same opportunity.",
            "combination"
        )

    score = min(max(score, 0), 100)

    return {
        "score": score,
        "signals": signals,
        "categories": categories
    }


# -----------------------------
# RISK INTELLIGENCE
# -----------------------------

def calculate_risk(score, signals=None, categories=None):
    signals = signals or []
    categories = categories or []

    if score >= 60:
        level = "HIGH RISK"
        css_class = "high"

        important = [
            signal["title"]
            for signal in signals
            if signal.get("title")
        ][:3]

        if important:
            explanation = (
                "This score was driven by warning signs including "
                + ", ".join(important)
                + "."
            )
        else:
            explanation = (
                "Several significant warning patterns were detected."
            )

        message = (
            "Do not send money or sensitive information until independently verified."
        )

        action = (
            "Stop and independently verify the employer, website, "
            "payment request, and contact details before proceeding."
        )

    elif score >= 25:
        level = "CAUTION"
        css_class = "medium"

        count = len(signals)

        if count == 1:
            explanation = "One warning pattern was detected."
        else:
            explanation = (
                f"{count} warning patterns were detected across "
                f"{len(categories)} category or categories."
            )

        message = (
            "Some warning signs were detected. Verify the opportunity "
            "independently before proceeding."
        )

        action = (
            "Pause before applying, paying, or sharing sensitive information. "
            "Verify the opportunity using independent sources."
        )

    else:
        level = "NO OBVIOUS WARNING SIGNS"
        css_class = "low"

        explanation = (
            "No major warning pattern was detected in the information provided."
        )

        message = (
            "No major warning pattern was detected. "
            "This is not proof that the opportunity is legitimate."
        )

        action = (
            "You may continue researching the opportunity, but independently "
            "verify the employer before sharing money or sensitive information."
        )

    return {
        "level": level,
        "class": css_class,
        "message": message,
        "explanation": explanation,
        "action": action
    }


# -----------------------------
# TITLE PARSER
# -----------------------------

class TitleParser:

    @staticmethod
    def extract(html):
        if not html:
            return ""

        match = re.search(
            r"<title[^>]*>(.*?)</title>",
            html,
            re.IGNORECASE | re.DOTALL
        )

        if match:
            title = re.sub(r"<.*?>", "", match.group(1))
            return clean_text(title)

        return ""


# -----------------------------
# WEBSITE INSPECTION
# -----------------------------

def inspect_website(url):
    signals = []
    title = ""
    status = "unknown"

    parsed = urlparse(url)

    hostname = parsed.hostname or ""
    lower_host = hostname.lower()

    # Domain checks
    if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", hostname):
        add_signal(
            signals,
            "website",
            "Website uses an IP address",
            "The link uses a raw IP address instead of a normal domain name."
        )

    if len(hostname) > 45:
        add_signal(
            signals,
            "website",
            "Unusually long website address",
            "The website hostname is unusually long and should be independently checked."
        )

    if "xn--" in lower_host:
        add_signal(
            signals,
            "website",
            "Punycode domain detected",
            "The domain uses Punycode, which can sometimes make look-alike domains harder to recognize."
        )

    if parsed.scheme.lower() != "https":
        add_signal(
            signals,
            "website",
            "Website is not using HTTPS",
            "The supplied website does not use HTTPS."
        )

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "GigLenn/7.0 Website Inspector"
            }
        )

        with urllib.request.urlopen(request, timeout=8) as response:
            status = response.status
            content_type = response.headers.get(
                "Content-Type",
                ""
            )

            raw = response.read(300000)

            try:
                html = raw.decode(
                    "utf-8",
                    errors="ignore"
                )
            except Exception:
                html = ""

            title = TitleParser.extract(html)

            if status >= 400:
                add_signal(
                    signals,
                    "website",
                    "Website returned an error",
                    f"The website returned HTTP status {status}."
                )

            if not title:
                add_signal(
                    signals,
                    "website",
                    "Website has no clear page title",
                    "The page did not provide a clear HTML title."
                )

            page_text = clean_text(
                re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
            )

            page_text = clean_text(
                re.sub(r"<style.*?</style>", " ", page_text, flags=re.I | re.S)
            )

            website_analysis = analyze_text(page_text)

            for signal in website_analysis["signals"]:
                add_signal(
                    signals,
                    "website",
                    signal["title"],
                    signal["detail"]
                )

    except Exception as exc:
        add_signal(
            signals,
            "website",
            "Website could not be fully inspected",
            "The website could not be reached or inspected automatically."
        )

        status = "unreachable"

    return {
        "url": url,
        "title": title,
        "status": status,
        "signals": signals
    }


# -----------------------------
# HTTP HELPERS
# -----------------------------

def send_json(handler, status_code, data):
    body = json.dumps(
        data,
        ensure_ascii=False
    ).encode("utf-8")

    handler.send_response(status_code)

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Access-Control-Allow-Origin",
        "*"
    )

    handler.send_header(
        "Access-Control-Allow-Methods",
        "GET, POST, PATCH, DELETE, OPTIONS"
    )

    handler.send_header(
        "Access-Control-Allow-Headers",
        "Content-Type"
    )

    handler.send_header(
        "Content-Length",
        str(len(body))
    )

    handler.end_headers()
    handler.wfile.write(body)


def read_json(handler):
    try:
        length = int(
            handler.headers.get(
                "Content-Length",
                "0"
            )
        )

        raw = handler.rfile.read(length)

        if not raw:
            return {}

        return json.loads(
            raw.decode("utf-8")
        )

    except Exception:
        return {}


# -----------------------------
# REQUEST HANDLER
# -----------------------------

class GigLennHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(
            "%s - %s"
            % (
                self.address_string(),
                format % args
            )
        )

    def do_OPTIONS(self):
        self.send_response(204)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, PATCH, DELETE, OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type"
        )

        self.end_headers()

    # -------------------------
    # GET
    # -------------------------

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Root
        if path == "/":
            send_json(
                self,
                200,
                {
                    "name": "GigLenn",
                    "version": VERSION,
                    "status": "online",
                    "riskIntelligence": True,
                    "smartAnalysis": True,
                    "websiteInspection": True
                }
            )
            return

        # Text analysis
        if path == "/analyze":
            text = query.get(
                "text",
                [""]
            )[0]

            analysis = analyze_text(text)

            risk = calculate_risk(
                analysis["score"],
                analysis["signals"],
                analysis["categories"]
            )

            send_json(
                self,
                200,
                {
                    "analysis": analysis,
                    "risk": risk
                }
            )
            return

        # Website check
        if path == "/check":
            url = query.get(
                "url",
                [""]
            )[0].strip()

            if not url:
                send_json(
                    self,
                    400,
                    {
                        "error": "URL is required"
                    }
                )
                return

            if not re.match(
                r"^https?://",
                url,
                re.IGNORECASE
            ):
                url = "https://" + url

            website = inspect_website(url)

            website_text_parts = [
                website.get("title", "")
            ]

            for signal in website["signals"]:
                website_text_parts.append(
                    signal.get("title", "")
                )
                website_text_parts.append(
                    signal.get("detail", "")
                )

            combined_text = clean_text(
                " ".join(website_text_parts)
            )

            analysis = analyze_text(
                combined_text
            )

            for signal in website["signals"]:
                add_signal(
                    analysis["signals"],
                    "website",
                    signal["title"],
                    signal["detail"]
                )

                if signal["title"]:
                    if signal["title"] not in analysis["categories"]:
                        analysis["categories"].append("website")

            # Website signals add modest extra weight.
            high_signal_titles = {
                "Website uses an IP address",
                "Punycode domain detected",
                "Website returned an error"
            }

            caution_signal_titles = {
                "Unusually long website address",
                "Website is not using HTTPS",
                "Website has no clear page title",
                "Website could not be fully inspected"
            }

            for signal in website["signals"]:
                if signal["title"] in high_signal_titles:
                    analysis["score"] += 15
                elif signal["title"] in caution_signal_titles:
                    analysis["score"] += 6

            analysis["score"] = min(
                max(analysis["score"], 0),
                100
            )

            risk = calculate_risk(
                analysis["score"],
                analysis["signals"],
                analysis["categories"]
            )

            send_json(
                self,
                200,
                {
                    "website": website,
                    "analysis": analysis,
                    "risk": risk
                }
            )
            return

        # Reports
        if path == "/reports":
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row

            rows = conn.execute("""
                SELECT *
                FROM reports
                ORDER BY id DESC
            """).fetchall()

            conn.close()

            reports = [
                dict(row)
                for row in rows
            ]

            send_json(
                self,
                200,
                {
                    "reports": reports
                }
            )
            return

        send_json(
            self,
            404,
            {
                "error": "Not found"
            }
        )

    # -------------------------
    # POST
    # -------------------------

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path != "/reports":
            send_json(
                self,
                404,
                {
                    "error": "Not found"
                }
            )
            return

        data = read_json(self)

        company = clean_text(
            data.get("company", "")
        )

        link = clean_text(
            data.get("link", "")
        )

        source = clean_text(
            data.get("source", "")
        )

        payment = clean_text(
            data.get("payment", "")
        )

        amount = clean_text(
            data.get("amount", "")
        )

        details = clean_text(
            data.get("details", "")
        )

        email = clean_text(
            data.get("email", "")
        )

        conn = sqlite3.connect(DB_FILE)

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO reports
            (
                company,
                link,
                source,
                payment,
                amount,
                details,
                email,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (
            company,
            link,
            source,
            payment,
            amount,
            details,
            email
        ))

        report_id = cursor.lastrowid

        conn.commit()
        conn.close()

        send_json(
            self,
            201,
            {
                "success": True,
                "id": report_id
            }
        )

    # -------------------------
    # PATCH
    # -------------------------

    def do_PATCH(self):
        parsed = urlparse(self.path)

        match = re.match(
            r"^/reports/(\d+)$",
            parsed.path
        )

        if not match:
            send_json(
                self,
                404,
                {
                    "error": "Not found"
                }
            )
            return

        report_id = int(
            match.group(1)
        )

        data = read_json(self)

        status = clean_text(
            data.get("status", "")
        )

        allowed_statuses = {
            "pending",
            "reviewing",
            "verified",
            "rejected"
        }

        if status not in allowed_statuses:
            send_json(
                self,
                400,
                {
                    "error": "Invalid status"
                }
            )
            return

        conn = sqlite3.connect(DB_FILE)

        cursor = conn.cursor()

        cursor.execute("""
            UPDATE reports
            SET status = ?
            WHERE id = ?
        """, (
            status,
            report_id
        ))

        updated = cursor.rowcount

        conn.commit()
        conn.close()

        if not updated:
            send_json(
                self,
                404,
                {
                    "error": "Report not found"
                }
            )
            return

        send_json(
            self,
            200,
            {
                "success": True
            }
        )

    # -------------------------
    # DELETE
    # -------------------------

    def do_DELETE(self):
        parsed = urlparse(self.path)

        if parsed.path == "/reports":
            conn = sqlite3.connect(DB_FILE)

            conn.execute(
                "DELETE FROM reports"
            )

            conn.commit()
            conn.close()

            send_json(
                self,
                200,
                {
                    "success": True
                }
            )
            return

        match = re.match(
            r"^/reports/(\d+)$",
            parsed.path
        )

        if match:
            report_id = int(
                match.group(1)
            )

            conn = sqlite3.connect(DB_FILE)

            cursor = conn.cursor()

            cursor.execute(
                "DELETE FROM reports WHERE id = ?",
                (report_id,)
            )

            deleted = cursor.rowcount

            conn.commit()
            conn.close()

            if not deleted:
                send_json(
                    self,
                    404,
                    {
                        "error": "Report not found"
                    }
                )
                return

            send_json(
                self,
                200,
                {
                    "success": True
                }
            )
            return

        send_json(
            self,
            404,
            {
                "error": "Not found"
            }
        )


# -----------------------------
# START SERVER
# -----------------------------

if __name__ == "__main__":
    init_db()

    print()
    print("GigLenn Backend v7.0")
    print("Status: ONLINE")
    print("Database: SQLite")
    print("Smart Analysis: ENABLED")
    print("Risk Intelligence: ENABLED")
    print("Website Inspection: ENABLED")
    print("Server: http://localhost:3000")
    print()

    server = HTTPServer(
        (HOST, PORT),
        GigLennHandler
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("GigLenn backend stopped.")
        server.server_close()
