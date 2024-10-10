import validators
from db import get_db
from metrics import detect_device, get_client_ip, get_location, detect_browser_and_os
from flask import request


def is_valid_url(url):
    """Validate if the given content is a valid URL."""
    return validators.url(url)

def process_metrics(qr_code_id, user_agent):
    """Collect tracking information and save it to the database."""
    device = detect_device(user_agent)
    language = request.headers.get('Accept-Language', 'Unknown')
    ip_address = get_client_ip()
    referrer = request.headers.get('Referer', 'Direct Access')
    region = get_location(ip_address)
    browser, os = detect_browser_and_os(user_agent)

    db = get_db()
    db.execute('''INSERT INTO qr_code_tracking (qr_code_id, device_type, ip_address, region, browser, os, language, referrer)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
               (qr_code_id, device, ip_address, region, browser, os, language, referrer))
    db.commit()
    return device
