# SARJAK Pipeline Commands

Run these commands from the folder that contains the deployed `csv/` folder.
The location of that parent folder does not matter. Every project path starts
with `csv/`.

## Configuration

The runtime loads `csv/info.txt`. The current database
configuration uses SQL Server `10.1.0.6` for ICMS lookups, email polling,
completion updates, and movement inserts.

Create `csv/info.txt` from `csv/info.example.txt` and replace the credential
placeholders during production deployment. `csv/info.txt` is intentionally
excluded from Git because it contains secrets.

## Create the Python environment

```bash
python3.14 -m venv csv/.venv
source csv/.venv/bin/activate
python -m pip install --upgrade pip
pip install -r csv/code/requirements.txt
python -c "import openpyxl, xlrd, et_xmlfile; print('dependencies OK')"
sqlcmd -? >/dev/null 2>&1 && echo "sqlcmd OK"
```

Dependencies are installed into `csv/.venv` during production setup. The
runtime does not use or assume a fixed package-installation path.

## Manual runs

```bash
source csv/.venv/bin/activate

# Poll continuously for pending emails and download matching attachments.
python csv/code/api/processor.py

# Process one email by internet message ID.
python csv/code/api/processor.py "<message-id>"

# Process csv/files/api without database inserts.
python csv/code/pipeline.py

# Process csv/files/api, insert movement records, and mark emails complete.
python csv/code/pipeline.py --insert

# Process explicit files or folders inside the project.
python csv/code/pipeline.py csv/files/api --insert
```

Runtime output is created below `csv/files/`:

```text
csv/files/
|-- api/
|-- processed/<timestamp>/
|-- extraction/<timestamp>/
`-- results/<timestamp>/
```

## PM2 deployment

Start PM2 from the folder that contains `csv/`.

```bash
VENV_PY=csv/.venv/bin/python

pm2 start "$VENV_PY" \
  --name sarjak-api-poller \
  -- csv/code/api/processor.py

pm2 start "$VENV_PY" \
  --name sarjak-pipeline \
  --no-autorestart \
  --cron "0 * * * *" \
  -- csv/code/pipeline.py --insert

pm2 save
pm2 startup
```

## PM2 operations

```bash
pm2 status
pm2 logs sarjak-api-poller
pm2 logs sarjak-pipeline
pm2 restart sarjak-api-poller
pm2 restart sarjak-pipeline
pm2 stop all
pm2 delete all
```
