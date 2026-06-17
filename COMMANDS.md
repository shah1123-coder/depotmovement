# Depot File Extraction — Setup & Run Commands (Ubuntu 22.04, Python 3.10, venv)

All commands are run from the repository root (the `csv/` folder). No Docker.

---

## 1. System packages

```bash
sudo apt-get update
sudo apt-get install -y python3.10 python3.10-venv python3-pip curl
```

## 2. Install Microsoft `sqlcmd` (mssql-tools18)

All database access goes through the `sqlcmd` CLI.

```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo tee /etc/apt/trusted.gpg.d/microsoft.asc
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y mssql-tools18 unixodbc-dev
echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> ~/.bashrc
source ~/.bashrc
sqlcmd -?    # must print usage
```

> If the binary is `sqlcmd18` or installed elsewhere, set `SQLCMD_PATH` in `info.txt`
> to its absolute path (e.g. `/opt/mssql-tools18/bin/sqlcmd`).

## 3. Get the code

```bash
cd ~
# copy or clone the project so that ~/csv contains code/, depot_report/, files/, info.txt
cd csv
```

## 4. Python virtual environment + dependencies

```bash
cd csv
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r code/requirements.txt
python -c "import openpyxl, xlrd, et_xmlfile; print('Python dependencies OK')"
```

## 5. Configuration (`csv/info.txt`)

Confirm `info.txt` at the repo root holds the correct values (env vars in the real
environment override these). Current settings:

```text
ICMS_SERVER=10.1.0.6
ICMS_DATABASE=ICMS
ICMS_USER=icms_AI_ro
ICMS_PASSWORD=AI@iCMS@RO

MAIL_DB_SERVER=10.1.0.6
MAIL_DB_USER=icms_AI_ro
MAIL_DB_PASSWORD=AI@iCMS@RO
PROCESS_EMAIL_DATABASE=EMail_Reader_Process_Data

SQLCMD_PATH=sqlcmd
```

> All `sqlcmd` calls already pass `-C` (trust server certificate). Leave
> `*_USER`/`*_PASSWORD` blank only if you want integrated auth (`-E`).

## 6. Verify DB connectivity

```bash
sqlcmd -S 10.1.0.6 -d ICMS -U icms_AI_ro -P 'AI@iCMS@RO' -C -Q "SELECT 'CONNECTED';" -W -h -1 -l 15
```

## 7. Smoke-test the CLIs

```bash
cd csv
source .venv/bin/activate
python code/pipeline.py --help
python code/extract.py --help
python code/converter.py --help
```

## 8. Run

```bash
cd csv
source .venv/bin/activate

# (optional) pull attachments into files/api/ for one internet message id
python code/api/processor.py "<internet-message-id>"

# extract + report only (NO database writes)
python code/pipeline.py

# extract + report + insert valid + errors + mark emails complete
python code/pipeline.py --insert

# process explicit files / a folder
python code/pipeline.py path/to/workbook.xlsx
python code/pipeline.py path/to/input-directory --insert

# tune header sensitivity (min consecutive text cells for a header)
python code/pipeline.py --min-cells 4
```

## 9. Outputs

```text
files/
├── processed/<YYYY-MM-DD_HH-MM-SS>/      # copies of the input workbooks
├── extraction/<YYYY-MM-DD_HH-MM-SS>/     # intermediate per-table .xlsx
└── results/<YYYY-MM-DD_HH-MM-SS>/
    ├── IN/ OUT/                          # routed Gate-In / Gate-Out tables
    ├── in.txt  out.txt
    ├── gate_in.json  gate_out.json  gate_errors.json
```

## 10. Run the email intake on a schedule (optional)

```bash
cd csv
source .venv/bin/activate
python code/api/processor.py        # polls pending VISHNU_DEPOT emails every hour
```

## 11. Run everything under PM2 (process manager)

PM2 keeps the hourly email-intake daemon alive and runs the pipeline on a
schedule. The key is pointing PM2 at the **venv interpreter** and the **repo
root** as the working directory. Replace `$HOME/csv` if your path differs.

```bash
# install Node + PM2 once
sudo apt-get install -y nodejs npm
sudo npm install -g pm2

# 1) email-intake daemon (long-running; processor.py already loops every hour)
pm2 start code/api/processor.py \
  --name depot-intake \
  --interpreter $HOME/csv/.venv/bin/python \
  --cwd $HOME/csv

# 2) extraction pipeline with DB inserts (one-shot, re-run every 30 min via cron)
pm2 start code/pipeline.py \
  --name depot-pipeline \
  --interpreter $HOME/csv/.venv/bin/python \
  --cwd $HOME/csv \
  --no-autorestart \
  --cron-restart "*/30 * * * *" \
  -- --insert

# 3) persist across reboots
pm2 save
pm2 startup        # then run the sudo command it prints

# manage / observe
pm2 status
pm2 logs depot-intake
pm2 logs depot-pipeline
pm2 restart depot-intake
pm2 stop depot-pipeline
pm2 delete depot-pipeline
```

> `--interpreter .../.venv/bin/python` makes PM2 use the virtualenv (no
> `source activate` needed). `--cwd $HOME/csv` ensures all relative paths
> (`info.txt`, `files/`, `code/`) resolve. For the one-shot pipeline,
> `--no-autorestart` + `--cron-restart` means "run once on each cron tick"
> instead of restarting in a tight loop.
