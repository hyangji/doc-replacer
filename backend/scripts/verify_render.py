"""렌더 함수 검증: 샘플 HWP → HTML 저장 + <table>/<p> 개수 출력."""
import sys

sys.path.insert(0, r"C:/dev/workspace/doc-replacer/backend")

from app.services.hwp_service import render_hwp_to_html

PATH = r"C:/Users/rkdgi/OneDrive/바탕 화면/고시문 샘플.hwp"
OUT = r"C:/Users/rkdgi/AppData/Local/Temp/sample_render.html"

with open(PATH, "rb") as f:
    data = f.read()

frag = render_hwp_to_html(data, "hwp")

# 표/문단 개수
n_table = frag.count("<table ")
n_p = frag.count("<p>")
n_fallback = frag.count("table fallback")

# 브라우저에서 바로 열 수 있게 최소 wrapper
full = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<style>table{margin:12px 0;font-size:13px}td{padding:4px 8px}p{margin:4px 0}</style>"
    "</head><body>" + frag + "</body></html>"
)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(full)

print(f"saved: {OUT}")
print(f"<table> count: {n_table}")
print(f"<p> count: {n_p}")
print(f"fallback tables: {n_fallback}")

# 184,636 표 구조 확인
idx = frag.find("184,636")
if idx != -1:
    snippet = frag[max(0, idx - 400):idx + 200]
    # 셀 구조 확인용으로 안전 출력 (콘솔 인코딩 회피: 유니코드 escape)
    print("\n--- 184,636 주변 HTML (td 구조 확인) ---")
    print(snippet.encode("ascii", "backslashreplace").decode("ascii"))
else:
    print("184,636 not found")
