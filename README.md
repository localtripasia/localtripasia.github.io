# Local Trip — 한국·일본 여행 트렌드 자동 게시 봇

매일 한 번 **영어 카드뉴스**를 만들어 **인스타그램**(캐러셀)과 **핀터레스트**(핀)에 자동으로 올리고,
링크 페이지에 아고다·트립닷컴·클룩 제휴 링크를 추가하는 봇이에요. K뷰티 봇(@seoul.skin.picks)과
같은 구조를 재활용했어요. 자세한 기획 배경은 "한일 여행 트렌드 계정 기획서" 문서를 참고하세요.

> ⚠️ **지금 이 저장소는 1차 스캐폴딩이에요.** 코드는 돌아가고 테스트도 통과하지만(`python -m bot demo`),
> 카드 디자인은 임시 템플릿이고, 아고다·트립닷컴·클룩·e-Stat 연동은 실제 API 호출 코드가 TODO로
> 남아 있어요(제휴 승인 전이라 테스트할 수 없어서예요). 도시 20곳 중 서울·도쿄 2곳만 실제 자료가
> 있어요. 다음 단계(자료 만들기 → 카드 디자인 → Secret 넣기)에서 채워요.

---

## 자동으로 일어나는 일

**매일 밤 10시 7분 (한국 시간) — 게시 (`daily-post.yml`)**
1. `config.toml [series]`에서 이번 달 목표 대비 가장 뒤처진 시리즈를 골라요.
2. `content/*.toml`의 자료로 카드뉴스(표지 + 내용 슬라이드)와 캡션을 만들어요. 아고다·트립닷컴·
   클룩 버튼이 있는 게시물은 캡션에 `#ad`가 자동으로 들어가요.
3. 링크 페이지(`index.html`)를 업데이트해요. `No.12 → 예약 링크`가 추가돼요.
4. 인스타에 캐러셀로 게시해요. 화·목·토에는 같은 카드로 만든 릴스를 먼저 올려요.
5. 핀터레스트용 세로 이미지와 가이드 페이지(`/p/NNN.html`)를 만들어 피드(`feed.xml`)에 추가해요.
   핀터레스트가 24시간 안에 핀으로 올려요.

**매주 월요일 아침 9시 17분 — 트렌드 새로고침 (`weekly-trends.yml`)**
- 네이버 검색어 트렌드(한국 목적지)와 e-Stat 숙박통계(일본 도도부현)를 가져와 `data/trend_latest.json`에
  저장해요. 목요일 "이번 주 현지인이 가는 곳" 게시물이 이걸 읽어요.

## 시리즈 (`config.toml [series]`)

| 시리즈 | 월 횟수 | 내용 | 자료 |
|---|---|---|---|
| city101 | 6 | 왜 가야 하나·언제·가는 법·할 것 3가지·숙소 예산 3단계 | `content/cities.toml` |
| hood | 6 | 동네 한 곳 소개 (분위기·할 것·가는 법) | `content/hoods.toml` |
| area | 3 | 동네 비교 ("명동 vs 홍대 vs 성수") | `content/areas.toml` |
| hotel | 4 | 조건별 호텔 픽 (예산 3단계) | `content/cities.toml`의 `example_hotels` + 아고다 API |
| transport | 3 | JR패스·코레일패스·티머니·eSIM | `content/passes.toml` |
| route | 2 | 3일·5일 코스, 한일 연결 코스 | `content/routes.toml` |
| season | 2 | 벚꽃·단풍·눈 시기, 축제 | `content/seasons.toml` |
| words | 1 | 식당·온천·지하철에서 쓰는 말 | `content/words.toml` |
| weekly | 매주 목 | 네이버 검색 TOP + 일본 숙박통계 | `data/trend_latest.json` |
| recap | 1 | 지난달 결산 | (추후 구현) |

숫자·간격은 `config.toml`에서 바로 바꿀 수 있어요. `python -m bot check`으로 이번 달 진행 상황을 볼 수 있어요.

## 데이터 출처 (전부 공식 API, robots.txt·약관 확인됨)

- **한국:** [네이버 API HUB](https://api.ncloud-docs.com/docs/naver-api-hub-overview) 검색어 트렌드,
  [한국관광공사 공공데이터](https://www.data.go.kr/data/15101753/openapi.do).
- **일본:** [e-Stat API](https://www.e-stat.go.jp/api/en/api-info/api-guide) 숙박여행통계(도도부현별 월간
  숙박자 수). **라쿠텐 트래블 랭킹 API는 쓰지 않아요** — [약관](https://webservice.rakuten.co.jp/guide/rule)상
  순위 화면에 타사(아고다 등) 링크를 걸 수 없고, 응답 데이터를 공개 저장소에 저장할 수 없고,
  지역별이 아니라 전국 TOP 10만 제공돼요. 이 세 가지가 기획과 맞지 않아서 대체했어요.
- **호텔:** [아고다 제휴 Long Tail Search API](https://partners.agoda.com/Content/Documents/AffiliateLiteApi/Affiliate_Lite_API_V2.0.pdf)
  (승인 전에는 `content/cities.toml`의 `example_hotels`를 링크 없이 보여줘요).

## 제휴 3곳

호텔은 아고다·트립닷컴 두 버튼을 나란히 두고, 투어·패스·eSIM은 클룩(Involve Asia 경유)이 맡아요.
제휴 링크 모양은 `config.toml`의 `[agoda]`/`[tripcom]`/`[klook]`에 템플릿으로 넣어두고, 승인 전에는
각 서비스 홈페이지로 연결되는 일반 링크로 게시돼요 (승인 후 `bot/sources/agoda.py`의 TODO를 실제
API 호출로 바꿔요).

## Secret 한눈에 보기

| 이름 | 필수 | 용도 |
|---|---|---|
| `IG_ACCESS_TOKEN` | 게시하려면 필수 | 인스타 게시 |
| `KTO_API_KEY` | 권장 | 한국 동네·도시 카드 표지 사진 (한국관광공사 관광사진 API, 공공누리 1유형) |
| `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` | 권장 | 목요일 게시물의 한국 검색 트렌드 |
| `ESTAT_APP_ID` | 권장 | 목요일 게시물의 일본 숙박통계 |
| `AGODA_SITE_ID` / `AGODA_API_KEY` | 승인 후 | 호텔 실제 목록·제휴 링크 |
| `TRIPCOM_AFFILIATE_KEY` | 승인 후 | 트립닷컴 딥링크 |
| `INVOLVE_ASIA_KEY` | 승인 후 | 클룩 딥링크 |
| `GH_PAT` | 선택 | 인스타 토큰 자동 연장 저장 |
| `IG_USER_ID` | 거의 불필요 | 페이스북 로그인 방식 API를 쓸 때만 |

**API 키·토큰 값은 Claude가 보거나 입력하지 않아요.** Secret 이름만 미리 채워두고, 값은 직접 붙여넣어요.

## 폴더 구조

```
config.toml                    ← 계정·게시 설정
content/cities.toml             ← 도시 101 자료 + 호텔 예시 (지금 서울·도쿄만)
content/areas.toml               ← 동네 비교 자료
content/passes.toml               ← 교통·준비물 자료
content/routes.toml                ← 코스 자료
content/seasons.toml                ← 계절·축제 자료
content/words.toml                   ← 현지 말·에티켓
content/keywords.toml                 ← 네이버에서 볼 목적지 검색어
content/hoods.toml                     ← 동네 한 곳씩 소개 (서울 8곳)
content/photos.toml                     ← 손으로 고른 표지 사진 목록 (자동 사진보다 우선)
photos/                                  ← 사진 파일 (자동으로 받은 것 + 직접 넣은 것)
data/state.json                        ← 게시 기록 (봇이 자동 관리)
data/trend_latest.json                  ← 이번 주 트렌드 (매주 월요일 자동)
data/agoda_catalog.json                  ← 도시별 아고다 호텔 목록 (제휴 승인 후 자동)
assets/music/                             ← 릴스 배경음악 (직접 합성한 오리지널 곡)
bot/                                       ← 봇 코드
  editorial.py                              ← content/*.toml 로더 + 오늘의 주제 고르기
  series.py                                  ← 월 횟수 스케줄러
  copy.py                                     ← 캡션·버튼·기사 본문 조립 (AI 없음)
  render.py                                    ← 카드 이미지 렌더러 (1차 템플릿)
  sources/agoda.py, sources/estat.py           ← 제휴/통계 API 클라이언트 (TODO 있음)
.github/workflows/                            ← 매일 게시 + 주간 트렌드 + 토큰 연장
tests/                                         ← 자료 검증(출처 2개 이상 등) + 스모크 테스트
```

**내 컴퓨터에서 미리보기** (파이썬 3.11+가 있을 때)
```
pip install -r requirements.txt
python -m bot demo          # demo_output/ 폴더에 샘플 카드와 링크 페이지 생성
python -m unittest discover tests
```
