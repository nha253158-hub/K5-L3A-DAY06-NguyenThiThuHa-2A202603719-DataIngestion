"""Chuẩn hóa RST -> văn bản thuần, tách thành "trang nội dung" (content unit), ghi manifest.

Quy tắc tính trang (ghi trong báo cáo):
  * Một "trang" = một đơn vị liên tục bắt đầu tại tiêu đề mục cấp <= 3 của tài liệu gốc.
  * Đơn vị phải có >= MIN_UNIT ký tự đã chuẩn hóa; mục ngắn hơn được gộp vào đơn vị liền trước
    (không bỏ nội dung); tài liệu tổng < MIN_UNIT ký tự bị loại và ghi log.
  * Loại: danh sách Examples/References thuần tham chiếu, toctree, ảnh/figure, mục lục.

Chạy: python3 -I src/build_corpus.py
"""
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "corpus"
MIN_UNIT = 1500
MAX_HEADING_LEVEL = 3
TAG = "1.9.1"
LICENSE = "BSD-3-Clause (scikit-learn developers); xem data/raw/COPYING"

DIRECTIVE = re.compile(r"^(\s*)\.\.\s+([A-Za-z][\w:-]*)::\s*(.*)$")
LABEL = re.compile(r"^\s*\.\.\s+_([^:`]+):\s*$")
COMMENT = re.compile(r"^(\s*)\.\.(\s.*)?$")
DROP = {"toctree", "currentmodule", "figure", "image", "plot", "include", "autosummary", "raw", "index",
        "module", "only", "highlight", "literalinclude", "rst-class", "glossary", "automodule",
        "autoclass", "autofunction", "versionmodified", "contents", "tabularcolumns", "centered",
        "prompt", "tab-set", "tab-item"}
TITLED = {"note": "Note:", "warning": "Warning:", "tip": "Tip:", "hint": "Hint:", "important": "Important:",
          "caution": "Caution:", "danger": "Danger:", "attention": "Attention:", "seealso": "See also:"}
VERSION = {"versionadded": "Added in", "versionchanged": "Changed in", "deprecated": "Deprecated since"}
BLOCK_TITLE = {"topic", "admonition", "dropdown", "rubric"}
CODE = {"code-block", "sourcecode", "code", "doctest", "testcode", "math"}
UNDERLINE_CHARS = set("=-~^\"'#*+`_.:")


def lead(s: str) -> int:
    return len(s) - len(s.lstrip(" "))


def dedent(lines):
    ind = [lead(x) for x in lines if x.strip()]
    k = min(ind) if ind else 0
    return [x[k:] if x.strip() else "" for x in lines]


def clean_directives(lines, log):
    out, i, n = [], 0, len(lines)
    while i < n:
        ln = lines[i]
        if LABEL.match(ln):
            log["labels"] += 1
            i += 1
            continue
        m = DIRECTIVE.match(ln)
        if m:
            indent, name, arg = len(m.group(1)), m.group(2).lower(), m.group(3).strip()
            j, body = i + 1, []
            while j < n and (lines[j].strip() == "" or lead(lines[j]) > indent):
                body.append(lines[j])
                j += 1
            # bỏ các dòng option (:xxx:) ở đầu body
            k = 0
            while k < len(body) and re.match(r"^\s+:[\w-]+:", body[k]):
                k += 1
            body_text = clean_directives(dedent(body[k:]), log)  # xử lý đệ quy directive lồng nhau
            i = j
            if name in DROP:
                log["dropped_directive:" + name] += 1
                continue
            if name == "rubric" and arg.lower() in {"examples", "references", "example", "reference"}:
                # danh sách thuần tham chiếu: bỏ phần body liền kề dạng bullet
                log["dropped_rubric:" + arg.lower()] += 1
                while i < n and (lines[i].strip() == "" or re.match(r"^\s*([*\-]|\d+\.|\[)", lines[i])
                                 or lead(lines[i]) > 0):
                    i += 1
                continue
            if name in TITLED:
                out += ["", TITLED[name]] + body_text + [""]
            elif name in VERSION:
                out += ["", f"{VERSION[name]} {arg}:"] + body_text + [""]
            elif name in BLOCK_TITLE:
                out += ["", arg] + body_text + [""]
            elif name in CODE:
                out += [""] + (["Math:"] if name == "math" else []) + [("    " + x) if x else x for x in (
                    [arg] + body_text if name == "math" and arg else body_text)] + [""]
            else:
                log["unknown_directive:" + name] += 1
                out += [""] + ([arg] if arg else []) + body_text + [""]
            continue
        if COMMENT.match(ln) and not ln.strip().startswith(".. ["):
            indent = len(COMMENT.match(ln).group(1))
            j = i + 1
            while j < n and (lines[j].strip() == "" or lead(lines[j]) > indent):
                j += 1
            log["comments"] += 1
            i = j
            continue
        if ln.strip().startswith(".. ["):  # định nghĩa footnote/citation: giữ như tham chiếu thô -> loại
            indent = lead(ln)
            j = i + 1
            while j < n and (lines[j].strip() == "" or lead(lines[j]) > indent):
                j += 1
            log["footnote_defs_dropped"] += 1
            i = j
            continue
        # literal block marker "::"
        if ln.rstrip().endswith("::") and not ln.strip().startswith("|"):
            ln = re.sub(r"\s*::\s*$", ":" if not ln.rstrip().endswith(" ::") else "", ln.rstrip()) or ""
            log["literal_blocks"] += 1
        out.append(ln)
        i += 1
    return out


ROLE = re.compile(r":(?:[\w+]+:)?([\w+]+):`([^`]+)`")
EXAMPLE_REFS = []


def log_example(name):
    EXAMPLE_REFS.append(name)


def sub_role(m):
    role, body = m.group(1), m.group(2).strip()
    mm = re.match(r"^(.*?)\s*<([^>]+)>$", body, re.S)
    if mm and mm.group(1):
        return mm.group(1)
    tilde = body.startswith("~")
    body = body.lstrip("~!")
    if body.startswith("sphx_glr_"):  # tham chiếu tới ví dụ trong gallery: giữ tên file ví dụ
        name = body[body.index("plot_"):] if "plot_" in body else body.replace("sphx_glr_auto_examples_", "")
        log_example(name)
        return f"(example: {name})"
    if role == "math":
        return f"${body}$"
    if role in {"class", "func", "meth", "mod", "attr", "obj", "data", "exc", "py"} and tilde and "." in body:
        return body.split(".")[-1]
    if role == "cite":
        return f"[{body}]"
    return body


def clean_inline(s: str, log) -> str:
    s, c = ROLE.subn(sub_role, s)
    log["roles_replaced"] += c
    s = re.sub(r"`([^`<]+?)\s*<[^>]+>`_{1,2}", r"\1", s)         # hyperlink có text
    s = re.sub(r"`([^`]+?)`_{1,2}", r"\1", s)                    # hyperlink tên
    s = re.sub(r"``([^`]+?)``", r"\1", s)                        # inline literal
    s = re.sub(r"`([^`]+?)`", r"\1", s)                          # interpreted text còn lại
    s = re.sub(r"\*\*([^*]+?)\*\*", r"\1", s, flags=re.S)  # in đậm, có thể kéo dài qua nhiều dòng
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = re.sub(r"\[([\w\-]+)\]_", r"[\1]", s)                    # footnote ref
    s = s.replace("\\ ", "").replace("\\*", "*")
    return s


def is_underline(s: str) -> bool:
    t = s.strip()
    return len(t) >= 3 and len(set(t)) == 1 and t[0] in UNDERLINE_CHARS and s == s.lstrip()


def split_sections(lines):
    """Trả về list section: {level, title, body[list[str]]} theo thứ tự tài liệu."""
    styles, secs = {}, []
    cur = {"level": 0, "title": "", "body": []}
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        over = i + 2 < n and is_underline(ln) and lines[i + 1].strip() and is_underline(lines[i + 2]) \
            and lines[i + 2].strip()[0] == ln.strip()[0]
        under = (not over and ln.strip() and not is_underline(ln) and i + 1 < n and is_underline(lines[i + 1])
                 and len(lines[i + 1].strip()) >= len(ln.strip()) and lead(ln) == 0)
        if over or under:
            title = lines[i + 1].strip() if over else ln.strip()
            key = (over, (ln if over else lines[i + 1]).strip()[0])
            styles.setdefault(key, len(styles) + 1)
            secs.append(cur)
            cur = {"level": styles[key], "title": title, "body": []}
            i += 3 if over else 2
            continue
        cur["body"].append(ln)
        i += 1
    secs.append(cur)
    return secs


def normalise_text(lines, log):
    txt = clean_inline("\n".join(lines), log)  # xử lý cả đoạn để role/link nhiều dòng được thay đúng
    txt = unicodedata.normalize("NFC", txt)
    txt = re.sub(r"\+[-=]{3,}(\+[-=]{3,})*\+?", "", txt)  # viền bảng dạng +----+
    txt = re.sub(r"(?m)^[ \t]*[=+\-|]{3,}[ \t=+\-|]*$", "", txt)  # dòng chỉ gồm viền bảng
    txt = re.sub(r"(?m)^[ \t]*\|[ \t|]*$", "", txt)  # dòng chỉ còn dấu |
    txt = re.sub(r"\|[A-Za-z][\w]*\|", "", txt)  # substitution ảnh như |name|
    txt = re.sub(r"[ \t]+\n", "\n", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt


def build_units(module, guide_section, text_raw, log):
    lines = clean_directives(text_raw.splitlines(), log)
    secs = split_sections(lines)
    doc_title = next((s["title"] for s in secs if s["level"] == 1), module)
    pieces = []  # (level, heading_path_title, text)
    stack = []
    for s in secs:
        body = normalise_text(s["body"], log)
        if s["level"] > 0:
            stack = stack[: s["level"] - 1] + [clean_inline(s["title"], log)]
            head = "#" * min(s["level"], 4) + " " + stack[-1]
            body = (head + "\n\n" + body).strip()
        if body.strip():
            pieces.append({"level": s["level"], "path": " > ".join(stack) if stack else doc_title, "text": body})
    units = []
    for p in pieces:
        start_new = (not units) or (p["level"] <= MAX_HEADING_LEVEL and len(units[-1]["text"]) >= MIN_UNIT)
        if start_new:
            units.append({"path": p["path"], "text": p["text"], "headings": [p["path"]]})
        else:
            units[-1]["text"] += "\n\n" + p["text"]
            units[-1]["headings"].append(p["path"])
    while len(units) > 1 and len(units[-1]["text"]) < MIN_UNIT:  # đuôi ngắn gộp ngược
        last = units.pop()
        units[-1]["text"] += "\n\n" + last["text"]
        units[-1]["headings"] += last["headings"]
    return doc_title, units


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fetch = {r["source_id"]: r for r in csv.DictReader(open(ROOT / "data" / "fetch_log.csv", encoding="utf-8"))}
    mapping = list(csv.DictReader(open(ROOT / "data" / "guide_mapping.csv", encoding="utf-8")))
    manifest, all_units, nlog, excluded = [], [], [], []
    for item in mapping:
        mod = item["module"]
        path = RAW / "modules" / f"{mod}.rst"
        raw = path.read_text(encoding="utf-8")
        log = Counter()
        title, units = build_units(mod, item["guide_section"], raw, log)
        total = sum(len(u["text"]) for u in units)
        f = fetch[f"doc/modules/{mod}.rst"]
        if total < MIN_UNIT:
            excluded.append((mod, f"tổng {total} ký tự < {MIN_UNIT}"))
            nlog.append({"doc_id": mod, "note": "EXCLUDED", **dict(log)})
            continue
        page_ids = []
        for k, u in enumerate(units):
            uid = f"{mod}:{k:03d}"
            page_ids.append(uid)
            all_units.append({
                "unit_id": uid, "doc_id": mod, "doc_title": title, "guide_section": item["guide_section"],
                "heading_path": u["path"], "headings": u["headings"], "index_in_doc": k,
                "source": f"https://github.com/scikit-learn/scikit-learn/blob/{TAG}/doc/modules/{mod}.rst",
                "char_count": len(u["text"]), "text": u["text"],
            })
        manifest.append({
            "source_id": mod, "title": title, "source_path_or_url": f["url"],
            "license_or_permission": LICENSE, "accessed_at": f["accessed_at"], "snapshot_version": f"scikit-learn {TAG}",
            "guide_section": item["guide_section"], "n_pages": len(units),
            "page_ids": ";".join(page_ids), "normalized_char_count": total,
            "raw_sha256": f["sha256"],
            "page_rule": f"unit bắt đầu tại tiêu đề cấp<={MAX_HEADING_LEVEL}, >= {MIN_UNIT} ký tự chuẩn hóa",
        })
        nlog.append({"doc_id": mod, "raw_chars": len(raw), "normalized_chars": total, "units": len(units), **dict(log)})
    with open(OUT / "units.jsonl", "w", encoding="utf-8") as fo:
        for u in all_units:
            fo.write(json.dumps(u, ensure_ascii=False) + "\n")
    with open(ROOT / "data" / "manifest.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(manifest[0].keys()))
        w.writeheader()
        w.writerows(manifest)
    keys = sorted({k for r in nlog for k in r})
    with open(ROOT / "results" / "normalization_log.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=["doc_id"] + [k for k in keys if k != "doc_id"], restval=0)
        w.writeheader()
        w.writerows(nlog)
    sizes = [u["char_count"] for u in all_units]
    stats = {
        "docs_kept": len(manifest), "docs_excluded": excluded, "pages": len(all_units),
        "pages_ge_1500": sum(s >= MIN_UNIT for s in sizes), "min_chars": min(sizes), "max_chars": max(sizes),
        "total_chars": sum(sizes), "pages_by_guide_section": dict(Counter(u["guide_section"] for u in all_units)),
        "sha256_units": hashlib.sha256("".join(u["text"] for u in all_units).encode()).hexdigest(),
    }
    (ROOT / "results" / "corpus_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
