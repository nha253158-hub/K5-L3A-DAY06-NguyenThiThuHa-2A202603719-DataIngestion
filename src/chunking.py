"""Hai chiến lược chunk. Mọi chunk là một lát cắt LIÊN TỤC của văn bản trang (unit) nên giữ được
offset (char_start, char_end) để truy vết và để kiểm tra evidence.

  A: fixed_size   - cửa sổ cố định 500 ký tự, overlap 50, không quan tâm ranh giới ý.
  B: heading_para - tôn trọng heading và đoạn văn; gộp đoạn tới ~target ký tự, không cắt giữa đoạn
                    trừ khi đoạn > max_chars (khi đó tách theo câu).
  C dùng lại chunk/chỉ mục của B; khác biệt duy nhất là filter metadata lúc truy vấn.
"""
import hashlib
import re
from dataclasses import dataclass

PARAMS = {
    "A": {"strategy": "fixed_size", "size": 500, "overlap": 50},
    "B": {"strategy": "heading_paragraph", "target": 600, "max_chars": 1000, "min_chars": 120},
}
HEADING = re.compile(r"(?m)^(#{1,4}) (.+)$")
PARA = re.compile(r"\S[\s\S]*?(?=\n[ \t]*\n|\Z)")
SENT_END = re.compile(r"(?<=[.!?:])\s+(?=[A-Z$(\[`\"'])")


@dataclass
class Chunk:
    chunk_id: str
    config: str
    unit_id: str
    doc_id: str
    char_start: int
    char_end: int
    text: str
    section_heading: str
    text_sha256: str


def chunk_fixed(text: str, size: int = 500, overlap: int = 50):
    spans, step, i = [], size - overlap, 0
    while i < len(text):
        j = min(i + size, len(text))
        if text[i:j].strip():
            spans.append((i, j))
        if j >= len(text):
            break
        i += step
    return spans


def _kind(block: str) -> str:
    if block.startswith("#"):
        return "heading"
    if block.startswith(("    ", "Math:", ">>>", "  >>>")):
        return "code"  # đính vào đoạn liền trước, không tách khỏi lời dẫn
    return "para"


def _pack(cuts, length, target):
    """Gộp tham lam theo các điểm cắt cho phép sao cho mỗi mảnh <= target khi có thể."""
    pieces, start, last = [], 0, None
    for c in sorted(set(cuts)) + [length]:
        if c - start > target and last is not None and last > start:
            pieces.append((start, last))
            start = last
        last = c
    pieces.append((start, length))
    return pieces


def _split_oversize(text: str, s: int, e: int, target: int, max_chars: int):
    """Tách một khối quá dài, vẫn là các lát liên tục không overlap.
    Ưu tiên ranh giới CÂU; chỉ khi một mảnh vẫn > max_chars (code/công thức không có ranh giới câu)
    mới dùng ranh giới DÒNG, cuối cùng mới cắt cứng. (v0 dùng xuống dòng ngay từ đầu nên cắt giữa câu - đã sửa.)"""
    seg = text[s:e]
    levels = [[m.end() for m in SENT_END.finditer(seg)], [m.end() for m in re.finditer(r"\n", seg)]]
    pieces = [(0, len(seg))]
    for cuts in levels:
        nxt = []
        for a, b in pieces:
            if b - a <= max_chars:
                nxt.append((a, b))
                continue
            sub = [c - a for c in cuts if a < c < b]
            nxt += [(a + x, a + y) for x, y in _pack(sub, b - a, target)]
        pieces = nxt
    out = []
    for a, b in pieces:  # cắt cứng nếu vẫn dài hơn max_chars
        while b - a > max_chars:
            out.append((a, a + max_chars))
            a += max_chars
        if seg[a:b].strip():
            out.append((a, b))
    return [(s + a, s + b) for a, b in out]


def chunk_heading_paragraph(text: str, target: int = 600, max_chars: int = 1000, min_chars: int = 120):
    blocks = [(m.start(), m.end(), _kind(m.group())) for m in PARA.finditer(text)]
    spans, cur = [], None
    for s, e, kind in blocks:
        if cur is None:
            cur = [s, e]
            continue
        cur_len = cur[1] - cur[0]
        if kind == "heading":
            if cur_len >= min_chars:
                spans.append(tuple(cur))
                cur = [s, e]
            else:
                cur[1] = e
        elif kind == "code":
            cur[1] = e
        else:
            if e - cur[0] > target and cur_len >= min_chars:
                spans.append(tuple(cur))
                cur = [s, e]
            else:
                cur[1] = e
    if cur:
        spans.append(tuple(cur))
    final = []
    for s, e in spans:
        if e - s > max_chars:
            final += _split_oversize(text, s, e, target, max_chars)
        else:
            final.append((s, e))
    # gộp chunk đuôi quá ngắn vào chunk trước nếu không vượt max_chars
    merged = []
    for s, e in final:
        if merged and (e - s) < min_chars // 2 and (e - merged[-1][0]) <= max_chars:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def nearest_heading(text: str, pos: int, fallback: str) -> str:
    last = fallback
    for m in HEADING.finditer(text):
        if m.start() <= pos:
            last = m.group(2).strip()
        else:
            break
    return last


def make_chunks(unit: dict, config: str):
    text = unit["text"]
    p = PARAMS["A" if config == "A" else "B"]
    spans = chunk_fixed(text, p["size"], p["overlap"]) if config == "A" else \
        chunk_heading_paragraph(text, p["target"], p["max_chars"], p["min_chars"])
    fb = unit["heading_path"].split(" > ")[-1]
    out = []
    for k, (s, e) in enumerate(spans):
        t = text[s:e]
        out.append(Chunk(
            chunk_id=f"{config}:{unit['unit_id']}:{k:03d}", config=config, unit_id=unit["unit_id"],
            doc_id=unit["doc_id"], char_start=s, char_end=e, text=t,
            section_heading=nearest_heading(text, s, fb), text_sha256=hashlib.sha256(t.encode("utf-8")).hexdigest(),
        ))
    return out


def norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
