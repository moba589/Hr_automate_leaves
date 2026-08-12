#!/usr/bin/env python3
import imaplib
import email
from email.header import decode_header
import json
import os
import sys
import urllib.request
import datetime

GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
INTAKE_URL         = os.environ["INTAKE_URL"]
INTAKE_SECRET      = os.environ["INTAKE_SECRET"]

LEAVE_KEYWORDS = [
    "leave", "chutti", "chhutti", "off day", "sick", "casual",
    "annual leave", "vacation", "rukhsat", "bimar"
]

def decode_str(raw):
    if raw is None:
        return ""
    parts = decode_header(raw)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="ignore")
        else:
            out += text
    return out

def get_plain_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                charset = part.get_content_charset() or "utf-8"
                return part.get_payload(decode=True).decode(charset, errors="ignore")
        return ""
    else:
        charset = msg.get_content_charset() or "utf-8"
        return msg.get_payload(decode=True).decode(charset, errors="ignore")

def looks_like_leave_request(subject, body):
    text = (subject + " " + body).lower()
    return any(kw in text for kw in LEAVE_KEYWORDS)

def push_to_intake(from_email, subject, body, message_id, received_at):
    payload = json.dumps({
        "key": INTAKE_SECRET,
        "from_email": from_email,
        "subject": subject[:250],
        "body": body[:4000],
        "message_id": message_id,
        "received_at": received_at,
    }).encode("utf-8")

    req = urllib.request.Request(
        INTAKE_URL, data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            print(f"  -> intake response: {resp.read().decode()}")
            return True
    except Exception as e:
        print(f"  -> FAILED to push to intake: {e}", file=sys.stderr)
        return False

def main():
    imap = imaplib.IMAP4_SSL("imap.gmail.com")
    imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    imap.select("INBOX")

    today_date = datetime.date.today().strftime("%d-%b-%Y")
    status, data = imap.search(None, f'(SINCE "{today_date}")')
    
    if status != "OK":
        print("IMAP search failed"); sys.exit(1)

    ids = data[0].split()
    print(f"Found {len(ids)} email(s) for today ({today_date})")

    for eid in ids:
        status, msg_data = imap.fetch(eid, "(RFC822)")
        if status != "OK":
            continue

        msg = email.message_from_bytes(msg_data[0][1])
        subject = decode_str(msg.get("Subject"))
        from_header = decode_str(msg.get("From"))
        
        from_email = email.utils.parseaddr(from_header)[1].lower()
        message_id = msg.get("Message-ID", f"noid-{eid.decode()}")
        received_at = msg.get("Date", "")
        body = get_plain_body(msg).strip()

        print(f"Checking: {from_email} | {subject}")

        if not looks_like_leave_request(subject, body):
            print("  -> skipped (no leave keyword match)")
            continue

        push_to_intake(from_email, subject, body, message_id, received_at)

    imap.close()
    imap.logout()

if __name__ == "__main__":
    main()
