import subprocess
import urllib.request
import urllib.parse
import json
import base64
import time
from pathlib import Path
import sys

# Import sender extraction logic
# We add the directory to sys.path to ensure we can import it
sys.path.append(str(Path(__file__).parent))
from sender_extractor import extract_original_sender_domain

# Paths
CSV_ROOT = Path(__file__).resolve().parents[2]
ATTACHMENT_DIR = CSV_ROOT / "files" / "api"
SQL_QUERY = """
SELECT DISTINCT [internet_message_id]
FROM [10.1.0.6].[EMail_Reader_Process_Data].[dbo].[tbl_Process_Emails]
WHERE [completed_at] IS NULL
  AND [Process] = 'VISHNU_DEPOT'
  AND NULLIF(LTRIM(RTRIM([internet_message_id])), '') IS NOT NULL
"""
POLL_SECONDS = 60 * 60

def get_message_ids():
    cmd = [
        "sqlcmd", "-S", "10.1.0.6", "-U", "icms_AI_ro", "-P", "AI@iCMS@RO",
        "-Q", SQL_QUERY, "-W", "-h", "-1"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return ids
    except Exception as e:
        print(f"Error fetching IDs from database: {e}")
        return []

def get_depot_info(sender_domain):
    """
    Finds PortName and PortId from the sender domain.
    """
    safe_domain = sender_domain.replace("'", "''")
    sql = f"SELECT pd.PortId, pd.PortName FROM dbo.PortDetails pd INNER JOIN dbo.LocationContacts lc ON pd.PortId = lc.PortId WHERE lc.DepotContactEmail = '{safe_domain}' AND lc.IsDeleted = 0"
    cmd = [
        "sqlcmd", "-S", "10.1.0.6", "-U", "icms_AI_ro", "-P", "AI@iCMS@RO",
        "-Q", sql, "-W", "-h", "-1"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip().split()
        if len(output) >= 2:
            port_id = output[0]
            port_name = " ".join(output[1:])
            return port_id, port_name
    except Exception as e:
        print(f"  - Depot Info Error: {e}")
    return None, "Not Found"

def should_process_attachment(filename):
    """
    Modular filter: Ignore ARCON, process SARJAK.
    """
    fn_upper = filename.upper()
    if "ARCON" in fn_upper:
        return False
    if "SARJAK" in fn_upper:
        return True
    return False

def save_base64_file(content_bytes_b64, target_path):
    try:
        file_data = base64.b64decode(content_bytes_b64)
        with open(target_path, 'wb') as f:
            f.write(file_data)
        return True
    except Exception as e:
        print(f"Error decoding/saving file: {e}")
        return False

def message_id_path(attachment_path):
    return attachment_path.with_name(f"{attachment_path.name}.message-id")

def get_body_preview(message_id):
    """
    Fetches the body_preview text for an email directly from tbl_Process_Emails.
    """
    safe_id = message_id.replace("'", "''")
    sql = (
        f"SELECT [body_preview] "
        f"FROM [10.1.0.6].[EMail_Reader_Process_Data].[dbo].[tbl_Process_Emails] "
        f"WHERE [internet_message_id] = '{safe_id}'"
    )
    cmd = [
        "sqlcmd", "-S", "10.1.0.6", "-U", "icms_AI_ro", "-P", "AI@iCMS@RO",
        "-Q", sql, "-W", "-h", "-1"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"  - Body Preview Error: {e}")
        return ""

def process_id(message_id):
    encoded_id = urllib.parse.quote(message_id)
    # html_url = f"https://mail-reader.sarjak.com/api/attachment/internet-id/{encoded_id}/html"
    attachments_url = f"https://mail-reader.sarjak.com/api/attachment/internet-id/{encoded_id}/external-attachments"

    print(f"Processing: {message_id}")

    # 1. Sender Domain Extraction from the body_preview column (not the HTML API).
    sender_domain = "Not Found"
    port_id, port_name = None, "Not Found"
    try:
        # --- Old approach: parse the HTML API body to find the original sender ---
        # with urllib.request.urlopen(html_url, timeout=15) as response:
        #     if response.status == 200:
        #         json_body = response.read().decode('utf-8', errors='ignore')
        #         sender_domain = extract_original_sender_domain(json_body)
        body_preview = get_body_preview(message_id)
        if body_preview:
            sender_domain = extract_original_sender_domain(body_preview)
            print(f"  - Original Sender Domain: {sender_domain}")
            if sender_domain != "Not Found":
                port_id, port_name = get_depot_info(sender_domain)
                print(f"  - Identified Depot: {port_name} (ID: {port_id})")
    except Exception as e:
        print(f"  - HTML API Error: {e}")

    # 2. External Attachments API
    try:
        with urllib.request.urlopen(attachments_url, timeout=15) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                attachments = data.get('attachments', []) if isinstance(data, dict) else []
                
                if attachments:
                    for i, att in enumerate(attachments):
                        original_name = att.get('name') or att.get('fileName') or "Unknown"
                        
                        if not should_process_attachment(original_name):
                            print(f"  - Skipping (Filter): {original_name}")
                            continue
                            
                        content_b64 = att.get('contentBytes')
                        if content_b64:
                            suffix = Path(original_name).suffix
                            base_name = str(port_id) if port_id else Path(original_name).stem
                            
                            ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
                            counter = 1
                            while True:
                                new_name = f"{base_name}_{counter}{suffix}"
                                target = ATTACHMENT_DIR / new_name
                                if not target.exists():
                                    break
                                counter += 1
                                
                            if save_base64_file(content_b64, target):
                                message_id_path(target).write_text(message_id, encoding="utf-8")
                                print(f"  - Saved attachment: {original_name} -> {new_name}")
                else:
                    print("  - No external attachments found.")
    except Exception as e:
        print(f"  - Attachments API Error: {e}")
    
    return sender_domain

def process_pending_ids():
    ids = get_message_ids()
    if not ids:
        print("No unprocessed IDs found in database.")
        return
    for mid in ids:
        try:
            process_id(mid)
        except Exception as e:
            print(f"Error processing {mid}: {e}")

if __name__ == "__main__":
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)

    # Check if a manual ID was provided as an argument
    if len(sys.argv) > 1:
        process_id(sys.argv[1])
    else:
        while True:
            try:
                process_pending_ids()
            except Exception as e:
                print(f"Poll cycle error: {e}")
            time.sleep(POLL_SECONDS)
