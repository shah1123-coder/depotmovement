# Technical Logic Brief: Depot File Extraction Module

## 1. Receive Depot Report File

* The module processes depot report files where each report is an Excel-based file.
* Supported file types include `.xlsx`, `.xls`, encrypted Excel files, and other Microsoft Excel-compatible formats.
* Each depot report file may have a completely different format, layout, sheet structure, header position, header wording, merged-cell structure, column order, or data alignment.
* The purpose of the file is to extract container Gate-In and Gate-Out movement records.
* The module must not depend on fixed Excel templates.
* The module must not assume fixed sheet names.
* The module must not assume fixed column positions.
* The module must not assume fixed header labels.
* The module must extract valid movement rows based on dynamic table detection and regex-driven row identification.

---

## 2. Identify File Region

* Depot report formats are grouped by region.
* Current regional scope is limited to India and China.
* Region selection is primarily based on language detection.
* If the report language is English, classify the file/sheet as India.
* If the report language is Chinese, classify the file/sheet as China.
* For sheet-level detection, use the sheet title:

  * If the sheet title contains any CJK character, choose China.
  * Otherwise, default to India.
* Region classification determines:

  * Sheet-selection rules.
  * Gate-In / Gate-Out keyword rules.
  * Header marker rules.
  * Booking fallback rules.
  * Vehicle regex rules.
  * Remarks marker rules.
  * Extraction configuration.
  * Validation expectations.
  * Future regional extensibility behavior.

---

## 3. Load Region-Specific Extraction Rules

* The complete extraction module functions on regex and dynamic header extraction.
* Separate regex/config files must exist per region.
* Regional regex separation is required so the system remains modular.
* Regional separation allows future expansion into additional countries without rewriting the core extraction engine.
* Shared regex rules are used where the format is region-independent.
* Region-specific regex and marker rules are used where India and China differ.
* Current shared container regex:

  * `\b[A-Z]{3}[UJZ]\d{7}\b`
* Container regex must be applied case-insensitively.
* Extracted container numbers must be uppercased.
* Shared Gate-Out booking regex:

  * `\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b`
* Shared time regex:

  * `([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(\s*[AP]M)?`
* Date regex coverage includes:

  * `dmy`
  * `mdy`
  * `ymd`
  * Separators: `.`, `/`, `-`, and space.
  * Textual forms such as `d-Mon-yyyy`.
  * Textual forms such as `Mon d, yyyy`.
* India vehicle regex:

  * `\b[A-Z]{2}[- ]?\d{2}[- ]?[A-Z]{1,3}[- ]?\d{4}\b`
* China vehicle regex:

  * Province-character prefix plus Chinese plate-number pattern.
* India booking fallback regex:

  * `(?!x)x`
  * This is intentionally a never-match fallback.
* China booking fallback regex:

  * `^\d{6}$`
* Sheet-name standalone IN regex:

  * `(?<![A-Za-z0-9])IN(?![A-Za-z0-9])`
* Sheet-name OUT logic is symmetric to the standalone IN rule.
* Gate direction IN indicators include:

  * Standalone `IN`
  * `GATE\s*IN`
  * Chinese `进`
* Gate direction OUT indicators include:

  * Standalone `OUT`
  * `GATE\s*OUT`
  * Chinese `出`
* Recognized sheet-name regex:

  * `GATE IN|GATE OUT|DAILY MOVEMENT|DAILY REPORT|GATE IN & OUT SUMMERY`
* Path sanitization invalid characters:

  * `<>:"/\|?*`
  * Control characters.
* Booked quantity parsing regex:

  * `(\d+)\s*X\s*(.+)`
* Email sender regex:

  * `[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}`

---

## 4. Identify Relevant Sheets

* Load each workbook and iterate through every worksheet.
* Use `sheet_selection_for_name(sheet.title)` to select region logic.
* China is selected if any CJK character is present in the sheet title.
* India is selected by default when no CJK character is present.
* Sheet eligibility is controlled through `should_process_sheet`.
* Convert sheet names to uppercase for eligibility checks.
* Exclude sheets whose names contain:

  * `MONTH`
  * `MASTER`
* Force-process sheets if the name belongs to `always_process_names`.
* `always_process_names` includes:

  * `SHEET1`
* Force-process China direct movement sheets if the sheet name is present in:

  * `direct_in_names`
  * `direct_out_names`
* China direct IN sheet name:

  * `进场`
* China direct OUT sheet name:

  * `出场`
* Determine whether the sheet contains an IN indicator.
* Determine whether the sheet contains an OUT indicator.
* If the language has an IN marker, use the region/language IN marker.
* If no region/language IN marker applies, use standalone IN regex:

  * `(?<![A-Za-z0-9])IN(?![A-Za-z0-9])`
* OUT detection follows the same logic symmetrically.
* Recognized sheet names are accepted if they match:

  * `GATE IN`
  * `GATE OUT`
  * `DAILY MOVEMENT`
  * `DAILY REPORT`
  * `GATE IN & OUT SUMMERY`
* Recognized sheet names are processed unless they contain both IN and OUT indicators.
* Generic sheet rule:

  * Process only when exactly one of IN or OUT is present.
  * This is an XOR condition.
* Reject sheet when both IN and OUT indicators are present and no safe resolution exists.
* Reject sheet when neither IN nor OUT indicators are present and the name is not force-included or recognized.

---

## 5. Classify Sheet Movement Intent

* Movement direction is classified as IN, OUT, or unresolved.
* Direction is derived from multiple sources in priority order:

  1. Extracted table filename.
  2. Parent folder name.
  3. Original workbook name.
* Direction detection logic:

  * `has_in` is true when any IN indicator is found.
  * `has_out` is true when any OUT indicator is found.
* IN indicators:

  * Standalone `IN`
  * `GATE\s*IN`
  * Chinese `进`
* OUT indicators:

  * Standalone `OUT`
  * `GATE\s*OUT`
  * Chinese `出`
* If both IN and OUT are detected:

  * Return `None`.
* If only IN is detected:

  * Return `IN`.
* If only OUT is detected:

  * Return `OUT`.
* If neither IN nor OUT is detected:

  * Return `None`.
* Workbook-level suffix logic:

  * Scan all `.xlsx` files under the workbook extraction folder.
  * If exactly one movement direction is found across all extracted tables, append `-IN` or `-OUT` suffix to output names.
* Final fallback:

  * If table filename and parent folder cannot determine direction, use the workbook name.
  * Workbook name fallback uses `GATE IN/GATE OUT` XOR matching.
* Do not force ambiguous tables into IN or OUT unless fallback logic resolves them clearly.

---

## 6. Normalize Merged Cells

* Open workbook with `openpyxl`.
* For table/header detection, load with:

  * `data_only=False`
* Detection must exclude formulas-as-text from valid plain-text header detection.
* Build a merged-cell map for every worksheet.
* For each merged range:

  * Get bounds:

    * `min_col`
    * `min_row`
    * `max_col`
    * `max_row`
  * Read the value from the top-left cell.
  * Register the same tuple and value for every `(row, col)` inside the merged range.
* Merged-cell handling ensures headers spanning multiple columns are understood as one logical unit.
* Merged-cell handling ensures duplicate values inside a merge range are not emitted multiple times.

---

## 7. Build Logical Rows

* For each row, scan columns from `1` to `max_column`.
* If a cell is the top-left cell of a merged range:

  * Emit one logical cell spanning the full merged range.
  * Jump directly to `end_col + 1`.
* If a cell is inside a merged range but not the top-left:

  * Skip it.
* If a cell is not merged:

  * Emit a `1×1` logical cell.
* Logical cell fields:

  * `row`
  * `end_row`
  * `start_col`
  * `end_col`
  * `value`
  * `is_horizontal_merge`
  * `is_vertical_merge`
* `is_horizontal_merge` is true when:

  * `end_col > start_col`
* `is_vertical_merge` is true when:

  * `end_row > start_row`
* Logical-row construction is used for:

  * Header detection.
  * Title detection.
  * Table boundary detection.
  * Cell clipping.
  * Output reconstruction.

---

## 8. Detect Header Rows Dynamically

* Header detection works at the logical-cell level.
* A plain-text header candidate cell must satisfy all conditions:

  * Value is a string.
  * Value is non-empty after stripping whitespace.
  * Value does not start with `=`.
* The following fail the plain-text header test:

  * Formulas.
  * Numbers.
  * Dates.
  * `None`.
  * Blank cells.
* Within each row:

  * Accumulate consecutive plain-text logical cells.
  * Break the run when a non-plain cell is encountered.
* A header run is valid only when the run length is at least:

  * `min_cells`
* Default `min_cells`:

  * `3`
* Header detection scans each sheet from top to bottom.
* When a row yields one or more valid header runs:

  * Emit a `HeaderRun` for each run.
  * Skip all immediately following rows that also qualify as header runs.
* Skipping immediately following header-like rows prevents duplicate detection of stacked or multi-line headers.
* `HeaderRun` fields:

  * `sheet`
  * `row`
  * `start_col`
  * `end_col`
  * `logical_cell_count`
  * `values[]`
  * `cells[]`
  * `title`
* `start_col` is the first run cell’s starting column.
* `end_col` is the last run cell’s ending column.

---

## 9. Identify Table Title

* Title lookup begins after a header run is found.
* Scan rows above the header.
* Search range:

  * From `header_row - 1`
  * Down to `header_row - 2`
* Maximum rows scanned above header:

  * `2`
* The first row above the header containing any non-empty logical cell becomes the title row.
* Title text is constructed by:

  * Taking all non-empty logical cell values from that row.
  * Stripping each value.
  * Joining values with spaces.
* If a title exists:

  * Attach it to the `HeaderRun`.
* If no title exists:

  * Table can still be extracted.
  * Sheet name can be used as fallback context.

---

## 10. Define Table Boundaries

* Data rows begin at:

  * `header.row + 1`
* Read rows downward from the first data row.
* Stop at the first row with no content in any logical cell.
* The first completely blank row terminates the table.
* Table horizontal range is restricted to:

  * `[header.start_col, header.end_col]`
* Data cells outside this column window are ignored.
* Cell clipping rule:

  * Keep only cells overlapping the header window.
  * Clamp `start_col` to:

    * `max(cell.start, header.start)`
  * Clamp `end_col` to:

    * `min(cell.end, header.end)`
  * If value is `None`, convert it to `""`.
  * Otherwise convert value to stripped string.
* Multiple tables in the same sheet are allowed.
* Each detected header run can produce a separate extracted table.

---

## 11. Detect Valid Container Rows

* Every candidate data row is scanned for container numbers.
* Shared container regex:

  * `\b[A-Z]{3}[UJZ]\d{7}\b`
* Container regex is case-insensitive.
* Extracted container numbers must be output uppercased.
* A valid movement row must contain a valid container number.
* Rows without a valid container number are skipped during final IN/OUT record extraction.
* During intermediate table extraction, rows without valid container numbers receive a synthetic error.
* Synthetic error column logic:

  * Append a cell at:

    * `header.end_col + 1`
  * If the row contains a container regex match:

    * Synthetic error value is `""`.
  * If the row does not contain a container regex match:

    * Synthetic error value is `INVALID_CONTAINER_NUMBER`.

---

## 12. Extract Intermediate Tables

* Write one `.xlsx` output file per detected table.
* Intermediate table output path:

  * `extraction/<workbook>/<sheet>/<sanitized-title-or-sheet ≤80 chars>.xlsx`
* If a title exists:

  * Write title to output row `1`.
  * Header row is offset by:

    * `header.row - title.row`
* If no title exists:

  * Header is written to output row `1`.
* Header row receives an extra label:

  * `"Error"`
* `"Error"` label is placed at:

  * `header.end_col + 1`
* Data rows follow the header.
* Horizontal merges are re-applied.
* Column normalization rule:

  * `col_offset = header.start_col - 1`
* Column normalization makes extracted tables start at column `1`.
* Path safety rule:

  * Replace characters `<>:"/\|?*` and control characters with spaces.
  * Collapse whitespace.
  * Strip trailing dots.
  * Fallback filename is `"untitled"` if sanitized output is empty.
* Locked-file fallback:

  * Append `_1` through `_999` when required.

---

## 13. Resolve Final Movement Direction

* After intermediate extraction, classify each table file as IN or OUT.
* Direction is derived from:

  1. Extracted table filename.
  2. Parent folder name.
  3. Original workbook name.
* Direction detection logic:

  * `has_in = standalone-IN regex OR GATE\s*IN OR Chinese 进`
  * `has_out = standalone-OUT regex OR GATE\s*OUT OR Chinese 出`
* If both `has_in` and `has_out` are true:

  * Direction is `None`.
* If only `has_in` is true:

  * Direction is `IN`.
* If only `has_out` is true:

  * Direction is `OUT`.
* If neither is true:

  * Direction is `None`.
* Workbook-level suffix rule:

  * Scan all `.xlsx` files under the workbook folder.
  * If exactly one direction is found across all files:

    * Append `-IN` or `-OUT` suffix to output names.
* Final fallback rule:

  * If filename and parent folder return `None`, use workbook name.
  * Workbook fallback uses `GATE IN/GATE OUT` regex XOR logic.
* Ambiguous direction is not forced.

---

## 14. Separate Gate-In and Gate-Out Tables

* Copy qualifying IN tables into:

  * `results/IN/`
* Copy qualifying OUT tables into:

  * `results/OUT/`
* Output naming format:

  * `<sanitized-workbook><suffix>.xlsx`
* Suffix may be:

  * `-IN`
  * `-OUT`
* Deduplication rule:

  * Deduplicate names per `(direction, basename)`.
  * Use suffixes:

    * `_1`
    * `_2`
    * Continued incrementally as needed.
* Tables with unresolved or ambiguous movement direction are not copied into final IN/OUT processing folders.

---

# Gate-In Technical Logic

## 15. Process Gate-In Tables

* Gate-In extraction is implemented in `in.py`.
* Load extracted table workbook with:

  * `data_only=True`
* Select patterns and fallback rules by language/region.
* Build merge map before row extraction.
* Detect remark column through row-major scan.
* Remark marker:

  * `remark`
* China additional remark marker:

  * `备注`
* For each row:

  * Gather raw values.
  * Search for valid container number.
  * If no container is found, skip the row.
  * Use the first container match in the row.
  * Use the first date match in the row.
  * Use the first time match in the row.
  * Read remark from the detected remark column.
* Gate-In record fields:

  * `container_no`
  * `date`
  * `time`
  * `remark`
  * `container_status`
  * `error_code`

---

## 16. Gate-In Field Requirements

* `container_no`:

  * Extracted using `\b[A-Z]{3}[UJZ]\d{7}\b`.
  * Case-insensitive match.
  * Output uppercased.
* `date`:

  * First date match in row.
  * Normalized when possible.
* `time`:

  * First time match in row.
  * Normalized when possible.
* `remark`:

  * Value from remark column.
  * Remark column detected using `remark` or China `备注`.
* `container_status`:

  * Extracted or later enriched from container/database status logic.
* `error_code`:

  * Empty when record is valid.
  * Populated during validation if required.

---

## 17. Gate-In Date and Time Handling

* Date values may come from:

  * Excel date cells.
  * Text cells.
  * Mixed-format cells.
* If date is `datetime` or `date`:

  * Normalize to `%Y-%m-%d`.
* If date is text:

  * Match using date regex.
  * Replace commas with spaces.
  * Collapse whitespace.
  * Try configured date formats.
  * Fallback to raw matched text if parsing fails.
* Supported date regex coverage:

  * `dmy`
  * `mdy`
  * `ymd`
  * Separators:

    * `.`
    * `/`
    * `-`
    * space
  * Textual:

    * `d-Mon-yyyy`
    * `Mon d, yyyy`
* Date parsing fallback formats include approximately 30 `strptime` patterns covering:

  * `d/m/y`
  * `m/d/y`
  * `y/m/d`
  * `/`
  * `.`
  * `-`
  * space separators
  * `%d %b %Y`
  * `%d %B %Y`
  * `%b %d %Y`
  * `%B %d %Y`
* Time values may come from:

  * Excel time cells.
  * Text cells.
  * Mixed-format cells.
* If time is `datetime` or `time`:

  * Normalize to `%H:%M:%S.000`.
* Shared time regex:

  * `([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(\s*[AP]M)?`
* Time parsing fallback formats:

  * `%I:%M %p`
  * `%I:%M%p`
* If parsing fails:

  * Reconstruct from regex groups as `HH:MM:SS.000`.

---

# Gate-Out Technical Logic

## 18. Process Gate-Out Tables

* Gate-Out extraction is implemented in `out.py`.
* For each row:

  * Require a valid container match.
  * If no container is found, skip the row.
  * Extract container from the row.
  * Resolve booking column.
  * Resolve seal column.
  * Resolve transporter column.
  * Resolve remarks column.
  * Resolve vehicle column or vehicle fallback.
  * Extract date using last/rightmost date match in row.
  * Extract time using last/rightmost time match in row.
* Gate-Out record fields:

  * `container_id`
  * `booking_id`
  * `seal_no`
  * `plot_out_date`
  * `plot_out_time`
  * `transporter`
  * `vehicle_no`
  * `remarks`
  * `error_code`

---

## 19. Gate-Out Field Requirements

* `container_id`:

  * Initially extracted through container number.
  * Later resolved to database `ContainerId`.
* `booking_id`:

  * Extracted from resolved booking column.
  * Validated through booking regex or fallback regex.
* `seal_no`:

  * Extracted using seal marker column.
* `plot_out_date`:

  * Last/rightmost date match in row.
* `plot_out_time`:

  * Last/rightmost time match in row.
* `transporter`:

  * Extracted using transporter marker column.
* `vehicle_no`:

  * Extracted using vehicle marker column or vehicle regex fallback.
* `remarks`:

  * Extracted using remark marker column.
* `error_code`:

  * Empty if valid.
  * `NO_BOOKING_ID` if booking is invalid or missing before validation.
  * Other errors may be added during validation.

---

## 20. Gate-Out Booking Logic

* Booking column resolution priority:

  1. Regex column.
  2. Marker columns.
  3. Fallback regex column.
* Regex column rule:

  * Find rightmost column containing booking pattern:

    * `XXX/XXX/######`
  * Exact regex:

    * `\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b`
* Marker-column rule:

  * Use `out_booking_markers`.
  * China additional booking marker:

    * `单号`
* Fallback regex column:

  * India fallback:

    * `(?!x)x`
    * Never-match fallback.
  * China fallback:

    * `^\d{6}$`
* Booking value is read from the resolved booking-column cell.
* Booking validation during extraction:

  * If booking matches main booking regex, error is empty.
  * If booking matches fallback regex, error is empty.
  * Otherwise set default error:

    * `NO_BOOKING_ID`
* `NO_BOOKING_ID` must be preserved during later validation.

---

## 21. Gate-Out Vehicle Logic

* Vehicle column resolution:

  * First use vehicle marker columns.
  * China additional vehicle marker:

    * `场车牌`
* If no vehicle marker column is found:

  * Scan valid container rows using vehicle regex fallback.
* India vehicle regex:

  * `\b[A-Z]{2}[- ]?\d{2}[- ]?[A-Z]{1,3}[- ]?\d{4}\b`
* China vehicle regex:

  * Province-character prefix plus Chinese plate-number pattern.
* Vehicle extraction must not block record creation if vehicle is blank.
* Vehicle is optional unless business rules later require it.

---

# Shared Normalization Technical Logic

## 22. Normalize Container Numbers

* Match container using:

  * `\b[A-Z]{3}[UJZ]\d{7}\b`
* Apply regex case-insensitively.
* Output container numbers uppercased.
* Normalize lookup keys as uppercase and no-space for database matching.
* Missing or invalid container number results in:

  * Intermediate error:

    * `INVALID_CONTAINER_NUMBER`
  * Final extraction skip unless a valid container anchor exists.

---

## 23. Normalize Dates

* Date regex supports:

  * `dmy`
  * `mdy`
  * `ymd`
  * `.`
  * `/`
  * `-`
  * space separators
  * `d-Mon-yyyy`
  * `Mon d, yyyy`
* If value is `datetime` or `date`:

  * Output `%Y-%m-%d`.
* If value is string:

  * Run date regex.
  * Replace `,` with space.
  * Collapse whitespace.
  * Try fallback date formats.
  * If all parsing fails, return raw matched text.
* Fallback parsing includes approximately 30 `strptime` patterns:

  * Day-first numeric formats.
  * Month-first numeric formats.
  * Year-first numeric formats.
  * Slash-separated formats.
  * Dot-separated formats.
  * Hyphen-separated formats.
  * Space-separated formats.
  * Short textual month formats.
  * Long textual month formats.

---

## 24. Normalize Times

* Time regex:

  * `([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(\s*[AP]M)?`
* If value is `datetime` or `time`:

  * Output `%H:%M:%S.000`.
* If value is string:

  * Run time regex.
  * Try fallback formats:

    * `%I:%M %p`
    * `%I:%M%p`
  * If parsing fails:

    * Reconstruct time from regex groups as `HH:MM:SS.000`.
* Time supports:

  * 24-hour format.
  * AM/PM format.
  * Optional seconds.
* Missing seconds are normalized into a full database-ready time representation.

---

## 25. Normalize Empty Values

* `None` cell values are converted to:

  * `""`
* Non-`None` values are converted to stripped strings.
* Blank optional fields remain blank.
* Blank mandatory fields are handled through validation.
* Formulas beginning with `=` are excluded from plain-text header detection.
* Numbers and dates fail header plain-text detection but may still be used as data values.

---

# Validation Technical Logic

## 26. Validate Gate-In Records

* Gate-In validation is database-driven.
* Error priority order:

  1. `NO_CONTAINER_ID`
  2. `DUPLICATE_RECORD`
  3. `INVALID_CONTAINER_STATUS_ID`
* `NO_CONTAINER_ID` trigger:

  * No `ContainerId` exists for extracted container number.
* `DUPLICATE_RECORD` trigger:

  * Existing `PlotInDetails` record exists for the same `ContainerId` and same date.
* Duplicate check query logic:

  * Per `(ContainerId, date)`.
  * Count rows in `PlotInDetails`.
  * Match where:

    * `ContainerId=?`
    * `CAST(PlotInDate AS DATE)=?`
* `INVALID_CONTAINER_STATUS_ID` trigger:

  * Container status is not in:

    * `{2,7}`
* Attach `status_id` to Gate-In record where available.
* Relevant status IDs from status master:

  * `{2,3,6,7}`
* Gate-In valid downstream status set:

  * `{2,7}`

---

## 27. Validate Gate-Out Records

* Gate-Out validation is database-driven.
* Error priority order:

  1. Preserve prior `NO_BOOKING_ID`
  2. `NO_CONTAINER_ID`
  3. `DUPLICATE_RECORD`
  4. `INVALID_ECP_COUNT`
* `NO_BOOKING_ID` trigger:

  * Booking was missing or invalid during extraction.
* `NO_CONTAINER_ID` trigger:

  * No `ContainerId` exists for extracted container number.
* `DUPLICATE_RECORD` trigger:

  * Existing `PlotOutDetails` record exists for same:

    * `ContainerId`
    * Date
    * `BookingId`
* Duplicate check query logic:

  * Per `(ContainerId, date, BookingId)`.
  * Count rows in `PlotOutDetails`.
  * Match where:

    * `ContainerId=?`
    * `CAST(PlotOutDate AS DATE)=?`
    * `BookingId=?`
* `INVALID_ECP_COUNT` trigger:

  * Extracted quantity for booking exceeds:

    * `booked quantity - already plotted quantity`
* Existing `NO_BOOKING_ID` must not be overwritten by later validation errors.

---

## 28. Validate Booking Quantities

* Resolve booking IDs before quantity validation.
* Numeric booking references are used as-is.
* Non-numeric booking references are matched against:

  * `BookingDetails.BookingNo`
* Also match trailing-letters-stripped booking variant.
* Booked quantity source:

  * `BookingDetails.BookedContainerQty`
* Booked quantity text format:

  * `"N X TYPE, M X TYPE"`
* Booked quantity parsing regex:

  * `(\d+)\s*X\s*(.+)`
* Sum all parsed `N` values to calculate total booked quantity.
* Already-plotted count query:

  * `SELECT BookingId, COUNT(ContainerId) FROM PlotOutDetails WHERE BookingId IN (...) GROUP BY BookingId`
* Compare extracted current-run quantity against remaining allowed quantity.
* If extracted quantity exceeds allowed quantity:

  * Set `INVALID_ECP_COUNT`.

---

## 29. Validate Duplicates

* Gate-In duplicate identity:

  * `ContainerId`
  * `PlotInDate` date portion
* Gate-Out duplicate identity:

  * `ContainerId`
  * `PlotOutDate` date portion
  * `BookingId`
* Gate-In duplicate query:

  * `plotin_records_exist`
  * `ContainerId=?`
  * `CAST(PlotInDate AS DATE)=?`
* Gate-Out duplicate query:

  * `plotout_records_exist`
  * `ContainerId=?`
  * `CAST(PlotOutDate AS DATE)=?`
  * `BookingId=?`
* Duplicate records are not inserted.
* Records with `DUPLICATE_RECORD` are excluded from `gate_errors.json`.
* Duplicate records may still appear in text/report outputs depending on reporting flow.

---

## 30. Validate Depot Identity

* PlotID is derived from attachment filename.
* PlotID derivation:

  * Take integer prefix before first underscore.
* Example:

  * `123_1.xlsx → 123`
* Sender-to-depot mapping can resolve depot identity before attachment naming.
* If `PortId` is resolved:

  * Attachment is named:

    * `<PortId>_<counter><ext>`
* If `PortId` is unresolved:

  * Attachment fallback name:

    * `<originalstem>_<counter>`
* Gate-In insert requires non-null `PlotID`.
* Gate-Out insert requires non-null `PlotId`.
* Records with unresolved mandatory depot/plot identity are not safely inserted.

---

# Output Technical Logic

## 31. Generate Gate-In Output

* Gate-In text output file:

  * `in.txt`
* Gate-In JSON output file:

  * `gate_in.json`
* Gate-In text columns:

  * `Container #`
  * `Date`
  * `Time`
  * `Remark`
  * `Cnt_status`
  * `ErrorCode`
* Gate-In JSON schema:

  * List of records.
  * Each record format:

    * `{"values": {...}}`
* Gate-In JSON `values` fields:

  * `PlotInID`
  * `PlotID`
  * `ContainerId`
  * `PlotInDate`
  * `PlotInStatus:"P"`
  * `CreatedBy:1`
  * `Remarks`
  * `BookingId`
  * `OutBookingID:null`
  * `ContainerStatusId`
  * Optional `ErrorCode`

---

## 32. Generate Gate-Out Output

* Gate-Out text output file:

  * `out.txt`
* Gate-Out JSON output file:

  * `gate_out.json`
* Gate-Out text columns:

  * `ContainerID`
  * `BookingId`
  * `SealNo`
  * `PlotOutDate`
  * `PlotOutTime`
  * `Transporter`
  * `VehicleNo`
  * `Remarks`
  * `ErrorCode`
* Gate-Out JSON schema:

  * List of records.
  * Each record format:

    * `{"values": {...}}`
* Gate-Out JSON `values` fields:

  * `PlotOutId`
  * `BookingId`
  * `ContainerId`
  * `SealNo`
  * `Transporter`
  * `VehicleNo`
  * `PlotOutDate`
  * `PlotOutTime`
  * `Remarks`
  * `CreatedBy:1`
  * `PlotOutStatus:"P"`
  * `PlotId`
  * `ContType`
  * `ContainerStatusId`
  * Optional `ErrorCode`

---

## 33. Generate Error Output

* Error JSON output file:

  * `gate_errors.json`
* Include records from both IN and OUT flows.
* Include only records where:

  * `ErrorCode` is set.
  * `ErrorCode` is not `DUPLICATE_RECORD`.
* Add `GateType` to each error record.
* `GateType` values:

  * `IN`
  * `OUT`
* Error output must preserve enough fields to allow operational review.

---

## 34. Generate Human-Readable Reports

* Generate:

  * `in.txt`
  * `out.txt`
* Report structure:

  * Per-depot blocks.
  * Title line.
  * Pipe-separated aligned columns.
  * Dashed separator row.
  * `(none)` when empty.
* Gate-In columns:

  * `Container # | Date | Time | Remark | Cnt_status | ErrorCode`
* Gate-Out columns:

  * `ContainerID | BookingId | SealNo | PlotOutDate | PlotOutTime | Transporter | VehicleNo | Remarks | ErrorCode`

---

## 35. Generate Structured JSON Outputs

* JSON outputs:

  * `gate_in.json`
  * `gate_out.json`
  * `gate_errors.json`
* `gate_in.json` contains Gate-In records.
* `gate_out.json` contains Gate-Out records.
* `gate_errors.json` contains actionable error records.
* Duplicate records are excluded from `gate_errors.json`.
* Valid and invalid records may both be present in movement JSON outputs when error metadata is attached.
* Error-free records are eligible for insertion.
* Error records are eligible for error persistence.

---

# Persistence Technical Logic

## 36. Insert Valid Gate-In Records

* Insert target:

  * `dbo.PlotInDetails`
* Insert fields:

  * `PlotID`
  * `ContainerId`
  * `PlotInDate`
  * `PlotInStatus`
  * `CreatedBy`
  * `Remarks`
  * `BookingId`
  * `EditedBy`
* Fixed insert values:

  * `CreatedBy=1`
  * `EditedBy=1`
* `PlotInStatus` value:

  * `P`
* Insert only:

  * Error-free rows.
  * Rows with non-null `PlotID`.
* Do not insert:

  * Rows with `NO_CONTAINER_ID`.
  * Rows with `DUPLICATE_RECORD`.
  * Rows with `INVALID_CONTAINER_STATUS_ID`.
  * Rows missing required depot/plot identity.

---

## 37. Insert Valid Gate-Out Records

* Insert target:

  * `dbo.PlotOutDetails`
* Insert fields:

  * `BookingId`
  * `ContainerId`
  * `SealNo`
  * `Transporter`
  * `VehicleNo`
  * `PlotOutDate`
  * `PlotOutTime`
  * `Remarks`
  * `CreatedBy`
  * `PlotOutStatus`
  * `PlotId`
  * `EditedBy`
* Fixed insert values:

  * `CreatedBy=1`
  * `EditedBy=1`
* `PlotOutStatus` value:

  * `P`
* Insert only:

  * Error-free rows.
  * Rows with non-null `PlotId`.
* Do not insert:

  * Rows with `NO_BOOKING_ID`.
  * Rows with `NO_CONTAINER_ID`.
  * Rows with `DUPLICATE_RECORD`.
  * Rows with `INVALID_ECP_COUNT`.
  * Rows missing required depot/plot identity.

---

## 38. Insert Movement Errors

* Error insert target:

  * `dbo.DepotMovementError`
* Insert failed rows with fields:

  * `GateType`
  * `ErrorCode`
  * `ContainerId`
  * `PlotID`
  * `PlotInID`
  * `PlotOutId`
  * `BookingId`
  * `PlotInDate`
  * `PlotOutDate`
  * `PlotOutTime`
  * `PlotInStatus`
  * `PlotOutStatus`
  * `OutBookingID`
  * `CreatedBy`
  * `Remarks`
  * `SealNo`
  * `Transporter`
  * `VehicleNo`
  * `ContType`
  * `ContainerStatusId`
* Error persistence keeps failed records reviewable.
* Error persistence includes both Gate-In and Gate-Out records.
* Duplicate records are excluded from `gate_errors.json`, but insert behavior depends on final error persistence flow.

---

# Email Intake Technical Logic

## 39. Discover Pending Depot Emails

* Mail source DB:

  * SQL Server `MAIL_DB_SERVER`
* Default mail DB server:

  * `10.1.0.6`
* Mail database:

  * `EMail_Reader_Process_Data`
* Access method:

  * `sqlcmd` subprocess.
* Do not use:

  * `pyodbc` for mail DB access.
* Pending email discovery query:

  * `SELECT DISTINCT internet_message_id FROM dbo.tbl_Process_Emails WHERE completed_at IS NULL AND Process='VISHNU_DEPOT' AND NULLIF(LTRIM(RTRIM(internet_message_id)),'') IS NOT NULL`
* Only process:

  * Rows where `completed_at IS NULL`.
  * Rows where `Process='VISHNU_DEPOT'`.
  * Rows where `internet_message_id` is not blank after trimming.

---

## 40. Resolve Original Sender

* Email body source query:

  * `SELECT body_preview FROM dbo.tbl_Process_Emails WHERE internet_message_id = '<id>'`
* Scan `body_preview` raw text for first email address.
* Sender email regex:

  * `[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}`
* Sender domain rule:

  * Take first regex email match.
  * Keep `@` plus everything after the last `@`.
* If no email match is found:

  * Use `"Not Found"`.

---

## 41. Map Sender to Depot

* Sender-to-depot mapping query:

  * `SELECT pd.PortId, pd.PortName FROM dbo.PortDetails pd INNER JOIN dbo.LocationContacts lc ON pd.PortId=lc.PortId WHERE lc.DepotContactEmail='<domain>' AND lc.IsDeleted=0`
* Match sender domain against:

  * `LocationContacts.DepotContactEmail`
* Only active contacts:

  * `lc.IsDeleted=0`
* Output:

  * `PortId`
  * `PortName`
* Resolved `PortId` is used for attachment naming.
* If unresolved, fallback attachment naming is used.

---

## 42. Acquire Depot Attachments

* Attachment source endpoint:

  * `HTTPS mail-reader.sarjak.com/api/attachment/internet-id/<urlencoded-id>/external-attachments`
* Endpoint returns JSON.
* Expected JSON field:

  * `attachments[]`
* Attachment object fields:

  * `name` or `fileName`
  * Base64 `contentBytes`
* Attachment filter:

  * Skip if attachment name contains `ARCON`.
  * Keep only if attachment name contains `SARJAK`.
  * Otherwise skip.
* Attachment save folder:

  * `files/api/`
* Attachment naming when `PortId` resolved:

  * `<PortId>_<counter><ext>`
* Attachment naming when `PortId` unresolved:

  * `<originalstem>_<counter>`
* Message sidecar file:

  * `<file>.message-id`
* Message sidecar content:

  * `internet_message_id`

---

## 43. Mark Email Completion

* Completion write-back query:

  * `UPDATE dbo.tbl_Process_Emails SET completed_at='<ts>' WHERE internet_message_id IN (...) AND completed_at IS NULL; SELECT @@ROWCOUNT;`
* Completion write-back is performed only on:

  * `--insert`
* Completion write-back updates only records where:

  * `completed_at IS NULL`
* Completion result is checked with:

  * `SELECT @@ROWCOUNT`

---

# Run Control Technical Logic

## 44. Create Run Context

* Each run processes a batch of workbooks/attachments.
* Run artifacts are grouped by timestamp.
* Artifact folders include:

  * `processed`
  * `extraction`
  * `results`
* Each run keeps files isolated from other runs.
* Run context tracks:

  * Workbooks.
  * Directories.
  * Reports.
  * Database counts.
  * Message IDs.
  * Completion timestamp.

---

## 45. Publish Run Artifacts

* Run artifacts are atomically published to:

  * `files/{processed,extraction,results}/<YYYY-MM-DD_HH-MM-SS>/`
* Atomic publishing prevents partial results from replacing stable outputs.
* Intermediate extracted tables are preserved.
* Final IN/OUT result files are preserved.
* Human-readable reports are preserved.
* JSON outputs are preserved.
* Processed workbook copies are preserved.

---

## 46. Return Run Summary

* Pipeline returns JSON summary.
* Summary includes:

  * `workbooks`
  * `dirs`
  * `report paths`
  * `db counts`
  * `message ids`
  * `completed_at`
* Summary must clearly identify:

  * What was processed.
  * Where artifacts were written.
  * What reports were generated.
  * Which email message IDs were completed.
  * How many database records were inserted or affected.

---

# Failure Handling Technical Logic

## 47. Handle Unsupported Files

* If workbook cannot be opened, mark file as failed.
* If encrypted or unsupported format cannot be parsed, do not continue unsafe extraction.
* Preserve failure context.
* Continue processing other files where possible.
* Do not allow one failed workbook to corrupt the batch.

---

## 48. Handle Unclear Region

* Region detection defaults to India when no CJK character is found in sheet title.
* If China indicators are present, apply China rules.
* If language/region remains uncertain, avoid unsafe assumptions where possible.
* Use sheet-level region detection when workbook-level detection is insufficient.
* Keep unresolved cases reviewable.

---

## 49. Handle Missing Headers

* If no header run is found, no table is extracted from that section.
* Header run requires at least `min_cells=3` consecutive plain-text logical cells.
* Plain-text cell must be:

  * Non-empty string.
  * Stripped.
  * Not starting with `=`.
* Formulas, numbers, dates, and blank values are rejected as header candidates.
* Do not infer tables without headers.

---

## 50. Handle Missing Containers

* Rows without a valid container regex match are skipped during final extraction.
* Container regex:

  * `\b[A-Z]{3}[UJZ]\d{7}\b`
* Intermediate extracted table marks invalid rows using:

  * `INVALID_CONTAINER_NUMBER`
* Synthetic error column is added at:

  * `header.end_col + 1`
* If no valid container rows exist, no final movement records are created from that table.

---

## 51. Handle Ambiguous Movement Direction

* If both IN and OUT are detected in the same direction source:

  * Return `None`.
* If filename is ambiguous:

  * Try parent folder.
* If parent folder is ambiguous:

  * Try workbook name.
* If workbook-wide scan finds exactly one direction:

  * Apply that direction.
* If ambiguity remains:

  * Do not copy table into final `results/IN/` or `results/OUT/`.
  * Do not insert records from that table.

---

## 52. Handle Missing Required Business Fields

* Gate-In mandatory business requirements:

  * Valid container.
  * Resolved `ContainerId`.
  * Non-duplicate movement.
  * Valid container status.
  * Non-null `PlotID` for insertion.
* Gate-Out mandatory business requirements:

  * Valid container.
  * Resolved `ContainerId`.
  * Valid/resolved booking.
  * Non-duplicate movement.
  * Booking quantity not exceeded.
  * Non-null `PlotId` for insertion.
* Optional fields:

  * Remarks.
  * Seal number.
  * Transporter.
  * Vehicle number.
* Optional blank fields do not block extraction unless downstream business rules require them.

---

## 53. Handle Database Validation Failures

* If container lookup fails:

  * Set `NO_CONTAINER_ID`.
* If booking lookup fails:

  * Preserve or set `NO_BOOKING_ID`.
* If duplicate exists:

  * Set `DUPLICATE_RECORD`.
* If container status invalid for IN:

  * Set `INVALID_CONTAINER_STATUS_ID`.
* If Gate-Out quantity exceeds booking capacity:

  * Set `INVALID_ECP_COUNT`.
* Records with blocking validation errors are not inserted into movement tables.
* Failed records are kept for reporting and error persistence.

---

# Database Technical Logic

## 54. ICMS Connection

* ICMS server:

  * `ICMS_SERVER`
* Default ICMS server:

  * `10.10.0.72`
* Database:

  * `ICMS`
* Driver:

  * `ODBC Driver 17`
* Query chunk size:

  * `1000` IDs per `IN (...)` query.
* Insert connection:

  * `_connect_archeet`
* Insert connection target:

  * `archeet` DB.
* All inserts use:

  * `_connect_archeet`

---

## 55. Status Master Logic

* Status master IDs:

  * `1–15`
* Status examples:

  * `AV`
  * `EY`
  * `ECP`
  * `ECP`
  * `LIP`
  * `LOB`
  * `LAD`
* Relevant status IDs:

  * `{2,3,6,7}`
* Gate-In downstream valid status set:

  * `{2,7}`

---

## 56. Container Lookup Logic

* Container ID query:

  * `SELECT ContainerNo, ContainerId FROM ContainerEntry WHERE ContainerNo IN (...)`
* Container keys are normalized:

  * Uppercase.
  * No spaces.
* Container info query:

  * `SELECT ContainerNo, ContainerStatusId, LocationPlotId FROM ContainerEntry ...`
* Plot info follow-up query:

  * `SELECT PlotID, PlotName FROM PlotInformationDetails ...`
* Container info output:

  * `status_in_relevant_or_None`
  * `location_plot_id`
  * `plot_name`
* Container status IDs are derived from:

  * First element of `get_container_info`
* Container type query:

  * `SELECT ContainerNo, ContainerType FROM ContainerEntry WHERE ...`

---

## 57. Depot Lookup Logic

* Latest depot names are resolved using a CTE across:

  * `ContainerEntry`
  * `PlotInDetails`
  * `PortDetails`
  * `LocationPortMapping`
  * `LocationTypeMapping`
* Location mapping filters:

  * `LocationPortMapping.IsActive=1`
  * `LocationPortMapping.IsPrimary=1`
  * `LocationTypeMapping.LocationTypeId=2`
  * `LocationTypeMapping.IsActive=1`
* Latest depot ranking:

  * `ROW_NUMBER()`
  * Ordered by `PlotInDate DESC`
  * Use `rn=1`
* Depot ID lookup:

  * `SELECT PortName, PortId FROM PortDetails WHERE PortName IN (...)`

---

## 58. Booking Lookup Logic

* Booking reference resolution:

  * Numeric refs are used as-is.
  * Non-numeric refs match against `BookingDetails.BookingNo`.
  * Also try trailing-letters-stripped variant.
* Booked quantity source:

  * `BookingDetails.BookedContainerQty`
* Booked quantity parsing regex:

  * `(\d+)\s*X\s*(.+)`
* Plot-out count query:

  * `SELECT BookingId, COUNT(ContainerId) FROM PlotOutDetails WHERE BookingId IN (...) GROUP BY BookingId`
* Previous Gate-Out booking lookup:

  * Latest `PlotOutDetails.BookingId` per `ContainerId`.
  * Order by:

    * `PlotOutDate DESC`
    * `PlotOutId DESC`
  * Use:

    * `rn=1`

---

## 59. Latest Movement ID Lookup Logic

* Latest Plot-In ID lookup:

  * Get latest `PlotInID`.
  * Filter:

    * `PlotInStatus='P'`
  * Order by:

    * `PlotInDate DESC`
    * `PlotInID DESC`
* Latest Plot-Out ID lookup:

  * Get latest `PlotOutId`.
  * Filter:

    * `PlotOutStatus='P'`
  * Order by:

    * `PlotOutDate DESC`
    * `PlotOutId DESC`

---

## 60. Existence Check Logic

* `container_ids_exist`:

  * Per-ID `EXISTS` checks against `ContainerEntry`.
* `booking_ids_exist`:

  * Per-ID `EXISTS` checks against `BookingDetails`.
* These existence checks support validation and prevent unsafe inserts.

---

# Final Technical Acceptance Criteria

## 61. File-Level Acceptance

* Accept Excel-based depot files.
* Support `.xlsx`, `.xls`, encrypted Excel, and Microsoft Excel-compatible formats where parseable.
* Process India and China files.
* Classify China using CJK characters.
* Default non-CJK sheet names to India.
* Process only eligible movement sheets.
* Exclude `MONTH` and `MASTER`.
* Force-process `SHEET1`.
* Force-process China `进场` and `出场`.
* Handle merged cells.
* Detect headers dynamically.
* Stop tables at first blank row.
* Preserve intermediate extracted tables.

---

## 62. Extraction-Level Acceptance

* Detect containers using:

  * `\b[A-Z]{3}[UJZ]\d{7}\b`
* Detect booking IDs using:

  * `\b[A-Za-z]{3}/[A-Za-z]{3}/\d{6}\b`
* Detect time using:

  * `([01]?\d|2[0-3]):([0-5]\d)(:[0-5]\d)?(\s*[AP]M)?`
* Detect India vehicles using:

  * `\b[A-Z]{2}[- ]?\d{2}[- ]?[A-Z]{1,3}[- ]?\d{4}\b`
* Detect India IN using:

  * `(?<![A-Za-z0-9])IN(?![A-Za-z0-9])`
* Detect directions using:

  * Standalone `IN`
  * Standalone `OUT`
  * `GATE\s*IN`
  * `GATE\s*OUT`
  * Chinese `进`
  * Chinese `出`
* Detect recognized sheet names using:

  * `GATE IN|GATE OUT|DAILY MOVEMENT|DAILY REPORT|GATE IN & OUT SUMMERY`
* Use IN first date/time match.
* Use OUT last/rightmost date/time match.
* Use IN remark markers:

  * `remark`
  * China `备注`
* Use OUT booking marker:

  * `out_booking_markers`
  * China `单号`
* Use OUT seal marker:

  * `seal`
* Use OUT transporter marker:

  * `transporter`
* Use OUT remarks markers:

  * `remark`
  * China `备注`
* Use OUT vehicle marker:

  * China `场车牌`
* Use China booking fallback:

  * `^\d{6}$`
* Use India booking fallback:

  * `(?!x)x`

---

## 63. Validation-Level Acceptance

* Gate-In error priority:

  1. `NO_CONTAINER_ID`
  2. `DUPLICATE_RECORD`
  3. `INVALID_CONTAINER_STATUS_ID`
* Gate-Out error priority:

  1. Preserve `NO_BOOKING_ID`
  2. `NO_CONTAINER_ID`
  3. `DUPLICATE_RECORD`
  4. `INVALID_ECP_COUNT`
* Gate-In valid status set:

  * `{2,7}`
* Relevant status IDs:

  * `{2,3,6,7}`
* Duplicate Gate-In key:

  * `ContainerId + PlotInDate`
* Duplicate Gate-Out key:

  * `ContainerId + PlotOutDate + BookingId`
* Booking quantity parser:

  * `(\d+)\s*X\s*(.+)`
* Error-free records only are inserted.
* Duplicate records are excluded from `gate_errors.json`.

---

## 64. Output-Level Acceptance

* Generate:

  * `in.txt`
  * `out.txt`
  * `gate_in.json`
  * `gate_out.json`
  * `gate_errors.json`
* Generate intermediate extracted `.xlsx` tables.
* Generate final `results/IN/` and `results/OUT/`.
* Use safe path sanitization:

  * Replace `<>:"/\|?*` and control characters.
  * Collapse whitespace.
  * Strip trailing dots.
  * Fallback to `"untitled"`.
* Use locked-file fallback:

  * `_1` through `_999`
* Use run artifact path:

  * `files/{processed,extraction,results}/<YYYY-MM-DD_HH-MM-SS>/`
* Return JSON summary containing:

  * `workbooks`
  * `dirs`
  * `report paths`
  * `db counts`
  * `message ids`
  * `completed_at`

---

## 65. Database Table Acceptance

* Tables touched:

  * `ContainerEntry`
  * `PlotInformationDetails`
  * `PortDetails`
  * `LocationContacts`
  * `LocationPortMapping`
  * `LocationTypeMapping`
  * `BookingDetails`
  * `PlotInDetails`
  * `PlotOutDetails`
  * `DepotMovementError`
  * Mail DB table `tbl_Process_Emails`

