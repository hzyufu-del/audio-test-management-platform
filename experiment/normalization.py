"""Frozen literal-transcription-v1 parser; no scoring or business enrichment."""

import json
import re
from collections import Counter
from pathlib import Path

FIELDS = (
    "suggested_code", "title", "module", "priority", "case_type", "scenario_type",
    "precondition", "steps", "expected_result",
)

def literal(value):
    """Strip presentation at a cell/label edge, never invent field content."""
    value = value.strip()
    if (value.startswith("**") and value.endswith("**")) or (
            value.startswith("__") and value.endswith("__")):
        value = value[2:-2].strip()
    return value


def converted(raw, field, rules):
    if raw is None:
        return None, [], False
    if not isinstance(raw, str):
        return None, ["unsupported_value_type_retained_in_private_source"], False
    value = raw.strip()
    changes = ["trim_field_edge_whitespace"] if value != raw else []
    if not value:
        return None, changes, False
    # Preserve codes, enum terminology, case, Markdown and step numbering.
    return value, changes, field in {"priority", "case_type", "scenario_type"}


def spans(indices, lines):
    groups = []
    for index in sorted(indices):
        number = index + 1
        if groups and number == groups[-1]["end"] + 1:
            groups[-1]["end"] = number
        else:
            groups.append({"start": number, "end": number})
    return [{**item, "source_text": "".join(lines[item["start"] - 1:item["end"]])}
            for item in groups]


def finalize_case(occurrences, index, raw_case, source_span):
    missing = [field for field in FIELDS if not occurrences[field] or (
        len(occurrences[field]) == 1 and occurrences[field][0]["converted_value"] is None)]
    ambiguous = [field for field in FIELDS if len(occurrences[field]) > 1]
    values = {field: occurrences[field][0]["converted_value"]
              if len(occurrences[field]) == 1 else None for field in FIELDS}
    return {"case_index": index, "source_line_span": source_span,
            "raw_case_text": raw_case, "raw_fields": occurrences,
            "converted_nine_fields": values,
            "missing_fields": missing, "ambiguous_fields": ambiguous}


def parse_table(line):
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    # An escaped pipe is retained in its own cell; it is not a column boundary.
    return re.split(r"(?<!\\)\|", line[1:-1])


def transcription(text, rules):
    """Only explicit labels/case boundaries/table headers. Retain every span."""
    lines = text.splitlines(keepends=True)
    label_names = "|".join(re.escape(label) for label in
                           sorted(rules["label_map"], key=len, reverse=True))
    label_pattern = re.compile(
        r"^\s*(?:[-*+]\s+|\d+[.)、]\s+)?(?:\*\*|__)?"
        rf"(?P<label>{label_names})(?:\*\*|__)?\s*[：:]"
        r"(?:\*\*|__)?\s*(?P<value>.*)$")
    heading_pattern = re.compile(
        r"^\s*(?:#{1,6}\s*)?(?:\*\*|__)?"
        r"(?:用例\s*\d+|测试用例\s*\d+|(?:Test\s+)?Case\s+\d+|"
        r"\d+[.)、]\s*(?:测试)?用例)(?:\*\*|__)?(?:\s*[：:].*|\s*)$",
        re.IGNORECASE)
    numbered_markdown_heading = re.compile(
        r"^\s*(?:#{1,6}\s+|\*\*|__)\s*\d+[.)、:：]\s+\S.*$")
    unknown_label = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*)?[\w\u4e00-\u9fff ]{1,40}[：:]")
    used, presentation = set(), set()
    cases, unknown = [], Counter()
    table_indices = set()
    # Labeled Markdown tables: each row is an explicit case. Unknown cells stay
    # in the raw row and are explicitly recorded; duplicate headers are ambiguous.
    for i in range(max(0, len(lines) - 1)):
        header = parse_table(lines[i])
        divider = parse_table(lines[i + 1])
        if not header or not divider or len(header) != len(divider):
            continue
        if not all(re.fullmatch(r"\s*:?-{3,}:?\s*", cell) for cell in divider):
            continue
        labels = [literal(cell) for cell in header]
        if not any(label in rules["label_map"] for label in labels):
            continue
        presentation.update({i, i + 1})
        table_indices.update({i, i + 1})
        j = i + 2
        while j < len(lines):
            cells = parse_table(lines[j])
            if cells is None:
                break
            table_indices.add(j)
            if len(cells) != len(labels):
                j += 1
                continue
            occurrences = {field: [] for field in FIELDS}
            unparsed_cells = []
            for column, (label, raw) in enumerate(zip(labels, cells), 1):
                field = rules["label_map"].get(label)
                if field is None:
                    unparsed_cells.append({"column": column, "header": label,
                                           "raw_cell_text": raw})
                    continue
                value, operations, unmapped = converted(raw, field, rules)
                if unmapped:
                    unknown[(field, value)] += 1
                occurrences[field].append({"source_label": label, "source_column": column,
                    "source_line_span": {"start": j + 1, "end": j + 1},
                    "source_text": lines[j], "raw_value_text": raw,
                    "converted_value": value, "operations": operations,
                    "unmapped_literal": unmapped})
            case = finalize_case(occurrences, 0, lines[j], {"start": j + 1, "end": j + 1})
            case["unparsed_cells"] = unparsed_cells
            cases.append(case)
            used.add(j)
            j += 1
    matches = {i: label_pattern.match(line.rstrip("\r\n"))
               for i, line in enumerate(lines) if i not in table_indices}
    matches = {i: match for i, match in matches.items() if match}
    headings = [i for i, line in enumerate(lines) if i not in table_indices
                and (heading_pattern.fullmatch(line.rstrip("\r\n"))
                     or numbered_markdown_heading.fullmatch(line.rstrip("\r\n")))]
    starts = set(headings)
    # A first/repeated explicit code field provides a boundary when there is no
    # active numbered heading, or another code already occurred in that heading.
    active_code = False
    for i in sorted(set(headings) | set(matches)):
        if i in headings:
            active_code = False
        elif rules["label_map"][matches[i]["label"]] == "suggested_code":
            if not starts or active_code or not any(h <= i for h in headings):
                starts.add(i)
            active_code = True
    starts = sorted(starts)
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        occurrences = {field: [] for field in FIELDS}
        field_lines = sorted(i for i in matches if start <= i < end)
        for n, line_index in enumerate(field_lines):
            match = matches[line_index]
            field = rules["label_map"][match["label"]]
            limit = field_lines[n + 1] if n + 1 < len(field_lines) else end
            content_end = line_index + 1
            # Scalar fields never swallow unlabeled later text. Explicit free
            # text fields accept continuation until an unknown label/table/header
            # or a blank/separator. The untouched remainder stays unparsed.
            if field in {"precondition", "steps", "expected_result"}:
                while content_end < limit:
                    candidate = lines[content_end]
                    if (content_end in table_indices or content_end in headings
                            or not candidate.strip() or re.fullmatch(r"\s*---\s*", candidate)
                            or unknown_label.match(candidate)):
                        break
                    content_end += 1
            first = lines[line_index].rstrip("\r\n")[match.start("value"):]
            continuation = "".join(lines[line_index + 1:content_end])
            raw = first + ("\n" + continuation if continuation else "")
            value, operations, unmapped = converted(raw, field, rules)
            if unmapped:
                unknown[(field, value)] += 1
            occurrences[field].append({"source_label": match["label"],
                "source_line_span": {"start": line_index + 1, "end": content_end},
                "source_text": "".join(lines[line_index:content_end]),
                "raw_value_text": raw, "converted_value": value,
                "operations": ["explicit_label_mapping"] + operations,
                "unmapped_literal": unmapped})
            used.update(range(line_index, content_end))
        if start in headings:
            presentation.add(start)
        # A heading enclosing an already parsed table is a presentation container,
        # not an extra empty case. Its exact line is retained as presentation.
        if not field_lines and any(start < index < end for index in used & table_indices):
            continue
        # Keep explicit empty cases. Their nine fields remain null.
        cases.append(finalize_case(occurrences, 0, "".join(lines[start:end]),
                                   {"start": start + 1, "end": end}))
    for i, line in enumerate(lines):
        if not line.strip() or re.fullmatch(r"\s*---\s*", line):
            presentation.add(i)
    cases.sort(key=lambda case: case["source_line_span"]["start"])
    for i, case in enumerate(cases, 1):
        case["case_index"] = i
    unparsed = set(range(len(lines))) - used - presentation
    result = {"case_count": len(cases), "cases": cases,
              "missing_field_count": sum(len(c["missing_fields"]) for c in cases),
              "ambiguous_field_count": sum(len(c["ambiguous_fields"]) for c in cases),
              "unmapped_value_count": sum(unknown.values()),
              "unmapped_values": [{"field": field, "literal": value, "occurrences": count}
                                  for (field, value), count in sorted(unknown.items())],
              "unparsed_spans": spans(unparsed, lines),
              "presentation_spans": spans(presentation - used, lines),
              "raw_initial_text": text,
              "parse_status": "parsed" if cases else "no_explicit_case_boundaries"}
    if unparsed and cases:
        result["parse_status"] = "parsed_with_unparsed_spans"
    return result

def transcribe(text):
    """Retain exact raw and source lines, projecting only explicit labels."""
    if not isinstance(text, str):
        raise TypeError("Transcription requires text.")
    rules = json.loads(Path(__file__).with_name("normalization_policy.json").read_text(encoding="utf-8"))
    log = transcription(text, rules)
    normalized = [case["converted_nine_fields"] for case in log["cases"]]
    usable = any(any(value is not None for value in case.values()) for case in normalized)
    return {"raw": text, "normalized": normalized, "conversion_log": log, "usable": usable}
