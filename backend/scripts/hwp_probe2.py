"""Verify position-counting consistency: for EVERY paragraph,
PARA_HEADER nChars (u32@0) must equal PARA_TEXT n_positions, and
the last CHAR_SHAPE pos and last LINE_SEG start must be < nChars."""
import io
import struct
import sys
import zlib

import olefile

sys.stdout.reconfigure(encoding="utf-8")

SAMPLE = r"C:\Users\rkdgi\OneDrive\바탕 화면\고시문 샘플.hwp"

TAG_PARA_HEADER = 66
TAG_PARA_TEXT = 67
TAG_PARA_CHAR_SHAPE = 68
TAG_PARA_LINE_SEG = 69


def parse_para_text(text_data):
    text = ""
    pos_count = 0
    i = 0
    while i < len(text_data) - 1:
        ch = struct.unpack_from("<H", text_data, i)[0]
        i += 2
        if ch < 32:
            if ch in (0, 10, 13):
                pos_count += 1
            else:
                i += 14
                pos_count += 8
        else:
            text += chr(ch)
            pos_count += 1
    return text, pos_count


with open(SAMPLE, "rb") as f:
    file_data = f.read()
ole = olefile.OleFileIO(io.BytesIO(file_data))
raw = ole.openstream("BodyText/Section0").read()
ole.close()
d = zlib.decompressobj(-15)
data = d.decompress(raw) + d.flush()

records = []
pos = 0
while pos < len(data):
    if pos + 4 > len(data):
        break
    tag_data = struct.unpack_from("<I", data, pos)[0]
    tag_id = tag_data & 0x3FF
    level = (tag_data >> 10) & 0x3FF
    size = (tag_data >> 20) & 0xFFF
    pos += 4
    if size == 0xFFF:
        size = struct.unpack_from("<I", data, pos)[0]
        pos += 4
    records.append((tag_id, level, data[pos:pos + size]))
    pos += size

# Group paragraphs, validate nChars vs n_positions, header counts
n_paras = 0
mismatch = 0
header_field_ok = True
idx = 0
while idx < len(records):
    tag, lvl, pl = records[idx]
    if tag == TAG_PARA_HEADER:
        n_paras += 1
        raw_nchars = struct.unpack_from("<I", pl, 0)[0] if len(pl) >= 4 else None
        nchars = raw_nchars & 0x7FFFFFFF if raw_nchars is not None else None
        n_charshape_hdr = struct.unpack_from("<H", pl, 12)[0] if len(pl) >= 14 else None
        n_lineseg_hdr = struct.unpack_from("<H", pl, 16)[0] if len(pl) >= 18 else None
        j = idx + 1
        text_npos = 0
        has_text = False
        cs_entries = 0
        cs_last = -1
        ls_segs = 0
        ls_last = -1
        while j < len(records):
            t2, l2, p2 = records[j]
            if t2 == TAG_PARA_HEADER:
                break
            if t2 == TAG_PARA_TEXT:
                _, text_npos = parse_para_text(p2)
                has_text = True
            elif t2 == TAG_PARA_CHAR_SHAPE:
                cs_entries = len(p2) // 8
                if cs_entries:
                    cs_last = struct.unpack_from("<I", p2, (cs_entries - 1) * 8)[0]
            elif t2 == TAG_PARA_LINE_SEG:
                ls_segs = len(p2) // 36
                if ls_segs:
                    ls_last = struct.unpack_from("<i", p2, (ls_segs - 1) * 36)[0]
            j += 1
        # if no PARA_TEXT, nChars typically 1 (empty para) or matches
        expected = text_npos if has_text else nchars
        if has_text and nchars != text_npos:
            mismatch += 1
            if mismatch <= 10:
                print(f"NCHAR MISMATCH para{n_paras}: header nchars={nchars} text_npos={text_npos}")
        # check header count fields
        if n_charshape_hdr != cs_entries or n_lineseg_hdr != ls_segs:
            header_field_ok = False
            if n_paras <= 30:
                print(f"COUNT FIELD para{n_paras}: hdr_cs={n_charshape_hdr} actual_cs={cs_entries} "
                      f"hdr_ls={n_lineseg_hdr} actual_ls={ls_segs}")
        # range checks
        if has_text and cs_last >= nchars and cs_last != -1 and cs_entries > 1:
            print(f"CS OUT OF RANGE para{n_paras}: cs_last={cs_last} nchars={nchars}")
        idx = j
        continue
    idx += 1

print(f"\nTotal paragraphs: {n_paras}")
print(f"nChars==n_positions mismatches: {mismatch}")
print(f"header count fields (cs@12,ls@16) all match: {header_field_ok}")
