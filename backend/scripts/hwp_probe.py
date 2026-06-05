"""Probe HWP binary record structure to measure exact offsets for
PARA_HEADER nChars, CHAR_SHAPE entries, and LINE_SEG segments."""
import io
import struct
import sys
import zlib

import olefile

sys.stdout.reconfigure(encoding="utf-8")

SAMPLE = "/c/Users/rkdgi/OneDrive/바탕 화면/고시문 샘플.hwp".replace("/c/", "C:/", 1).replace("/", "\\")

TAG_PARA_HEADER = 66
TAG_PARA_TEXT = 67
TAG_PARA_CHAR_SHAPE = 68
TAG_PARA_LINE_SEG = 69

TAGNAMES = {66: "PARA_HEADER", 67: "PARA_TEXT", 68: "CHAR_SHAPE", 69: "LINE_SEG"}


def is_compressed(file_data):
    ole = olefile.OleFileIO(io.BytesIO(file_data))
    try:
        header = ole.openstream("FileHeader").read()
        props = struct.unpack_from("<I", header, 36)[0]
        return bool(props & 1)
    finally:
        ole.close()


def parse_para_text(text_data):
    """Return (string, n_positions). n_positions counts WCHAR positions
    including control chars (control = 1 position each in HWP position units,
    but extended controls occupy 8 positions: 7 from 14-byte payload + 1)."""
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
                pos_count += 8  # 1 (control) + 7 (14 bytes / 2)
        else:
            text += chr(ch)
            pos_count += 1
    return text, pos_count


def main():
    with open(SAMPLE, "rb") as f:
        file_data = f.read()
    compressed = is_compressed(file_data)
    ole = olefile.OleFileIO(io.BytesIO(file_data))
    streams = sorted(
        "/".join(e) for e in ole.listdir()
        if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")
    )
    print("compressed:", compressed, "sections:", streams)
    raw = ole.openstream(streams[0]).read()
    ole.close()
    if compressed:
        d = zlib.decompressobj(-15)
        data = d.decompress(raw) + d.flush()
        print("unused_data len:", len(d.unused_data))
    else:
        data = raw

    # Walk records, group into paragraphs
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

    print("total records:", len(records))

    # Print first several paragraphs (PARA_HEADER...) with their meta
    shown = 0
    idx = 0
    while idx < len(records) and shown < 12:
        tag, lvl, pl = records[idx]
        if tag == TAG_PARA_HEADER:
            print("\n=== PARA_HEADER idx", idx, "level", lvl, "payloadlen", len(pl), "===")
            # dump first 24 bytes as u32 little endian
            maxo = (len(pl) // 4) * 4
            u32s = [struct.unpack_from("<I", pl, o)[0] for o in range(0, maxo, 4)]
            print("  header u32[0..]:", u32s)
            u16s = [struct.unpack_from("<H", pl, o)[0] for o in range(0, (len(pl) // 2) * 2, 2)]
            print("  header u16[0..]:", u16s)
            # collect this para's group
            j = idx + 1
            para_text = None
            ntext_pos = None
            while j < len(records):
                t2, l2, p2 = records[j]
                if t2 == TAG_PARA_HEADER:
                    break
                if t2 == TAG_PARA_TEXT:
                    s, npos = parse_para_text(p2)
                    para_text = s
                    ntext_pos = npos
                    print("  PARA_TEXT idx", j, "payloadlen", len(p2),
                          "n_positions", npos, "text=", repr(s[:60]))
                elif t2 == TAG_PARA_CHAR_SHAPE:
                    n_entries = len(p2) // 8
                    entries = [struct.unpack_from("<II", p2, k * 8) for k in range(n_entries)]
                    print("  CHAR_SHAPE idx", j, "payloadlen", len(p2),
                          "n_entries", n_entries, "entries(pos,id)=", entries)
                elif t2 == TAG_PARA_LINE_SEG:
                    # LINE_SEG stride is typically 36 bytes per segment in HWP5
                    for stride in (36, 32, 28):
                        if len(p2) % stride == 0:
                            break
                    n_seg = len(p2) // stride if stride else 0
                    print("  LINE_SEG idx", j, "payloadlen", len(p2),
                          "guess_stride", stride, "n_seg", n_seg)
                    # dump each segment's first two u32 (textpos, ...)
                    for k in range(min(n_seg, 6)):
                        seg = p2[k * stride:(k + 1) * stride]
                        head = [struct.unpack_from("<i", seg, o)[0] for o in range(0, min(len(seg), 16), 4)]
                        print("      seg", k, "i32[0..3]:", head)
                j += 1
            shown += 1
            idx = j
            continue
        idx += 1


if __name__ == "__main__":
    main()
