#!/usr/bin/env python3
"""Reconcile a STAR session-log CSV against an RSM HTML `.xls` export."""

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path


CENT = Decimal("0.01")


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table_stack = []
        self.current_row = None
        self.current_cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            table = []
            self.tables.append(table)
            self.table_stack.append(table)
        elif tag == "tr" and self.table_stack:
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.current_cell is not None:
            self.current_row.append("".join(self.current_cell).strip())
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if self.current_row:
                self.table_stack[-1].append(self.current_row)
            self.current_row = None
        elif tag == "table" and self.table_stack:
            self.table_stack.pop()


def money(value):
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text or text.lower() in {"nan", "none", "-"}:
        return Decimal("0")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"Invalid currency value: {value!r}") from error


def number(value):
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "-"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def identifier(value):
    parsed = number(value)
    if parsed is None:
        raise ValueError(f"Invalid student ID: {value!r}")
    return str(int(parsed))


def service_date(value):
    text = str(value).strip().split(" ")[0]
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Invalid service date: {value!r}")


def normalized(value):
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def session_time(value):
    text = normalized(value).upper()
    for pattern in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            return datetime.strptime(text, pattern).strftime("%H:%M")
        except ValueError:
            continue
    return None


def require_columns(columns, required, source):
    missing = [column for column in required if column not in columns]
    if missing:
        raise ValueError(f"{source} is missing required columns: {', '.join(missing)}")


def load_star(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        require_columns(
            columns,
            {"Student Id Number", "Session Date", "Therapist", "Service", "Amount"},
            "STAR CSV",
        )
        rows = []
        for source in reader:
            if not normalized(source.get("Student Id Number")):
                continue
            rows.append(
                {
                    "sid": identifier(source["Student Id Number"]),
                    "date": service_date(source["Session Date"]),
                    "therapist": normalized(source.get("Therapist")),
                    "session_id": normalized(source.get("Session ID")),
                    "start_time": normalized(source.get("Start Time")),
                    "end_time": normalized(source.get("End Time")),
                    "service": normalized(source.get("Service")),
                    "amount": money(source["Amount"]),
                    "hours": number(source.get("Hours")),
                }
            )
    return rows


def parse_tables(path):
    parser = TableParser()
    parser.feed(Path(path).read_text(encoding="utf-8", errors="replace"))
    parser.close()
    tables = [table for table in parser.tables if table]
    if not tables:
        raise ValueError("RSM export contains no HTML tables. Export the invoice with Export → XLS.")
    return max(tables, key=len)


def find_header(table):
    for index, row in enumerate(table[:5]):
        headers = [normalized(value) for value in row]
        if "SID" in headers and any("Grand Total" in header for header in headers):
            return index, headers
    raise ValueError("Could not find RSM header row containing SID and Grand Total.")


def load_rsm(path):
    table = parse_tables(path)
    header_index, headers = find_header(table)
    required = {"SID", "Srvc Date", "Therapist", "Service", "Grand Total"}
    require_columns(headers, required, "RSM export")
    locations = {header: headers.index(header) for header in required}
    hours_index = headers.index("Hours") if "Hours" in headers else None
    status_index = headers.index("No Show?") if "No Show?" in headers else None
    rows = []
    for source in table[header_index + 1 :]:
        if len(source) <= locations["SID"] or not normalized(source[locations["SID"]]):
            continue
        values = source + [""] * max(0, len(headers) - len(source))
        rows.append(
            {
                "sid": identifier(values[locations["SID"]]),
                "date": service_date(values[locations["Srvc Date"]]),
                "therapist": normalized(values[locations["Therapist"]]),
                "service": normalized(values[locations["Service"]]),
                "amount": money(values[locations["Grand Total"]]),
                "hours": number(values[hours_index]) if hours_index is not None else None,
                "status": normalized(values[status_index]) if status_index is not None else "",
            }
        )
    return rows


def amount_value(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def row_summary(row, amount_name):
    summary = {
        "sid": row["sid"],
        "date": row["date"],
        "therapist": row["therapist"],
        "service": row["service"],
        amount_name: amount_value(row["amount"]),
    }
    if "status" in row:
        summary["status"] = row["status"]
    for field in ("session_id", "start_time", "end_time"):
        if row.get(field):
            summary[field] = row[field]
    return summary


def duplicate_star_sessions(star_rows):
    by_slot = defaultdict(list)
    unchecked = 0
    for row in star_rows:
        start = session_time(row.get("start_time"))
        end = session_time(row.get("end_time"))
        therapist = normalized(row.get("therapist")).casefold()
        if start is None or end is None or not therapist:
            unchecked += 1
            continue
        by_slot[(row["sid"], row["date"], therapist, start, end)].append(row)

    duplicates = []
    for (sid, date, _, start, end), rows in sorted(by_slot.items()):
        if len(rows) < 2:
            continue
        duplicates.append(
            {
                "sid": sid,
                "date": date,
                "therapist": rows[0]["therapist"],
                "start_time": start,
                "end_time": end,
                "star_session_count": len(rows),
                "star_sessions": [row_summary(row, "star_amount") for row in rows],
            }
        )
    return {"count": len(duplicates), "unchecked_session_count": unchecked, "rows": duplicates}


def likely_hours_rounding(star, rsm, difference):
    if star["hours"] is None or rsm["hours"] is None:
        return False
    return (
        star["hours"].quantize(CENT, rounding=ROUND_HALF_UP)
        == rsm["hours"].quantize(CENT, rounding=ROUND_HALF_UP)
        and abs(difference) < Decimal("1")
    )


def reconcile(star_rows, rsm_rows):
    star_by_key = defaultdict(list)
    rsm_by_key = defaultdict(list)
    for row in star_rows:
        star_by_key[(row["sid"], row["date"])].append(row)
    for row in rsm_rows:
        rsm_by_key[(row["sid"], row["date"])].append(row)

    star_keys = set(star_by_key)
    rsm_keys = set(rsm_by_key)
    only_in_star = []
    only_in_rsm = []
    exact_matches = []
    amount_mismatches = []
    count_mismatches = []

    for key in sorted(star_keys - rsm_keys):
        only_in_star.extend(row_summary(row, "star_amount") for row in star_by_key[key])
    for key in sorted(rsm_keys - star_keys):
        only_in_rsm.extend(row_summary(row, "rsm_amount") for row in rsm_by_key[key])

    for sid, date in sorted(star_keys & rsm_keys):
        star_group = sorted(star_by_key[(sid, date)], key=lambda row: row["amount"], reverse=True)
        rsm_group = sorted(rsm_by_key[(sid, date)], key=lambda row: row["amount"], reverse=True)
        if len(star_group) != len(rsm_group):
            count_mismatches.append(
                {
                    "sid": sid,
                    "date": date,
                    "star_session_count": len(star_group),
                    "rsm_session_count": len(rsm_group),
                    "star_amounts": [amount_value(row["amount"]) for row in star_group],
                    "rsm_amounts": [amount_value(row["amount"]) for row in rsm_group],
                    "star_services": [row["service"] for row in star_group],
                    "rsm_services": [row["service"] for row in rsm_group],
                    "star_sessions": [row_summary(row, "star_amount") for row in star_group],
                    "rsm_sessions": [row_summary(row, "rsm_amount") for row in rsm_group],
                }
            )
            continue
        for star, rsm in zip(star_group, rsm_group):
            difference = (star["amount"] - rsm["amount"]).quantize(CENT, rounding=ROUND_HALF_UP)
            record = {
                "sid": sid,
                "date": date,
                "star_amount": amount_value(star["amount"]),
                "rsm_amount": amount_value(rsm["amount"]),
                "diff": amount_value(difference),
                "star_service": star["service"],
                "rsm_service": rsm["service"],
            }
            if difference == 0:
                exact_matches.append(record)
            else:
                record["likely_hours_rounding"] = likely_hours_rounding(star, rsm, difference)
                amount_mismatches.append(record)

    star_total = sum((row["amount"] for row in star_rows), Decimal("0"))
    rsm_total = sum((row["amount"] for row in rsm_rows), Decimal("0"))
    return {
        "totals": {
            "star_total": amount_value(star_total),
            "rsm_total": amount_value(rsm_total),
            "diff": amount_value(star_total - rsm_total),
            "star_session_count": len(star_rows),
            "rsm_session_count": len(rsm_rows),
        },
        "duplicate_star_sessions": duplicate_star_sessions(star_rows),
        "exact_matches": {"count": len(exact_matches)},
        "amount_mismatches": {"count": len(amount_mismatches), "rows": amount_mismatches},
        "count_mismatches": {"count": len(count_mismatches), "rows": count_mismatches},
        "only_in_star": {"count": len(only_in_star), "rows": only_in_star},
        "only_in_rsm": {"count": len(only_in_rsm), "rows": only_in_rsm},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--star", required=True, help="Path to the STAR session-log CSV")
    parser.add_argument("--rsm", required=True, help="Path to the RSM invoice HTML .xls export")
    arguments = parser.parse_args()
    print(json.dumps(reconcile(load_star(arguments.star), load_rsm(arguments.rsm)), indent=2))


if __name__ == "__main__":
    main()
