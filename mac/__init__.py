"""
macOS 메뉴 막대 판 — rumps(PyObjC) 로 상태 항목 하나를 띄우고, 제목(글자)에 5h/7d 사용률을 쓴다.

Windows 판(ai_status_bar.py)과 나누어 쓰는 것: providers/ (자격증명·조회·파싱), polling.py (하한·디바운스·백오프),
i18n.py, applog.py, version.py. 이 패키지는 macOS 에서만 import 된다 — Windows 파일은 건드리지 않는다.

  paths.py        설정·로그·LaunchAgent 경로
  settings.py     settings.json (Windows 와 같은 스키마·화이트리스트)
  title.py        메뉴 막대 제목 문자열 조립 — 순수 함수 (tests/test_mac_title.py)
  launchagent.py  로그인 시 자동 시작 (~/Library/LaunchAgents/com.yeojeonghun.ai-status-bar.plist)
  app.py          rumps 앱 — 메뉴·폴링·알림
"""
