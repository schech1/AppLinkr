from flask import Flask, request
import requests
from user_agents import parse


### User Information
def get_client_ip():
    """Get the client IP address."""
    if 'X-Forwarded-For' in request.headers:
        ip_address = request.headers['X-Forwarded-For'].split(',')[0]
        print(ip_address, flush=True)
    else:
        ip_address = request.remote_addr
    return ip_address




def get_location(ip_address):
    """Get the approximate location of the user from their IP address."""
    try:
        response = requests.get(f'http://ipinfo.io/{ip_address}/json')
        data = response.json()
        return f"{data['city']}, {data['region']}, {data['country']}"
    except Exception as e:
        print(f"Error fetching location for IP {ip_address}: {e}")
        return "Unknown"
    


def detect_browser_and_os(user_agent):
    """Detect browser and operating system from User-Agent."""
    ua = parse(user_agent)
    browser = f"{ua.browser.family} {ua.browser.version_string}"
    os = f"{ua.os.family} {ua.os.version_string}"
    return browser, os


def detect_device(user_agent):
    """Detect the device based on the User-Agent string."""
    if "Android" in user_agent:
        return "android"
    elif "iPhone" in user_agent or "iPad" in user_agent:
        return "ios"
    else:
        return "unknown"