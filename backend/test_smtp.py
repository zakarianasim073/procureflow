import os, sys, smtplib
from email.mime.text import MIMEText

# Load from .env
host = os.getenv("SMTP_HOST", "smtp.gmail.com")
port = int(os.getenv("SMTP_PORT", "587"))
user = os.getenv("SMTP_USER", "himel09073@gmail.com")
passwd = "btvxktjwepxtmwtn"
to = os.getenv("ALERT_EMAIL", "z.nasim073@gmail.com")

print(f"Testing SMTP...")
print(f"  Host: {host}:{port}")
print(f"  User: {user}")
print(f"  To:   {to}")
print(f"  Pass: {'set (%d chars)' % len(passwd)}")
print()

msg = MIMEText(
    "<html><body>"
    "<h2>Procurement Flow — SMTP Test</h2>"
    "<p>Your Gmail App Password is working!</p>"
    "<p>You will now receive BWDB tender alerts and reports automatically.</p>"
    "<hr><p style='color:#666;font-size:12px'>Procurement Flow Specialist BD</p>"
    "</body></html>",
    "html",
)
msg["Subject"] = "Procurement Flow — Gmail SMTP Configured Successfully"
msg["From"] = f"Procurement Flow <{user}>"
msg["To"] = to

try:
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, passwd)
        server.send_message(msg)
    print("OK: Test email sent to", to)
    print("Check your inbox at", to)
except smtplib.SMTPAuthenticationError:
    print("FAIL: Authentication error. App Password may be wrong or not yet activated.")
    print("Wait a few minutes and try again. If it persists, generate a new one at")
    print("https://myaccount.google.com/apppasswords")
except Exception as e:
    print(f"FAIL: {e}")
