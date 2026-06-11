# SARJAK Email / Movement Pipeline — Ubuntu Deployment & Run Guide

## Assumptions on the server
- Project root : `/opt/sarjak/csv`   *(adjust to your real path)*
- Code dir     : `/opt/sarjak/csv/code`
- Wheels (deps): `/opt/sarjak/csv/dependencies`  *(the `.whl` files)*
- **Python 3.14** — the bundled `pyodbc` wheel is `cp314`, so Python 3.14 is required.

> Replace `/opt/sarjak/csv` everywhere below with your actual path.

### Folder layout that must be transferred
```
csv/
├── code/                 # this module (pipeline + api)
│   ├── api/              # processor.py, sender_extractor.py
│   ├── pipeline.py, extract.py, converter.py, movement.py,
│   │   in.py, out.py, database.py, countries/
│   ├── requirements.txt
│   └── commands.md
├── dependencies/         # offline .whl files
└── files/                # api/ processed/ extraction/ results/ (created at runtime)
```
> **Also required:** the sibling project **`depot report/`** must sit next to `csv/`
> (i.e. `<parent>/depot report/code/db/icms_client.py`). `in.py`, `out.py`, and
> `database.py` import `db.icms_client` from there via a relative `parents[2]` path.

---

## 1. System packages (one-time, needs sudo)
```bash
sudo apt-get update
sudo apt-get install -y python3.14 python3.14-venv unixodbc unixodbc-dev curl gnupg

# Microsoft ODBC Driver 17 + sqlcmd (mssql-tools) for SQL Server connectivity:
curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17 mssql-tools18 unixodbc-dev

# Put sqlcmd on PATH:
echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> ~/.bashrc
source ~/.bashrc

# Node + pm2 (process manager):
sudo apt-get install -y nodejs npm
sudo npm install -g pm2
```

## 2. Python virtualenv + offline dependency install
```bash
cd /opt/sarjak/csv/code
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

# Install ONLY from the local wheels folder (no internet):
pip install --no-index --find-links=/opt/sarjak/csv/dependencies -r requirements.txt

# Sanity check:
python -c "import openpyxl, xlrd, pyodbc, et_xmlfile; print('deps OK')"
sqlcmd -? >/dev/null 2>&1 && echo "sqlcmd OK"
```

## 3. Run with pm2
```bash
# Use the venv python explicitly so pm2 uses the right interpreter.
VENV_PY=/opt/sarjak/csv/code/.venv/bin/python

# (a) API poller — runs forever, fetches new emails + downloads attachments hourly:
pm2 start $VENV_PY \
    --name sarjak-api-poller \
    --cwd /opt/sarjak/csv/code/api \
    -- processor.py

# (b) Pipeline runner — converts/extracts/classifies and inserts into the DB.
#     Runs once then exits, scheduled hourly via pm2 cron (no autorestart loop):
pm2 start $VENV_PY \
    --name sarjak-pipeline \
    --cwd /opt/sarjak/csv/code \
    --no-autorestart \
    --cron "0 * * * *" \
    -- pipeline.py --insert

# Persist the process list and enable start-on-boot:
pm2 save
pm2 startup       # run the command it prints (with sudo) to enable boot startup
```

## 4. Useful pm2 management commands
```bash
pm2 status                       # list processes
pm2 logs sarjak-api-poller       # tail poller logs
pm2 logs sarjak-pipeline         # tail pipeline logs
pm2 restart sarjak-api-poller
pm2 restart sarjak-pipeline
pm2 stop all
pm2 delete all
```

## 5. Manual one-off runs (for testing)
```bash
source /opt/sarjak/csv/code/.venv/bin/activate
python pipeline.py                      # default input: ../files/api, no DB insert
python pipeline.py --insert             # insert valid + error payloads into the DB
python api/processor.py "<message-id>"  # process a single email by internet message id
```
