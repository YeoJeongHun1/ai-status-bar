# AI Status Bar

> **Anthropic · OpenAI · GitHub 등 어느 회사와도 무관한 개인 오픈소스입니다.** 각 서비스의 이름은 그 회사의 상표입니다.

Windows 작업 표시줄의 빈 공간에 **AI 구독의 사용량(5시간 / 주간 한도)** 을 상시 표시하는 작은 도구입니다.
설정 페이지를 열지 않아도 지금 얼마나 썼는지, 언제 리셋되는지 한눈에 보입니다.

![screenshot](docs/screenshot.png)

```
Claude work   5h ▬▬▬░░░░░ 23% ↺12:09   │   Codex work   5h ▬░░░░░░░  4% ↺17:10
              7d ▬▬▬▬▬░░░ 66% ↺09/01   │                7d ▬▬░░░░░░ 12% ↺09/03
```

*(English below)*

## 지원 서비스

| 서비스 | 계정 = 이 파일이 있는 폴더 | 창 | 데이터 원본 |
|---|---|---|---|
| **Claude Code** (Claude Pro/Max) | `%USERPROFILE%\.claude\.credentials.json` (또는 `CLAUDE_CONFIG_DIR`) | 5시간 · 7일 · 모델별(Fable 등) | 비공식 API **또는** 공식 모드(상태줄 데이터, 네트워크 0) |
| **Codex** (ChatGPT Plus/Pro/Team) | `%USERPROFILE%\.codex\auth.json` (또는 `CODEX_HOME`) | 5시간 · 주간 | 비공식 API |

계정을 여러 개(예: 회사·개인) 두면 항목이 여러 개가 됩니다. 항목 = 서비스 × 계정.

## 특징

- **2줄 표시, 필요한 정보만** — 위 5시간, 아래 주간. 리셋 시각은 「몇 분 후」가 아니라 이 PC 현지 시각(`↺12:10`, 오늘이 아니면 `↺09/01 13:00`).
  서비스·계정·폴더·플랜·마지막 조회는 바에 **마우스를 올리면 카드 툴팁**(서비스 칩 · 창별 미니 막대 · 플랜 칩)으로 보이고, 올린 항목은 둥글게 강조됩니다 — 바 자체에는 글자를 더 얹지 않습니다.
- **색** — 초록(<50%) · 노랑(50~79%) · 빨강(80%+). 80% / 95% 를 넘는 순간 알림 1회.
- **표시 방식 커스텀** — 모든 항목 동시에 / 클릭으로 전환 / 자동 슬라이드(주기 설정) / 하나 고정. 항목 순서·라벨·창(5h/7d) 선택.
- **스타일** — 계정 라벨 on/off(기본 off), 막대 «자동 / 막대+숫자 / 숫자만», 라벨 색.
- **설정 창 = 라이브 미리보기 + 프리셋** — 어떤 값을 바꿔도 위쪽 미리보기가 즉시 다시 그려지고, «기본 / 미니멀 / 라벨 포함 / 풀 정보 / 슬라이드 / 고정» 카드를 누르면 한 번에 적용됩니다. «저장» 은 적용만 하고 창은 남습니다(닫기는 따로).
- **배경 투명** — 글자·막대만 그려지고, 나머지 영역은 클릭이 작업 표시줄로 통과합니다.
- **빈 공간 자동 배치** — 작업 표시줄을 캡처해 실제로 비어 있는 열을 찾고, 그중 가장 왼쪽에 놓습니다. 해상도·DPI·정렬·위젯·앱 수가 달라도 같은 코드가 돕니다.
  왼쪽 날씨 위젯의 경계는 UI Automation 으로 정확히 읽고(외부 프로세스 없이 COM 직접 호출), 위젯 바로 뒤에는 28px 여백을 둡니다. 20초마다 다시 재고, 2초마다 우리 자리 양끝 밑에 뭔가 들어왔는지 확인해 즉시 옮깁니다 — 날씨 문구가 길어져도 겹치지 않습니다.
- **폭에 따라 3단계** — 막대+숫자 → 숫자만 → `›` 버튼(누르면 위로 상세 팝업).
- **깜빡이지 않음** — 창을 화면 캡처에서 제외(`WDA_EXCLUDEFROMCAPTURE`)해 두고 재므로, 앱을 바꿔도 바가 숨었다 나타나지 않습니다. 전체화면 앱이 앞에 오면 숨깁니다.
- **작업 표시줄 버튼을 차지하지 않음** — 오른쪽 `^` 트레이 안의 아이콘으로만 존재합니다.
- **파이썬 불필요** — zip 을 풀어 실행하면 끝. 설치 프로그램·레지스트리·자기 복사 없음.
- **지원 언어** — 한국어 · English · 日本語 · Português (Brasil) · Español. Windows 표시 언어를 따르며 설정에서 바꿀 수 있습니다.

## 설치

1. 이 PC 에서 [Claude Code](https://code.claude.com) 나 [Codex CLI](https://developers.openai.com/codex) 로 **한 번 로그인**돼 있어야 합니다 (위 표의 파일이 그때 생깁니다).
2. [Releases](https://github.com/YeoJeongHun1/ai-status-bar/releases) 에서 `AIStatusBar-<버전>-win64.zip` 을 받아 **원하는 폴더에 풉니다** (예: `%LOCALAPPDATA%\Programs\AIStatusBar`).
3. 푼 폴더의 `AIStatusBar.exe` 를 실행 → 시작 설정 창에서 계정이 잡혔는지 확인하고 「로그인할 때 자동 시작」을 고른 뒤 **시작**.

![settings](docs/settings.png)

- 프로그램은 **풀어 둔 자리에서 그대로** 돕니다. 자동 시작은 시작프로그램 폴더의 바로가기 하나뿐입니다.
- **제거**: 자동 시작을 끄고(설정 창 또는 `AIStatusBar.exe --no-autostart`) 폴더를 지우면 끝. 설정 파일은 `%LOCALAPPDATA%\AIStatusBar\settings.json` 하나입니다.

### 백신·SmartScreen 이 막을 때

코드 서명이 없는 개인 오픈소스라 **처음 보는 exe** 취급을 받습니다.

- **Windows SmartScreen** 「확인되지 않은 앱」 → 「추가 정보 → 실행」.
- **Microsoft Defender** 가 `Trojan:Win32/Sabsik.*!ml` · `Wacatac.*!ml` 처럼 끝에 `!ml` 이 붙은 이름으로 잡는다면 머신러닝 휴리스틱의 **오탐**입니다.
  이 판단을 유발하는 요소는 처음부터 뺐습니다 — 단일 exe(임시 폴더에 풀어 실행) 대신 **폴더 배포**, 자기 복사·PowerShell 호출·자기 삭제 코드 없음, 버전 정보 리소스 포함. 같은 Defender 엔진의 로컬 스캔에서 폴더·zip 모두 위협 0 입니다.
- 그래도 잡히면: ① Defender 「보호 기록」에서 «허용» ② [Microsoft 에 오탐 신고](https://www.microsoft.com/wdsi/filesubmission) ③ 못 믿겠으면 「소스로 실행」 — 코드 전부가 이 저장소에 있습니다.
- 근본 해결은 코드 서명 인증서(연 수십만 원)뿐이라, 사용자가 늘면 [GitHub Sponsors](https://github.com/sponsors/YeoJeongHun1) 로 마련할 계획입니다.

### 사용

| 동작 | 결과 |
|---|---|
| 왼쪽 클릭 | 「클릭으로 전환·자동 슬라이드」 모드면 다음 항목. 그 외엔 새로고침(막대 모드) / 상세 팝업(`›` 모드) |
| 오른쪽 클릭 | 메뉴 — 설정 · 다음 항목 · 새로고침 · 빈 공간 다시 재기 · 각 서비스 사용량 페이지 · 사용 방법 · 종료 |
| 트레이 `^` 안 아이콘 | 우클릭(또는 더블클릭) — 설정 · 다음 항목 · 새로고침 · 사용 방법 · 종료 |

### 설정 창

트레이 아이콘 또는 바 우클릭 → **설정…** (`AIStatusBar.exe --setup` 으로도 열림)

- **항목 (서비스 × 계정 폴더)** — 표시 on/off · 라벨(기본값: 로그인 이메일의 `@` 앞부분) · 창(5h/7d) · 순서 ▲▼ · 삭제.
  «다시 탐색» 은 모든 서비스의 기본 폴더와 환경변수(`CLAUDE_CONFIG_DIR`, `CODEX_HOME`)를 자동으로 찾고, «폴더 추가…» 로 서비스를 고른 뒤 아무 폴더나 직접 지정할 수 있습니다.
  «계정이 안 보여요?» 가 서비스별로 안 뜨는 이유를 설명합니다.
- **데이터 원본** — 비공식 API(5분마다) 또는 공식 모드(아래 절). 공식 모드에서 공식 데이터가 없는 항목(Codex)은 숨길 수 있습니다.
- **표시 방식** — 모든 항목 동시에 / 클릭으로 전환 / 자동 슬라이드(5~3600초) / 하나 고정(항목 선택). 자동 슬라이드는 **마우스가 바 위에 있는 동안 멈추고**, 벗어나면 주기를 처음부터 다시 셉니다.
- **표시 · 스타일 탭** — 프리셋 카드(미리보기 그림 포함) · 표시 방식 · 라벨 표시 · 막대 «자동/막대+숫자/숫자만» · 라벨 색 · 모델별 한도 표시. 맨 위 미리보기는 현재 폼 값을 그대로 그립니다(값이 없으면 예시값).
- **저장** — 적용하고 창은 그대로(«저장됨 ✓»). 저장하지 않고 닫으면 저장/버리기/취소를 묻습니다.
- **시작** — Windows 로그인 시 자동 시작 (시작프로그램 폴더 바로가기, 관리자 권한 불필요).
- **언어** — 시스템 기본 / 5개 언어.

- 명령줄: `--setup` 설정 창 열기 · `--autostart` / `--no-autostart` 자동 시작 켜기/끄기 (조용히)
- 갱신 주기 5분 (환경변수 `AI_STATUS_BAR_POLL_SEC`, 초)

### 소스로 실행

```bat
pip install pillow pystray pywin32
pythonw ai_status_bar.py
```

exe 다시 만들기: `build.cmd` (PyInstaller, 폴더 빌드 + zip).

## 어떻게 동작하나 — 투명하게

이 프로그램이 디스크에서 읽는 것, 네트워크로 보내는 것, 받는 것을 전부 적습니다. 네트워크 코드는 `providers/` 의 서비스별 파일에 **한 요청씩**만 있습니다.

### Claude Code (`providers/claude_code.py`)

**디스크에서 읽는 것** (읽기만)

| 파일 | 읽는 항목 | 용도 |
|---|---|---|
| `<설정 폴더>\.credentials.json` | `claudeAiOauth.accessToken`, `expiresAt`, `subscriptionType`, `rateLimitTier` | 토큰은 요청 헤더에만. 나머지는 설정 창 «연결 상태» |
| `<설정 폴더>\.claude.json` (기본 폴더는 `%USERPROFILE%\.claude.json`) | `oauthAccount.emailAddress` | 라벨(`@` 앞부분)만 |

**보내는 것** (비공식 API 모드, 계정마다 5분에 한 번 + «새로고침» 때)

```http
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <accessToken>
anthropic-beta: oauth-2025-04-20
User-Agent: ai-status-bar/1.0
```

**받아서 쓰는 것** — `five_hour.utilization/resets_at`, `seven_day.utilization/resets_at`, `limits[kind=weekly_scoped].percent/scope.model.display_name`. 나머지는 버립니다.

이 엔드포인트는 Anthropic 이 **문서화하지 않은 비공식** 경로입니다(개인 구독자용 공식 사용량 API 는 없습니다). 공식 데이터만 쓰려면 아래 «공식 모드».

### Codex (`providers/codex.py`)

**디스크에서 읽는 것** (읽기만)

| 파일 | 읽는 항목 | 용도 |
|---|---|---|
| `<설정 폴더>\auth.json` | `tokens.access_token`, `tokens.account_id`, `tokens.id_token`, `auth_mode` | 토큰·계정 ID 는 요청 헤더에만. `id_token`/`access_token` 의 JWT claim(`email`, `chatgpt_plan_type`, `exp`)을 **로컬에서 디코드**해 라벨·플랜·만료 표시(서명 검증 없음, 표시용) |

**보내는 것** (계정마다 5분에 한 번 + «새로고침» 때)

```http
GET https://chatgpt.com/backend-api/wham/usage
Authorization: Bearer <access_token>
ChatGPT-Account-Id: <account_id>
User-Agent: ai-status-bar/1.0
```

**받아서 쓰는 것** — `rate_limit.primary_window.{used_percent, reset_at, limit_window_seconds}` → 5h, `rate_limit.secondary_window.{…}` → 주간. 응답의 `email`·`user_id` 등 **나머지는 읽지 않습니다**.

이 엔드포인트도 OpenAI 가 **문서화하지 않은 비공식** 경로입니다(Codex CLI 의 `/status` 가 쓰는 것과 같은 계열). API 키 방식(`auth_mode: apikey`)은 사용량 창이 없어 지원하지 않습니다.

### 공통

- 목적지는 위 두 호스트뿐입니다. 통계·오류 보고·업데이트 확인 등 **다른 요청은 없습니다.** 본문(body)도 없습니다.
- 토큰을 **갱신하지 않고, 어디에도 저장하지 않습니다.** 만료되면 «⚠» 를 표시하고, 해당 CLI 를 한 번 실행하면 CLI 가 갱신한 파일을 다음 폴링에 다시 읽습니다.
- 저장하는 것: `%LOCALAPPDATA%\AIStatusBar\settings.json`(표시 설정·계정 폴더 목록·라벨), 자동 시작 바로가기 `AI Status Bar.lnk`, 공식 모드 파일(아래). **토큰이나 사용량 값은 저장하지 않습니다.** 로그·캐시·레지스트리 값을 만들지 않습니다.
- 방화벽·프록시 로그에서 `api.anthropic.com`·`chatgpt.com` 외 목적지가 보이면 버그이니 이슈로 알려 주세요.
- 비공식 경로라 각 회사가 바꾸면 «⚠ HTTP 4xx» 를 표시하고 멈춥니다 — 다른 우회를 시도하지 않습니다. **무보증 · 자기 책임으로 사용하세요.**

## 공식 모드 — 비공식 API 를 쓰지 않는 선택지 (Claude Code)

설정 창 «데이터 원본» 에서 고릅니다.

| | 비공식 API (기본) | 공식 모드 |
|---|---|---|
| 데이터 | `api.anthropic.com/api/oauth/usage` | Claude Code 상태줄이 **공식으로** 넘겨주는 `rate_limits` — [문서](https://code.claude.com/docs/en/statusline) |
| 네트워크 | 5분마다 요청 1회 | **없음** (로컬 파일만 읽음) |
| 갱신 | 항상 | **Claude Code 세션이 떠 있는 동안만** (세션이 없으면 마지막 값 + «N분 전») |
| 모델별 한도(Fable 등) | 있음 | 없음 |
| Codex | 표시 | 공식 데이터가 없어 숨김(설정으로 «공식 데이터 없음» 표시 가능) |

**설치가 무엇을 바꾸나** — 항목 행의 «상태줄 연결 설치» 를 누르면(확인 대화상자 뒤에):
1. 그 계정 폴더의 `settings.json` 을 `settings.json.bak-aistatusbar` 로 **백업**합니다.
2. `statusLine` 을 이 앱의 `statusline_export.ps1` 로 바꿉니다:
   `"statusLine": {"type": "command", "command": "powershell -NoProfile -ExecutionPolicy Bypass -File \"<앱 폴더>\\_internal\\statusline_export.ps1\""}`
3. 원래 `statusLine` 은 `%LOCALAPPDATA%\AIStatusBar\official\<key>.original.json` 에 보관합니다 (Claude Code 의 `settings.json` 에 낯선 키를 넣지 않기 위해 앱 폴더에 둡니다).

이후 Claude Code 가 상태줄을 그릴 때마다 스크립트가 받은 JSON 을 `%LOCALAPPDATA%\AIStatusBar\official\<key>.json` 에 저장하고, **원래 쓰던 상태줄 명령이 있으면 그 JSON 을 그대로 넘겨 출력을 인쇄**합니다(기존 상태줄은 그대로 보입니다). 없었다면 `모델 | 5h xx% | 7d xx%` 한 줄을 인쇄합니다. `<key>` 는 설정 폴더 경로의 SHA-1 앞 12자입니다. 새 Claude Code 세션부터 적용됩니다.

**해제 · 수동 복구** — «상태줄 연결 해제» 가 원래 `statusLine` 을 복원하고(없었다면 키 제거) 보관본을 지웁니다. 앱 없이 되돌리려면 `settings.json.bak-aistatusbar` 를 `settings.json` 으로 되돌리거나 `statusLine` 키를 지우면 됩니다.

**알아둘 점** — `rate_limits` 는 구독 계정 + 세션 첫 응답 이후에만 들어옵니다. 상태줄 명령마다 PowerShell 기동 비용(수백 ms)이 더해집니다. 공식 모드에서는 이 앱이 **네트워크 호출 코드를 아예 타지 않습니다.**

## 내 계정이 목록에 안 떠요

이 앱이 «계정»으로 보는 것은 각 CLI 가 로그인 정보를 저장하는 **파일**입니다 — CLI(터미널 앱)로 로그인해야 생기고, 웹·데스크톱 앱만 쓰면 생기지 않습니다.

**Claude Code** (`<설정 폴더>\.credentials.json`)
1. 이 PC 에서 Claude Code 로 로그인한 적이 없다 → 터미널에서 `claude` 실행해 로그인.
2. 같은 폴더에서 `/login` 으로 계정을 바꿔 가며 쓴다 → 파일에는 **마지막 계정 하나만** 남습니다.
3. `claude setup-token` + `CLAUDE_CODE_OAUTH_TOKEN` 환경변수 방식 → 토큰이 파일로 저장되지 않아 **볼 수 없습니다** (지원하지 않음).
4. 설정 폴더가 기본 위치 밖(`CLAUDE_CONFIG_DIR`) → 설정 창 «폴더 추가…».

**Codex** (`<설정 폴더>\auth.json`)
1. `codex login` 을 한 적이 없다 → 터미널에서 `codex login` (ChatGPT 계정).
2. API 키 방식(`auth_mode: apikey`, `OPENAI_API_KEY`) → 5시간/주간 창이 없어 표시할 것이 없습니다 (지원하지 않음).
3. 설정 폴더가 기본 위치 밖(`CODEX_HOME`) → «폴더 추가…».

**계정을 여러 개 동시에** 쓰려면 계정마다 폴더를 나누세요:
```powershell
$env:CLAUDE_CONFIG_DIR = "$HOME\.claude-b"; claude        # Claude Code 두 번째 계정
$env:CODEX_HOME = "$HOME\.codex-b"; codex login            # Codex 두 번째 계정
```
그다음 설정 창에서 «다시 탐색». macOS 는 Claude 토큰을 키체인에 저장해 파일이 없습니다 — 이 앱은 Windows 전용입니다.

## 알아둘 점

- Windows 11 의 작업 표시줄은 XAML 레이어가 전체를 덮고 있어 자식 창으로 붙이는 방식이 통하지 않습니다. 그래서 「항상 위」 창을 좌표만 맞춰 얹고 2초마다 다시 위로 올립니다. 작업 표시줄을 클릭하면 잠깐 가려졌다 돌아올 수 있습니다.
- 지원: Windows 10/11, 가로 작업 표시줄. 세로 도킹은 미지원. Windows 10 2004 이전에서는 캡처 제외 API 가 없어 재측정 때 0.1초 깜빡일 수 있습니다.
- 이전 이름(Claude Status Bar)의 설정(`%LOCALAPPDATA%\ClaudeStatusBar\settings.json`)과 자동 시작 바로가기는 첫 실행 때 자동으로 이전됩니다.

## 응원

쓸모 있었다면 ⭐ 하나, 또는 [GitHub Sponsors](https://github.com/sponsors/YeoJeongHun1) 로 커피 한 잔 부탁드립니다. 바 안에 광고는 넣지 않습니다.

## 상표 고지

Claude·Anthropic·OpenAI·ChatGPT·Codex 는 각 회사의 상표입니다. 이 앱은 서비스 식별 목적으로 **이름만** 표시하며 로고를 쓰지 않습니다. 두 회사와 무관한 개인 오픈소스입니다.

## 라이선스

MIT

---

# English

> **An independent open-source project, unaffiliated with Anthropic, OpenAI, GitHub or any other company.** Claude, Anthropic, OpenAI, ChatGPT and Codex are trademarks of their respective owners; names are shown only to identify the service, no logos are used.

A tiny Windows utility that shows your **AI subscription usage (5-hour / weekly limits)** in the empty area of the taskbar — always visible, no settings page to open.

| Service | Account = the folder containing | Windows | Data source |
|---|---|---|---|
| **Claude Code** (Claude Pro/Max) | `%USERPROFILE%\.claude\.credentials.json` (or `CLAUDE_CONFIG_DIR`) | 5-hour · 7-day · per-model | unofficial API **or** official mode (status-line data, zero network) |
| **Codex** (ChatGPT Plus/Pro/Team) | `%USERPROFILE%\.codex\auth.json` (or `CODEX_HOME`) | 5-hour · weekly | unofficial API |

- Two lines per entry (5h / weekly) with bars, percentages and the **local reset time**; entry = service × account, several accounts per service supported.
- **Display modes**: all entries at once / switch on click / auto slide (interval; pauses while the mouse is over the bar and restarts the full interval on leave) / pin one. Per-entry order, label, and which windows to show.
- **Only what matters on the bar**: service, account, folder, plan and last fetch appear in a **hover card** (service chip, mini bars per window, plan chip) with the hovered entry highlighted — not on the bar itself.
- **No overlap with the weather widget**: its exact edge is read via UI Automation (in-process COM, no external process) with a 28px gap; the bar re-measures every 20s and checks every 2s whether something slid under its edges, moving at once.
- **Style**: account label on/off (off by default), bars «auto / bars+numbers / numbers only», label color.
- **Settings = live preview + presets**: every change redraws the preview at the top instantly; preset cards (Default / Minimal / With labels / Full info / Slide / Pinned) apply a whole look at once. **Save** applies and keeps the window open; closing with unsaved changes asks.
- Transparent, click-through background; **auto-placement** by measuring the taskbar's empty columns; shrinks to numbers-only, then to a `›` button with a popup.
- No flicker (excluded from screen capture), hides during fullscreen apps, lives as a tray icon (no taskbar button).
- No Python required — unzip and run. No installer, no registry, no self-copy; "run at login" is one Startup-folder shortcut.
- **Languages**: 한국어 · English · 日本語 · Português (Brasil) · Español — follows your Windows display language.

**Install**: be logged in once with [Claude Code](https://code.claude.com) and/or [Codex CLI](https://developers.openai.com/codex) on this PC → download `AIStatusBar-<ver>-win64.zip` from Releases → unzip anywhere → run `AIStatusBar.exe` → tick "run at login" if you want → **Start**. To remove: turn off run-at-login and delete the folder.

**Antivirus**: unsigned personal open-source binary. SmartScreen: "More info → Run anyway". If Defender names it `...!ml` (Sabsik/Wacatac), that is an ML false positive on a Python executable; it ships as a plain folder (no one-file unpacker), with no self-copy/PowerShell/self-delete code and proper version info, which clears the local Defender scan. Allow it in Protection history, [report the false positive](https://www.microsoft.com/wdsi/filesubmission), or run from source (`pip install pillow pystray pywin32 && pythonw ai_status_bar.py`).

**How it works (full transparency)** — one request per account every 5 minutes, nothing else:
- Claude Code: `GET https://api.anthropic.com/api/oauth/usage` with `Authorization: Bearer <accessToken from .credentials.json>` and `anthropic-beta: oauth-2025-04-20`. Reads `five_hour.*`, `seven_day.*`, `limits[kind=weekly_scoped]`. From disk: `.credentials.json` (token, expiry, plan) and `.claude.json` (`oauthAccount.emailAddress`, label only).
- Codex: `GET https://chatgpt.com/backend-api/wham/usage` with `Authorization: Bearer <tokens.access_token from auth.json>` and `ChatGPT-Account-Id: <tokens.account_id>`. Reads `rate_limit.primary_window.*` (5h) and `rate_limit.secondary_window.*` (weekly) only. Label/plan/expiry come from decoding the local JWT claims (no signature check, display only). API-key mode has no usage windows and is not supported.
- Both endpoints are **unofficial** (undocumented by the vendors) and may break; the app then shows «⚠ HTTP 4xx» and does not try anything else. It talks to no other host, never refreshes or stores tokens, keeps no logs; settings live in `%LOCALAPPDATA%\AIStatusBar\settings.json`. No warranty.

**Official mode (Claude Code)**: instead of the unofficial API, use only the `rate_limits` that Claude Code's status line officially passes to its status-line command ([docs](https://code.claude.com/docs/en/statusline)). Zero network access; updates only while a Claude Code session is open; no per-model caps; Codex has no official data and is hidden. «Install status line link» on an entry backs up that folder's `settings.json` to `settings.json.bak-aistatusbar`, points `statusLine` at the bundled `statusline_export.ps1` (which saves the JSON to `%LOCALAPPDATA%\AIStatusBar\official\<key>.json` and then pipes it to your original status-line command, if any), and keeps the original `statusLine` in the app's folder. «Remove» restores it. Manual recovery: rename the `.bak-aistatusbar` file back, or delete the `statusLine` key.

**My account is not in the list**: an "account" is the login file the CLI writes — Claude Code: `.credentials.json` (missing if you never logged in on this PC, if you switch accounts with `/login` in one folder, if you use `claude setup-token` + `CLAUDE_CODE_OAUTH_TOKEN` — never written to a file, not supported — or if your folder is elsewhere via `CLAUDE_CONFIG_DIR`); Codex: `auth.json` (missing if you never ran `codex login`, if you use an API key — no usage windows, not supported — or if your folder is elsewhere via `CODEX_HOME`). Use «Add folder…» for custom folders. For several accounts at once give each its own folder: `$env:CLAUDE_CONFIG_DIR = "$HOME\.claude-b"; claude` / `$env:CODEX_HOME = "$HOME\.codex-b"; codex login`, then «Rescan». Windows-only (macOS keeps the Claude token in the Keychain).

MIT licensed. If it helps you, a ⭐ or a coffee via [GitHub Sponsors](https://github.com/sponsors/YeoJeongHun1) is appreciated.
