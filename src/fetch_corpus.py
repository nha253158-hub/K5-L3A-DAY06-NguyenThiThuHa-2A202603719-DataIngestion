"""Tải corpus: scikit-learn User Guide (RST) tại tag cố định, ghi log truy cập.

Nguồn : https://github.com/scikit-learn/scikit-learn (tag TAG), thư mục doc/
Quyền : BSD-3-Clause (xem data/raw/COPYING) - cho phép tái phân phối kèm thông báo bản quyền.
Mapping tài liệu -> mục guide được ĐỌC từ các file toctree của chính User Guide
(supervised_learning.rst, ...), không tự đặt tay.

Chạy: python3 -I src/fetch_corpus.py
"""
import csv
import hashlib
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TAG = "1.9.1"
BASE = f"https://raw.githubusercontent.com/scikit-learn/scikit-learn/{TAG}"
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
GUIDE_FILES = [
    "supervised_learning.rst",
    "unsupervised_learning.rst",
    "model_selection.rst",
    "data_transforms.rst",
    "inspection.rst",
]


def get(url: str) -> bytes:
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception as e:  # ghi lỗi, thử lại, không âm thầm bỏ qua
            last = e
            print(f"  lỗi {url}: {e} (lần {attempt + 1}/3)", file=sys.stderr)
            time.sleep(2)
    raise RuntimeError(f"Không tải được {url}: {last}")


def parse_toctree(text: str):
    """Trả về (tiêu đề mục, [tên module]) từ một file mục của User Guide."""
    lines = text.splitlines()
    title = None
    for i, ln in enumerate(lines[:-1]):
        nxt = lines[i + 1]
        if ln.strip() and nxt and set(nxt.strip()) <= set("-=~") and len(nxt.strip()) >= 3:
            title = ln.strip()
            break
    mods, in_tree = [], False
    for ln in lines:
        if ln.startswith(".. toctree::"):
            in_tree = True
            continue
        if in_tree:
            s = ln.strip()
            if not s or s.startswith(":"):
                continue
            if not ln.startswith(" "):
                in_tree = False
                continue
            m = re.match(r"modules/([\w]+)(\.rst)?$", s)
            if m:
                mods.append(m.group(1))
    return title, mods


def main():
    RAW.joinpath("modules").mkdir(parents=True, exist_ok=True)
    rows, mapping = [], []
    now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")

    def fetch(rel: str, dest: Path):
        url = f"{BASE}/{rel}"
        data = get(url)
        dest.write_bytes(data)
        rows.append({
            "source_id": rel, "url": url, "tag": TAG, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), "accessed_at": now(),
        })
        return data

    fetch("COPYING", RAW / "COPYING")
    for gf in GUIDE_FILES:
        data = fetch(f"doc/{gf}", RAW / f"doc_{gf}").decode("utf-8")
        title, mods = parse_toctree(data)
        for m in mods:
            mapping.append({"module": m, "guide_section": title, "guide_file": gf})
    for item in mapping:
        fetch(f"doc/modules/{item['module']}.rst", RAW / "modules" / f"{item['module']}.rst")
        print("ok", item["module"], "->", item["guide_section"])

    with open(ROOT / "data" / "fetch_log.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(ROOT / "data" / "guide_mapping.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["module", "guide_section", "guide_file"])
        w.writeheader()
        w.writerows(mapping)
    print(f"Xong: {len(mapping)} module, {len(rows)} file. Log: data/fetch_log.csv")


if __name__ == "__main__":
    main()
