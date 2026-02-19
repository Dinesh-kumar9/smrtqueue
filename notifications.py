# notifications.py — HTML Email Sender
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import EMAIL_ADDRESS, EMAIL_PASSWORD


def send_email_html(to_email: str, subject: str, html_body: str):
    """Send a styled HTML email via Gmail SMTP."""
    if not to_email:
        return

    msg = MIMEMultipart('alternative')
    msg['From']    = f"SmartQueue <{EMAIL_ADDRESS}>"
    msg['To']      = to_email
    msg['Subject'] = subject

    # Wrap in full HTML document with base styles
    full_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:24px;background:#1e1b4b;font-family:Inter,Arial,sans-serif;">
  {html_body}
  <p style="text-align:center;color:#475569;font-size:0.75rem;margin-top:24px;">
    SmartQueue &mdash; Intelligent Queue Management
  </p>
</body>
</html>"""

    msg.attach(MIMEText(full_html, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()
        print(f"✅ Email sent to {to_email} | Subject: {subject}")
    except Exception as e:
        print(f"❌ Error sending email to {to_email}: {e}")


# Backwards-compatible alias
def send_email(to_email: str, subject: str, body: str):
    """Plain-text fallback (wraps in simple HTML)."""
    html = f"<div style='padding:20px;'><pre style='white-space:pre-wrap;color:#f1f5f9;'>{body}</pre></div>"
    send_email_html(to_email, subject, html)