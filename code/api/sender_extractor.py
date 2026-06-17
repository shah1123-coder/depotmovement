import urllib.request
import urllib.parse
import re
import html
import json


def extract_original_sender_domain(json_response):
    try:
        data = json.loads(json_response)
        html_body = data.get("body_content", "")
    except Exception:
        html_body = json_response

    clean_text = html.unescape(html_body)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

    all_emails = re.findall(email_pattern, clean_text)
    sender_email = all_emails[0] if all_emails else "Not Found"

    if sender_email != "Not Found" and "@" in sender_email:
        return "@" + sender_email.split("@")[-1]
    return "Not Found"


def get_sender_domain_for_id(message_id):
    encoded_id = urllib.parse.quote(message_id)
    html_url = f"https://mail-reader.sarjak.com/api/attachment/internet-id/{encoded_id}/html"
    try:
        with urllib.request.urlopen(html_url, timeout=15) as response:
            if response.status == 200:
                json_body = response.read().decode('utf-8', errors='ignore')
                return extract_original_sender_domain(json_body)
    except Exception:
        pass
    return "Error/Not Found"


if __name__ == "__main__":
    import sys
    test_id = "<SL2P216MB137530AF8528AA6583E7BF2AA1112@SL2P216MB1375.KORP216.PROD.OUTLOOK.COM>"
    if len(sys.argv) > 1:
        test_id = sys.argv[1]
    print(f"Original Sender Domain: {get_sender_domain_for_id(test_id)}")
