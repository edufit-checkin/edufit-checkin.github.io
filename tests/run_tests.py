"""에듀핏 체크인 자동 테스트 (실제 Firebase 없이 가짜 서버로 실행)

실행:  python tests/run_tests.py
준비:  pip install playwright openpyxl  →  python -m playwright install chromium

검사 항목
  1. 휴대폰 폭(iPhone SE·13)에서 현황 표가 가로로 넘치지 않는지
  2. 담당자 2대 실시간 연결: 한쪽 출석이 다른 쪽에 반영되는지
  3. QR 셀프 체크인: 접수 닫힘/출석/중복/명단 없음/동명이인/종료/출석 없이 종료/서버 기록 삭제
  4. 서버에 이름·전화번호가 저장되지 않는지
  5. 100명 명단 준비 시간
"""
import json, os, sys, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
FAKE = os.path.join(TESTS, "fake")
DEMO = os.path.join(TESTS, "demo")
PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"

# ---------------- 가짜 Firestore 서버 ----------------
DB = {}
PAGES = {}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _h(self, code=200, ct="application/json"):
        self.send_response(code); self.send_header("Content-Type", ct)
        self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
    def do_OPTIONS(self): self._h()
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path == "/list":
            pre = q["prefix"][0]
            out = [{"id": k[len(pre):], "data": v} for k, v in DB.items() if k.startswith(pre) and "/" not in k[len(pre):]]
            self._h(); self.wfile.write(json.dumps(out).encode())
        elif u.path == "/get":
            self._h(); self.wfile.write(json.dumps(DB.get(q["path"][0])).encode())
        elif u.path == "/dump":
            self._h(); self.wfile.write(json.dumps(DB).encode())
        elif u.path.lstrip("/") in PAGES:
            self._h(ct="text/html; charset=utf-8"); self.wfile.write(PAGES[u.path.lstrip("/")])
        else:
            self._h(404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); b = json.loads(self.rfile.read(n))
        if self.path == "/del":
            DB.pop(b["path"], None)
        else:
            d = DB.setdefault(b["path"], {})
            for k, v in b["data"].items():
                if isinstance(v, dict) and "__au" in v:
                    arr = d.setdefault(k, [])
                    for x in v["__au"]:
                        if x not in arr: arr.append(x)
                else:
                    d[k] = v
        self._h(); self.wfile.write(b"{}")

def load_pages():
    app = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    # 테스트에서는 http로 열기 때문에 QR 만들기의 https 검사를 끈다
    app = app.replace('if (location.protocol !== "https:"){', 'if (false){')
    PAGES["app.html"] = app.encode("utf-8")
    PAGES["self.html"] = open(os.path.join(ROOT, "self.html"), "rb").read()

def route(r):
    name = r.request.url.rsplit("/", 1)[1]
    r.fulfill(status=200, body=open(os.path.join(FAKE, name), encoding="utf-8").read(),
              headers={"Content-Type": "application/javascript", "Access-Control-Allow-Origin": "*"})

# ---------------- 도우미 ----------------
FAILS = []
def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond: FAILS.append(name)

def page(b, p, dev, url):
    c = b.new_context(**p.devices[dev]); pg = c.new_page()
    pg.route("https://www.gstatic.com/firebasejs/**", route)
    pg.on("pageerror", lambda e: FAILS.append(f"페이지 오류: {e}"))
    pg.on("dialog", lambda d: d.accept())
    pg.goto(url); return pg

def keypad(pg, digits):
    pg.click("[data-view=view-checkin]")
    for d in digits: pg.click(f"#searchKeypad button:text-is('{d}')")

def status_rows(pg):
    pg.click("[data-view=view-status]"); pg.wait_for_timeout(150)
    return [r.inner_text().replace("\t", " | ") for r in pg.query_selector_all("#statusBody tr")]

def connect_new(pg):
    pg.click("[data-view=view-list]"); pg.click("#btnSyncNew")
    t = time.time()
    while pg.inner_text("#syncBadge") != "연결됨" and time.time() - t < 30: pg.wait_for_timeout(100)
    return pg.inner_text("#syncCodeShow")

def attend(S, name, l4):
    if S.is_visible("#back"): S.click("#back")
    S.fill("#name", name); S.fill("#last4", l4); S.click("#submit")
    S.wait_for_selector("#resultCard:not(.hidden)")
    return S.inner_text("#rTitle")

def dump(): return json.loads(urllib.request.urlopen(BASE + "/dump").read())

# ---------------- 테스트 ----------------
def main():
    try: sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔 한글 출력
    except Exception: pass
    load_pages()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    roster5 = os.path.join(DEMO, "test_5명_동명이인포함.xlsx")
    roster100 = os.path.join(DEMO, "test_100명.xlsx")

    with sync_playwright() as p:
        b = p.chromium.launch()

        print("[1] 휴대폰 폭 현황 표")
        for dev in ["iPhone SE", "iPhone 13"]:
            pg = page(b, p, dev, BASE + "/app.html")
            pg.set_input_files("#excelInput", roster5); pg.wait_for_timeout(300)
            status_rows(pg)
            sw, cw = pg.evaluate("[document.querySelector('.status-table').scrollWidth, document.querySelector('.status-table').parentElement.clientWidth]")
            check(f"{dev} 표 가로 넘침 없음", sw <= cw, f"{sw}>{cw}")
            pg.context.close()

        print("[2] 담당자 2대 실시간 연결")
        DB.clear()
        A = page(b, p, "iPhone 13", BASE + "/app.html"); A.set_input_files("#excelInput", roster5); A.wait_for_timeout(300)
        B = page(b, p, "iPhone SE", BASE + "/app.html"); B.set_input_files("#excelInput", roster5); B.wait_for_timeout(300)
        code = connect_new(A)
        B.click("[data-view=view-list]"); B.fill("#syncCodeInput", code); B.click("#btnSyncJoin")
        t = time.time()
        while B.inner_text("#syncBadge") != "연결됨" and time.time() - t < 30: B.wait_for_timeout(100)
        check("B 같은 코드로 연결", B.inner_text("#syncBadge") == "연결됨")
        keypad(A, "5678"); A.click("#btnConfirmCheckin"); A.wait_for_timeout(1000)
        check("A 출석이 B에 반영", "출석" in status_rows(B)[0])
        keypad(B, "5678"); B.click("#btnConfirmCheckin"); A.wait_for_timeout(1000)
        check("B 종료가 A에 반영", "완료" in status_rows(A)[0])
        A.context.close(); B.context.close()

        print("[3] QR 셀프 체크인")
        DB.clear()
        A = page(b, p, "iPhone 13", BASE + "/app.html"); A.set_input_files("#excelInput", roster5); A.wait_for_timeout(300)
        connect_new(A)
        check("동명이인 안내 표시", A.is_visible("#selfDupNote"))
        A.click("#btnSelfQR"); A.wait_for_timeout(300)
        pub = A.inner_text("#selfQRUrl").split("e=")[1].strip(); A.click("#btnSelfQRClose")
        S = page(b, p, "iPhone SE", BASE + "/self.html?e=" + pub); S.wait_for_timeout(800)
        check("접수 닫힘이면 버튼 잠김", S.is_disabled("#submit"))
        A.click("#selfMode button[data-mode=in]"); S.wait_for_timeout(800)
        check("출석 접수 표시", "출석 접수" in S.inner_text("#chip"))
        check("정상 출석", attend(S, "홍길동", "5678") == "출석 확인되었습니다")
        check("중복 출석 안내", attend(S, "홍 길동", "5678") == "이미 출석 확인되었어요")
        check("명단 없음 안내", attend(S, "홍길순", "5678") == "명단에서 찾지 못했어요")
        check("동명이인 안내", attend(S, "김영희", "5432") == "담당자 확인이 필요해요")
        A.wait_for_timeout(800)
        check("셀프 출석이 담당자 현황에 반영", "출석" in status_rows(A)[0])
        keypad(A, "3333"); A.click("#btnConfirmCheckin"); A.click("#btnResultRetry"); A.wait_for_timeout(500)
        A.click("[data-view=view-list]"); A.click("#selfMode button[data-mode=out]"); S.wait_for_timeout(800)
        check("키패드 출석자의 QR 종료", attend(S, "남궁민수", "3333") == "종료 확인되었습니다")
        check("출석 없이 종료 시도", attend(S, "이수진", "1212") == "출석 기록이 없어요")
        A.wait_for_timeout(800)
        rows = status_rows(A)
        check("담당자 현황 완료 반영", "완료" in rows[1], rows[1])
        txt = json.dumps(dump(), ensure_ascii=False)
        check("서버에 이름·전화번호 없음", not any(x in txt for x in ["홍길동", "김영희", "5678", "010"]))
        A.click("[data-view=view-list]"); A.click("#btnSelfWipe"); A.wait_for_timeout(1000)
        check("서버 기록 삭제 후 비어 있음", len(dump()) == 0, f"{len(dump())}건 남음")
        S.wait_for_timeout(800)
        check("삭제 후 QR은 없는 행사", "없는 행사" in S.inner_text("#chip"))
        A.context.close(); S.context.close()

        print("[4] 100명 명단 준비 시간")
        DB.clear()
        A = page(b, p, "iPhone 13", BASE + "/app.html"); A.set_input_files("#excelInput", roster100); A.wait_for_timeout(300)
        t = time.time(); connect_new(A); sec = time.time() - t
        print(f"  참고  100명 연결까지 {sec:.1f}초 (이 컴퓨터 기준)")
        check("100명 30초 이내 연결", sec < 30)
        b.close()

    srv.shutdown()
    print()
    if FAILS:
        print(f"실패 {len(FAILS)}건:"); [print("  -", f) for f in FAILS]; sys.exit(1)
    print("모든 테스트 통과")

if __name__ == "__main__":
    main()
