import os
import subprocess
import urllib.request
import urllib.parse
import json
import base64
import time
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent))
from sender_extractor import extract_original_sender_domain

CSV_ROOT = Path(__file__).resolve().parents[2]
ATTACHMENT_DIR = CSV_ROOT / "files" / "api"


def _load_env():
    env_path = CSV_ROOT / "info.txt"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env()

MAIL_DB_SERVER = os.environ.get("MAIL_DB_SERVER", "10.1.0.6")
MAIL_DB_USER = os.environ.get("MAIL_DB_USER", "")
MAIL_DB_PASSWORD = os.environ.get("MAIL_DB_PASSWORD", "")
MAIL_DB_DATABASE = os.environ.get("PROCESS_EMAIL_DATABASE", "EMail_Reader_Process_Data")
SQLCMD = os.environ.get("SQLCMD_PATH", "sqlcmd")
SQLCMD_BASE = [SQLCMD, "-S", MAIL_DB_SERVER, "-C"]
if MAIL_DB_USER and MAIL_DB_PASSWORD:
    SQLCMD_BASE += ["-U", MAIL_DB_USER, "-P", MAIL_DB_PASSWORD]
else:
    SQLCMD_BASE += ["-E"]

SQL_QUERY = f"""
SELECT DISTINCT [internet_message_id]
FROM [{MAIL_DB_SERVER}].[{MAIL_DB_DATABASE}].[dbo].[tbl_Process_Emails]
WHERE [completed_at] IS NULL
  AND [Process] = 'VISHNU_DEPOT'
  AND NULLIF(LTRIM(RTRIM([internet_message_id])), '') IS NOT NULL
"""
POLL_SECONDS = 60 * 60


def get_message_ids():
    cmd = SQLCMD_BASE + ["-Q", SQL_QUERY, "-W", "-h", "-1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except Exception as e:
        print(f"Error fetching IDs from database: {e}")
        return []


def get_depot_info(sender_domain):
    safe_domain = sender_domain.replace("'", "''")
    sql = (f"SELECT pd.PortId, pd.PortName FROM dbo.PortDetails pd "
           f"INNER JOIN dbo.LocationContacts lc ON pd.PortId = lc.PortId "
           f"WHERE lc.DepotContactEmail = '{safe_domain}' AND lc.IsDeleted = 0")
    cmd = SQLCMD_BASE + ["-Q", sql, "-W", "-h", "-1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.strip().split()
        if len(output) >= 2:
            return output[0], " ".join(output[1:])
    except Exception as e:
        print(f"  - Depot Info Error: {e}")
    return None, "Not Found"


def should_process_attachment(filename):
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
    safe_id = message_id.replace("'", "''")
    sql = (f"SELECT [body_preview] "
           f"FROM [{MAIL_DB_SERVER}].[{MAIL_DB_DATABASE}].[dbo].[tbl_Process_Emails] "
           f"WHERE [internet_message_id] = '{safe_id}'")
    cmd = SQLCMD_BASE + ["-Q", sql, "-W", "-h", "-1"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        print(f"  - Body Preview Error: {e}")
        return ""


def process_id(message_id):
    encoded_id = urllib.parse.quote(message_id)
    attachments_url = f"https://mail-reader.sarjak.com/api/attachment/internet-id/{encoded_id}/external-attachments"
    print(f"Processing: {message_id}")

    sender_domain = "Not Found"
    port_id, port_name = None, "Not Found"
    try:
        body_preview = get_body_preview(message_id)
        if body_preview:
            sender_domain = extract_original_sender_domain(body_preview)
            print(f"  - Original Sender Domain: {sender_domain}")
            if sender_domain != "Not Found":
                port_id, port_name = get_depot_info(sender_domain)
                print(f"  - Identified Depot: {port_name} (ID: {port_id})")
    except Exception as e:
        print(f"  - Sender Resolution Error: {e}")

    try:
        with urllib.request.urlopen(attachments_url, timeout=15) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                attachments = data.get('attachments', []) if isinstance(data, dict) else []
                if attachments:
                    for att in attachments:
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
    if len(sys.argv) > 1:
        process_id(sys.argv[1])
    else:
        while True:
            try:
                process_pending_ids()
            except Exception as e:
                print(f"Poll cycle error: {e}")
            time.sleep(POLL_SECONDS)
