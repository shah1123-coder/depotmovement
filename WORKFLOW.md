# Project Brief: Depot File Extraction Module — Logical Workflow Only

## Purpose

Create a depot file extraction module that can process depot report files received in Excel-based formats and extract container Gate-In and Gate-Out movement records from files where every depot may use a different layout, header style, sheet name, language, or column order.

The module must work without fixed templates by using language detection, regional classification, dynamic header detection, regex-based row identification, movement-direction classification, field extraction, record validation, and structured output generation.

---

## Core Objective

The system must take a depot report file, understand whether it belongs to India or China, identify the relevant Gate-In or Gate-Out data tables inside it, extract all valid container movement rows, normalize the extracted fields, validate the records, separate valid records from error records, and produce final structured outputs for downstream insertion and review.

---

## End-to-End Logical Workflow

### 1. Receive Depot Report File

* Accept depot report files in Excel-based formats such as `.xlsx`, `.xls`, encrypted Excel, or other Microsoft Excel-compatible formats.
* Treat each file as a depot movement report that may contain Gate-In records, Gate-Out records, or multiple sheets/tables.
* Do not assume any fixed sheet name, fixed header position, fixed column order, or fixed table layout.

---

### 2. Identify File Region

* Detect the language used in the depot report.
* If the workbook or sheet content is primarily English, classify it under the India region.
* If the workbook or sheet content contains Chinese text, classify it under the China region.
* Use the detected region to decide which regex rules, movement keywords, header markers, vehicle formats, booking fallbacks, and remark markers should be applied.

---

### 3. Load Region-Specific Extraction Rules

* Load the extraction configuration for the detected region.
* Use separate regex and marker definitions for India and China.
* Keep the logic modular so that additional regions can be added later without changing the core workflow.
* Ensure each region can define its own movement keywords, booking patterns, vehicle patterns, remark markers, sheet-name markers, and fallback extraction rules.

---

### 4. Identify Relevant Sheets

* Review every worksheet in the depot report.
* Ignore sheets that are clearly not movement sheets, such as monthly summary sheets, master sheets, or unrelated reference sheets.
* Always process explicitly allowed sheets such as generic operational sheets or known Gate-In/Gate-Out sheet names.
* Use sheet-name meaning, language, and movement keywords to decide whether the sheet may contain valid movement data.
* Reject sheets that are ambiguous when they appear to contain both Gate-In and Gate-Out indicators without enough clarity.
* Reject sheets that contain neither Gate-In nor Gate-Out indicators unless they are explicitly recognized as valid movement sheets.

---

### 5. Classify Sheet Movement Intent

* Determine whether each relevant sheet is related to Gate-In, Gate-Out, or unresolved movement.
* Check the sheet name for Gate-In indicators.
* Check the sheet name for Gate-Out indicators.
* For Chinese sheets, identify movement intent using Chinese movement markers.
* If only Gate-In is detected, classify the sheet as IN.
* If only Gate-Out is detected, classify the sheet as OUT.
* If both are detected, mark the sheet as ambiguous unless later table-level or workbook-level context resolves it.
* If neither is detected, rely on recognized sheet names or workbook-level fallback logic.

---

### 6. Normalize Merged Cells

* Detect merged cells inside each worksheet.
* Treat the top-left value of a merged range as the value for the full merged area.
* Ensure merged cells do not break header detection or row extraction.
* Convert merged and normal cells into a consistent logical cell structure.
* Preserve horizontal merge meaning where it helps reconstruct extracted tables.

---

### 7. Build Logical Rows

* Scan each worksheet row from left to right.
* Convert every visible cell or merged-cell block into a logical cell.
* Skip duplicate cells inside merged ranges so that the same merged value is not counted multiple times.
* Represent each logical cell with its start column, end column, row position, value, and merge span.
* Use these logical rows for header detection, title detection, table extraction, and row scanning.

---

### 8. Detect Header Rows Dynamically

* Search each worksheet from top to bottom for rows containing consecutive plain-text cells.
* Treat consecutive plain-text cells as a possible header run.
* A valid header run must contain enough consecutive header-like cells to represent a table.
* Do not treat numbers, dates, blank cells, formulas, or non-text cells as valid header cells.
* Allow different depots to use different header labels and different column orders.
* Avoid duplicate detection of stacked or multi-line headers by skipping immediately repeated header-like rows after one header is found.

---

### 9. Identify Table Title

* Look above each detected header row to find a nearby title row.
* Search a limited number of rows above the header.
* If a non-empty row exists above the header, treat it as the table title.
* Use the title only as contextual information, not as a required extraction dependency.
* If no title exists, use the sheet name as fallback context.

---

### 10. Define Table Boundaries

* Once a header row is detected, start reading data from the row immediately below it.
* Continue reading downward row by row.
* Stop when the first completely blank row is encountered.
* Limit the table horizontally to the detected header’s start and end columns.
* Do not extract unrelated content outside the detected table window.
* If multiple tables exist in a sheet, detect and process each table separately.

---

### 11. Detect Valid Container Rows

* For every row below the header, scan the row for a valid container number.
* A valid container number must match the standard pattern of four letters where the fourth character is `U`, `J`, or `Z`, followed by seven digits.
* Treat the container number as the main anchor for deciding whether a row is a movement record.
* Skip rows without a valid container number during final record extraction.
* Mark rows without valid container numbers as invalid in intermediate table outputs if required.
* Always normalize extracted container numbers to uppercase.

---

### 12. Extract Intermediate Tables

* For every detected table, extract the header and all rows up to the blank-row boundary.
* Preserve the table’s logical structure after clipping it to the detected header range.
* Add an error indicator for rows that do not contain valid container numbers.
* Save each extracted table as a clean intermediate movement table.
* Use these intermediate tables as the source for Gate-In and Gate-Out extraction.

---

### 13. Resolve Final Movement Direction

* Determine whether each extracted table represents Gate-In or Gate-Out.
* Use table filename or title first.
* If unresolved, use parent sheet or folder name.
* If still unresolved, use original workbook name.
* If exactly one movement direction is found across the workbook, apply that direction to all unresolved tables in that workbook.
* If movement direction remains ambiguous, do not force extraction into the wrong movement type.

---

### 14. Separate Gate-In and Gate-Out Tables

* Copy or route resolved Gate-In tables into the Gate-In processing flow.
* Copy or route resolved Gate-Out tables into the Gate-Out processing flow.
* Keep ambiguous or invalid tables out of final insertion flow.
* Ensure duplicate output names are handled safely so that no valid table overwrites another.

---

## Gate-In Logical Extraction Workflow

### 15. Process Gate-In Tables

* Load each resolved Gate-In table.
* Use the region-specific Gate-In extraction rules.
* Scan each row for a valid container number.
* Skip rows that do not contain a valid container number.
* Extract the first valid container number found in the row.
* Extract the first date found in the row.
* Extract the first time found in the row.
* Identify the remarks column using region-specific remark markers.
* Extract remarks from the detected remarks column if present.
* Extract or derive container status where available.
* Create one Gate-In record per valid container row.

---

### 16. Gate-In Field Requirements

Each Gate-In record should logically contain:

* Container number
* Gate-In date
* Gate-In time
* Remarks
* Container status
* Error code, if any

---

### 17. Gate-In Date and Time Handling

* Detect dates in numeric formats such as day-month-year, month-day-year, and year-month-day.
* Support separators such as slash, dot, hyphen, and space.
* Support textual month formats such as day-month-name-year and month-name-day-year.
* Normalize valid dates into a standard `YYYY-MM-DD` format.
* Detect time values in hour-minute, hour-minute-second, and AM/PM formats.
* Normalize valid time values into a standard time format.
* If parsing fails but a recognizable date or time string exists, preserve the raw detected value for review.

---

## Gate-Out Logical Extraction Workflow

### 18. Process Gate-Out Tables

* Load each resolved Gate-Out table.
* Use the region-specific Gate-Out extraction rules.
* Scan each row for a valid container number.
* Skip rows that do not contain a valid container number.
* Extract the container number from the row.
* Resolve the booking column using booking ID patterns, booking markers, or region-specific fallback rules.
* Extract booking ID from the resolved booking column.
* Extract seal number using seal-related header markers.
* Extract transporter using transporter-related header markers.
* Extract vehicle number using vehicle markers or vehicle regex fallback.
* Extract remarks using remark markers.
* Extract the last/rightmost date found in the row.
* Extract the last/rightmost time found in the row.
* Create one Gate-Out record per valid container row.

---

### 19. Gate-Out Field Requirements

Each Gate-Out record should logically contain:

* Container number or container ID
* Booking ID
* Seal number
* Plot-Out date
* Plot-Out time
* Transporter
* Vehicle number
* Remarks
* Error code, if any

---

### 20. Gate-Out Booking Logic

* First try to detect a booking column using the standard booking ID format.
* If no regex-based booking column is found, use region-specific booking header markers.
* If no marker-based booking column is found, apply regional fallback rules.
* For India, do not accept weak numeric fallbacks for booking unless they match the valid booking format.
* For China, allow six-digit numeric fallback booking references where applicable.
* If no valid booking ID is found for a Gate-Out row, mark the row with `NO_BOOKING_ID`.
* Preserve `NO_BOOKING_ID` during later validation rather than overwriting it with lower-priority errors.

---

### 21. Gate-Out Vehicle Logic

* Detect vehicle number from a dedicated vehicle column if such a column exists.
* For India, support Indian vehicle registration patterns.
* For China, support Chinese vehicle registration patterns using province-prefix logic.
* If no vehicle column exists, scan valid container rows for vehicle-like values.
* Leave vehicle number blank if no reliable vehicle value exists.

---

## Shared Normalization Workflow

### 22. Normalize Container Numbers

* Convert all extracted container numbers to uppercase.
* Remove unnecessary spacing where required.
* Accept only valid container-number formats.
* Treat invalid or missing container numbers as extraction errors.

---

### 23. Normalize Dates

* Accept dates from Excel date cells, text cells, or mixed-format cells.
* Convert recognized dates into `YYYY-MM-DD`.
* Support multiple international date formats because depot reports may not follow one standard.
* Preserve raw detected date text when parsing is uncertain.

---

### 24. Normalize Times

* Accept times from Excel time cells, text cells, or mixed-format cells.
* Convert recognized times into a standard time format.
* Support 24-hour time and AM/PM time.
* Preserve raw detected time text when parsing is uncertain.

---

### 25. Normalize Empty Values

* Convert blank cells and null values into empty strings.
* Do not treat blank optional fields as fatal errors.
* Treat blank mandatory fields as validation errors only when business rules require them.

---

## Validation Workflow

### 26. Validate Gate-In Records

* Check whether the extracted container exists in the container master.
* If the container does not exist, assign `NO_CONTAINER_ID`.
* Check whether the same container already has a Gate-In record for the same date.
* If a duplicate exists, assign `DUPLICATE_RECORD`.
* Check whether the container status is valid for Gate-In.
* If the status is invalid, assign `INVALID_CONTAINER_STATUS_ID`.
* Apply validation errors in priority order so that the most important error is assigned first.
* Attach relevant container status details where available.

---

### 27. Validate Gate-Out Records

* Preserve `NO_BOOKING_ID` if it was already assigned during extraction.
* Check whether the extracted container exists in the container master.
* If the container does not exist, assign `NO_CONTAINER_ID`.
* Check whether the same container, date, and booking already exist as a Gate-Out record.
* If a duplicate exists, assign `DUPLICATE_RECORD`.
* Check whether the booking quantity limit has been exceeded.
* If extracted Gate-Out quantity exceeds allowed booking quantity, assign `INVALID_ECP_COUNT`.
* Apply validation errors in priority order so that earlier critical errors are not overwritten incorrectly.

---

### 28. Validate Booking Quantities

* Resolve the booking ID for each Gate-Out record.
* Find the total booked quantity for the booking.
* Find how many containers have already been plotted out for the booking.
* Count how many containers are being extracted in the current run for the same booking.
* Ensure total plotted-out quantity does not exceed booked quantity.
* Mark records exceeding allowed quantity as `INVALID_ECP_COUNT`.

---

### 29. Validate Duplicates

* For Gate-In, detect duplicates using container and Gate-In date.
* For Gate-Out, detect duplicates using container, Gate-Out date, and booking ID.
* Do not insert duplicate movement records.
* Keep duplicate records visible in reports where required.
* Exclude duplicate records from operational error output if the final workflow treats duplicates as non-actionable.

---

### 30. Validate Depot Identity

* Derive the depot or plot identity from the incoming file context.
* Use the resolved depot identity to associate extracted movements with the correct depot.
* If depot identity cannot be resolved, allow extraction and reporting but prevent unsafe insertion of records that require a valid depot ID.
* Keep unresolved depot cases visible for review.

---

## Output Workflow

### 31. Generate Gate-In Output

* Create a structured Gate-In output containing all extracted Gate-In records.
* Include valid records and records with validation errors.
* Ensure each record carries all required movement fields.
* Include error codes where applicable.
* Prepare error-free records for downstream insertion.

---

### 32. Generate Gate-Out Output

* Create a structured Gate-Out output containing all extracted Gate-Out records.
* Include valid records and records with validation errors.
* Ensure each record carries all required movement fields.
* Include error codes where applicable.
* Prepare error-free records for downstream insertion.

---

### 33. Generate Error Output

* Collect all Gate-In and Gate-Out records with meaningful error codes.
* Add movement type to each error record.
* Exclude duplicate records from error output if duplicates are intentionally treated as already-existing rather than actionable failures.
* Ensure every failed record includes enough context for operations teams to review and correct it.

---

### 34. Generate Human-Readable Reports

* Create readable Gate-In and Gate-Out summaries.
* Group records by depot where applicable.
* Show extracted fields in aligned columns.
* Show `(none)` when no records exist.
* Include error codes beside records that failed validation.

---

### 35. Generate Structured JSON Outputs

* Generate a Gate-In JSON output for Gate-In movement records.
* Generate a Gate-Out JSON output for Gate-Out movement records.
* Generate a Gate-Errors JSON output for failed movement records.
* Ensure all JSON outputs are clean, predictable, and ready for downstream processing.

---

## Persistence Workflow

### 36. Insert Valid Gate-In Records

* Insert only Gate-In records that have no blocking errors.
* Insert only records with a valid depot or plot identity.
* Do not insert records with missing container IDs.
* Do not insert duplicate records.
* Preserve remarks and movement date information during insertion.

---

### 37. Insert Valid Gate-Out Records

* Insert only Gate-Out records that have no blocking errors.
* Insert only records with a valid depot or plot identity.
* Do not insert records with missing container IDs.
* Do not insert records with unresolved booking IDs.
* Do not insert duplicate records.
* Do not insert records that exceed booking quantity limits.
* Preserve seal, transporter, vehicle, remarks, movement date, and movement time information during insertion.

---

### 38. Insert Movement Errors

* Insert failed Gate-In and Gate-Out records into a dedicated movement-error flow.
* Preserve gate type, error code, container identity, booking identity, movement dates, movement times, remarks, seal number, transporter, vehicle number, container type, and container status where available.
* Ensure error records are reviewable and actionable by business users.

---

## Email Intake Workflow

### 39. Discover Pending Depot Emails

* Identify depot-report emails that are pending processing.
* Only process emails that belong to the depot extraction process.
* Ignore emails that have already been completed.
* Ignore records without a valid message identifier.

---

### 40. Resolve Original Sender

* Read the email body preview.
* Extract the first valid email address found in the text.
* Derive the sender domain from the extracted email address.
* If no sender email is found, mark sender domain as unresolved.

---

### 41. Map Sender to Depot

* Use the sender domain to identify the matching depot contact.
* Resolve the depot name and depot ID from the sender mapping.
* Use the resolved depot identity to name and contextualize the incoming attachment.
* If no depot mapping is found, continue safely but mark the depot context as unresolved.

---

### 42. Acquire Depot Attachments

* Retrieve external attachments linked to the pending email.
* Process only attachments that are relevant to Sarjak depot movement.
* Skip attachments that belong to ARCON or unrelated entities.
* Save accepted attachments using depot-aware naming.
* Preserve message ID linkage for traceability.

---

### 43. Mark Email Completion

* After successful processing, mark the corresponding email as completed.
* Only mark completion when insertion or final processing mode confirms completion.
* Keep incomplete or failed emails available for reprocessing.

---

## Run Control Workflow

### 44. Create Run Context

* Treat every processing execution as a separate run.
* Group processed files, extracted tables, final results, reports, and errors under the run context.
* Keep each run isolated to avoid mixing outputs from different execution batches.

---

### 45. Publish Run Artifacts

* Publish processed files, extraction tables, result files, reports, and JSON outputs atomically.
* Ensure partial outputs do not overwrite stable previous outputs.
* Preserve every relevant artifact required for debugging, review, and audit.

---

### 46. Return Run Summary

* Return a final run summary after processing completes.
* Include number of workbooks processed.
* Include locations of processed files, extracted tables, results, and reports.
* Include database insert counts.
* Include message IDs processed.
* Include completion timestamp.
* Include error counts or failed-record summaries where applicable.

---

## Failure Handling Workflow

### 47. Handle Unsupported Files

* If a file cannot be opened or parsed, mark it as failed.
* Do not allow one bad file to stop the entire batch if other files can still be processed.
* Preserve failed-file information for review.

---

### 48. Handle Unclear Region

* If language or region cannot be confidently detected, do not apply unsafe extraction assumptions.
* Either use safe default logic or mark the file as unresolved depending on confidence.
* Keep unresolved files visible for review.

---

### 49. Handle Missing Headers

* If no valid header row is found, skip table extraction for that sheet.
* Do not infer columns blindly without headers.
* Record the failure reason for review.

---

### 50. Handle Missing Containers

* If a table contains no valid container numbers, do not generate final movement records from it.
* Preserve intermediate table output only if useful for debugging.
* Avoid inserting any record without a valid container anchor.

---

### 51. Handle Ambiguous Movement Direction

* If a table could be both Gate-In and Gate-Out, do not force it into either flow unless workbook-level context clearly resolves it.
* Keep ambiguous tables out of insertion flow.
* Mark ambiguous cases for review.

---

### 52. Handle Missing Required Business Fields

* Gate-In records can proceed only if mandatory fields needed for insertion are valid.
* Gate-Out records can proceed only if container, booking, depot, and quantity validations pass.
* Optional fields such as remarks, transporter, vehicle number, or seal number may remain blank if not available.

---

### 53. Handle Database Validation Failures

* If validation lookups fail, do not insert unsafe records.
* Preserve extracted records and flag them for review.
* Keep extraction results separate from insertion results so that business users can still inspect what was extracted.

---

## Final Acceptance Criteria

### 54. File-Level Acceptance

* The module accepts depot Excel files from different depot formats.
* The module identifies the correct region using language.
* The module processes only relevant movement sheets.
* The module ignores unrelated or summary sheets.
* The module handles merged cells correctly.
* The module detects tables dynamically without fixed coordinates.
* The module stops extraction at the correct blank-row boundary.

---

### 55. Extraction-Level Acceptance

* The module extracts only rows with valid container numbers.
* The module correctly separates Gate-In and Gate-Out records.
* The module extracts dates and times from flexible formats.
* The module extracts booking IDs for Gate-Out records.
* The module extracts remarks for Gate-In and Gate-Out records.
* The module extracts transporter, vehicle, and seal fields where available.
* The module handles India and China-specific movement formats.

---

### 56. Validation-Level Acceptance

* The module identifies missing containers.
* The module identifies duplicate Gate-In records.
* The module identifies duplicate Gate-Out records.
* The module identifies invalid Gate-In container statuses.
* The module identifies missing Gate-Out booking IDs.
* The module identifies Gate-Out booking quantity violations.
* The module preserves error priority correctly.

---

### 57. Output-Level Acceptance

* The module produces clean Gate-In outputs.
* The module produces clean Gate-Out outputs.
* The module produces clear error outputs.
* The module produces readable reports.
* The module produces structured JSON files.
* The module keeps run artifacts organized.
* The module returns a useful run summary.

---

### 58. Insertion-Level Acceptance

* The module inserts only error-free Gate-In records.
* The module inserts only error-free Gate-Out records.
* The module does not insert duplicate records.
* The module does not insert records with unresolved mandatory IDs.
* The module does not insert records that exceed booking quantity limits.
* The module stores failed records in an error-review flow.

---

## Final Logical Summary

The depot extraction module receives depot Excel reports, detects the region from language, selects the correct regional rules, identifies relevant sheets, dynamically detects table headers, extracts rows containing valid container numbers, classifies each table as Gate-In or Gate-Out, extracts the required movement fields, normalizes dates and times, validates records against business rules, separates valid records from error records, generates structured outputs and reports, inserts only clean records, stores failed records for review, and preserves full run-level traceability.
