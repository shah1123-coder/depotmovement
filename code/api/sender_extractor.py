import urllib.request
import urllib.parse
import re
import html
import json

def extract_original_sender_domain(json_response):
    try:
        data = json.loads(json_response)
        html_body = data.get("body_content", "")
    except:
        html_body = json_response

    raw_text = html.unescape(html_body)
    email_pattern = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
    
    # Strip HTML tags
    clean_text = re.sub(r'<[^>]+>', ' ', raw_text)
    
    # Look for "From:" headers (common in forwarded emails)
    from_matches = re.findall(r'From\s*:\s*(.*?)(?:\r|\n|Sent:|To:|Subject:|$)', clean_text, re.IGNORECASE | re.DOTALL)
    
    found_emails = []
    for match in from_matches:
        emails = re.findall(email_pattern, match)
        found_emails.extend(emails)
    
    sender_email = "Not Found"
    if found_emails:
        # The deepest "From:" usually corresponds to the original sender
        sender_email = found_emails[-1] 
    else:
        # Fallback: scan the entire body for any email address
        all_emails = re.findall(email_pattern, clean_text)
        if all_emails:
            # Heuristic: Prefer external emails over internal ones if it's a forward
            for email in all_emails:
                if "sarjak.com" not in email.lower():
                    sender_email = email
                    break
            if sender_email == "Not Found":
                sender_email = all_emails[0]
    
    # Strip everything before the @ sign
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
    except:
        pass
    return "Error/Not Found"

if __name__ == "__main__":
    import sys
    test_id = "<SL2P216MB137530AF8528AA6583E7BF2AA1112@SL2P216MB1375.KORP216.PROD.OUTLOOK.COM>"
    if len(sys.argv) > 1:
        test_id = sys.argv[1]
    print(f"Original Sender Domain: {get_sender_domain_for_id(test_id)}")
