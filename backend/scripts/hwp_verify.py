"""Verify length-changing HWP replacement keeps metadata consistent.

Checks:
  1. Result Section0 decompresses cleanly with unused_data == 8-byte trailer,
     and trailer CRC/len match the new decompressed content.
  2. extract_tables still returns 50 tables.
  3. get_text_content reflects the replacement.
  4. For each edited paragraph: PARA_HEADER nChars == PARA_TEXT n_positions,
     and last CHAR_SHAPE pos < nChars (no out-of-range).
"""
import asyncio
import io
import struct
import sys
import zlib

import olefile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\dev\workspace\doc-replacer\backend")

from app.services.hwp_service import HwpService

SAMPLE = r"C:\Users\rkdgi\OneDrive\바탕 화면\고시문 샘플.hwp"


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


def section0(file_data):
    ole = olefile.OleFileIO(io.BytesIO(file_data))
    raw = ole.openstream("BodyText/Section0").read()
    ole.close()
    return raw


def check_stream(raw, label):
    d = zlib.decompressobj(-15)
    data = d.decompress(raw) + d.flush()
    trailer = d.unused_data
    print(f"[{label}] decompressed {len(data)}B, trailer {len(trailer)}B")
    ok = True
    if len(trailer) == 8:
        crc, ln = struct.unpack("<II", trailer)
        exp_crc = zlib.crc32(data) & 0xFFFFFFFF
        if crc != exp_crc:
            print(f"  TRAILER CRC MISMATCH: {crc:#x} != {exp_crc:#x}"); ok = False
        if ln != len(data):
            print(f"  TRAILER LEN MISMATCH: {ln} != {len(data)}"); ok = False
        if ok:
            print(f"  trailer CRC/len OK (crc={crc:#x} len={ln})")
    elif len(trailer) != 0:
        print(f"  UNEXPECTED trailer length {len(trailer)}"); ok = False
    return data, ok


def validate_paragraphs(data, label):
    recs = []
    pos = 0
    while pos < len(data):
        if pos + 4 > len(data):
            break
        td = struct.unpack_from("<I", data, pos)[0]
        tid = td & 0x3FF
        lv = (td >> 10) & 0x3FF
        sz = (td >> 20) & 0xFFF
        pos += 4
        if sz == 0xFFF:
            sz = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        recs.append((tid, lv, data[pos:pos + sz]))
        pos += sz

    mismatch = 0
    cs_oor = 0
    ls_oor = 0
    idx = 0
    while idx < len(recs):
        tid, lv, pl = recs[idx]
        if tid == 66:
            nchars = struct.unpack_from("<I", pl, 0)[0] & 0x7FFFFFFF
            j = idx + 1
            tpos = None
            cs_last = -1
            ls_last = -1
            cs_n = 0
            while j < len(recs) and recs[j][0] != 66:
                t2, _, p2 = recs[j]
                if t2 == 67:
                    _, tpos = parse_para_text(p2)
                elif t2 == 68:
                    cs_n = len(p2) // 8
                    if cs_n:
                        cs_last = struct.unpack_from("<I", p2, (cs_n - 1) * 8)[0]
                elif t2 == 69:
                    ns = len(p2) // 36
                    if ns:
                        ls_last = struct.unpack_from("<i", p2, (ns - 1) * 36)[0]
                j += 1
            if tpos is not None:
                if nchars != tpos:
                    mismatch += 1
                if cs_last >= nchars and cs_n > 1:
                    cs_oor += 1
                if ls_last >= nchars and ls_last != -1:
                    ls_oor += 1
            idx = j
            continue
        idx += 1
    print(f"[{label}] nChars!=npos: {mismatch}, CHAR_SHAPE out-of-range: {cs_oor}, "
          f"LINE_SEG start>=nChars: {ls_oor}")
    return mismatch, cs_oor, ls_oor


async def main():
    svc = HwpService()
    orig = open(SAMPLE, "rb").read()

    # baseline
    orig_data, _ = check_stream(section0(orig), "ORIG")
    base_mis, _, _ = validate_paragraphs(orig_data, "ORIG")
    orig_tables = await svc.extract_tables(orig, "hwp")
    print("ORIG tables:", len(orig_tables))

    # Apply a chain of length-changing + same-length replacements.
    pairs = [
        ("69.1", "69"),    # 4 -> 2 (shrink)
        ("28.9", "29"),    # 4 -> 2 (shrink)
        ("15", "15.2"),    # 2 -> 4 (grow)
    ]
    cur = orig
    total = 0
    for old, new in pairs:
        cur, n = svc.replace_text(cur, old, new, case_sensitive=True, file_type="hwp")
        print(f"replace {old!r}->{new!r}: {n} hits")
        total += n
    print("total replaced:", total)

    mod_data, stream_ok = check_stream(section0(cur), "MOD")
    mis, cs_oor, ls_oor = validate_paragraphs(mod_data, "MOD")
    mod_tables = await svc.extract_tables(cur, "hwp")
    print("MOD tables:", len(mod_tables))
    text = await svc.get_text_content(cur, "hwp")
    for old, new in pairs:
        print(f"  text contains {new!r}:", new in text)

    print("\n=== SUMMARY ===")
    print("stream valid (unused_data==trailer, crc/len ok):", stream_ok)
    print("tables 50 preserved:", len(mod_tables) == 50, f"({len(mod_tables)})")
    print("new-mismatches beyond baseline:", mis - base_mis)
    print("CHAR_SHAPE out-of-range:", cs_oor)

    # Save the Korean-verification file
    out_path = r"C:\Users\rkdgi\OneDrive\바탕 화면\고시문 샘플_길이변경테스트.hwp"
    with open(out_path, "wb") as f:
        f.write(cur)
    print("saved:", out_path)

    # Regression: same-length replacement still clean
    same, n2 = svc.replace_text(orig, "동두천", "동두천", case_sensitive=True, file_type="hwp")
    sd, sok = check_stream(section0(same), "SAME-LEN")
    sm, _, _ = validate_paragraphs(sd, "SAME-LEN")
    print("same-length regression stream ok:", sok, "mismatch delta:", sm - base_mis)


if __name__ == "__main__":
    asyncio.run(main())
