# Sender Email Classification

## Purpose

This is not an API module. It describes a simple classification helper that receives:

- `sender_email`
- `file_attachment`

and classifies the sender into a depot `PortId`.

## Inputs

```python
sender_email = "example@depot.com"
file_attachment = "report.xlsx"
```

The attachment is accepted as part of the input workflow, but the current classification key is the sender email.

## Classification Logic

1. Normalize the sender email by trimming whitespace and converting it to lowercase.
2. If the sender value contains `@`, keep only the domain-style portion starting at `@`.
3. Query `dbo.LocationContacts` using the normalized sender value.
4. Join `dbo.PortDetails` through `PortId`.
5. Return the matched `PortId`.
6. Rename the classified attachment to `PortId.fileattachment_extension`.
7. Return no classification when no active contact record matches.

## SQL Logic

```sql
SELECT pd.PortId
FROM dbo.PortDetails pd
INNER JOIN dbo.LocationContacts lc ON pd.PortId = lc.PortId
WHERE lc.DepotContactEmail = ?
  AND lc.IsDeleted = 0
```

## Expected Result Shape

```python
{
    "sender_email": sender_email,
    "file_attachment": file_attachment,
    "port_id": port_id,
    "renamed_file": f"{port_id}{Path(file_attachment).suffix.lower()}",
    "matched": bool(port_id),
}
```

## Rename Rule

If the sender email resolves to `PortId = 123` and the input attachment is:

```python
file_attachment = "daily-report.xlsx"
```

the classified file should be renamed to:

```python
123.xlsx
```

## Notes

- The API module currently resolves sender email to depot name.
- This classification version should resolve sender email to depot `PortId`.
- The attachment filename is retained for workflow context and supplies the output file extension.
