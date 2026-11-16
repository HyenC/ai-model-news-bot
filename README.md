# AI 생성 모델 소식 봇

이미지·영상·오디오 생성 모델의 새 소식을 1시간마다 확인해서, 한국어로 요약해 슬랙 채널로 보냅니다.
Claude Code 클라우드 예약 작업으로 돌아갑니다. 절차는 `bot/ROUTINE.md`, 판단 기준은 `bot/rules.md` 에 있습니다.

## 구조
- `bot/collect.py`: 소스를 확인해서 새 후보를 `out/candidates.json` 에 씀
- Claude: `bot/rules.md` 기준으로 판단·요약해서 `out/verdicts.json` 을 씀
- `bot/publish.py`: 형식 검사 후 슬랙 전송, `state/seen.json` 갱신

## 보는 곳 (`bot/sources.py`)
- fal.ai 모델 목록 (새 엔드포인트)
- Replicate 공식 모델 목록, Runware 모델 목록 (우리가 API를 가져오는 곳. 새로 등록되면 알림)
- Hugging Face (주요 기관의 신규 모델, 급상승 모델)
- 블로그 RSS: Google DeepMind, Google AI, OpenAI, ElevenLabs, Qwen, Hugging Face, Replicate, fal.ai
- 모델 회사 뉴스 페이지(새 글 링크 감시): Black Forest Labs, Runway, Luma AI, MiniMax, Meta AI, Recraft, Lightricks(LTX), Suno

## 동작
- 처음 보는 소스는 그 시점의 목록을 기준으로 저장만 하고 보내지 않습니다.
- 한 소스에서 새 항목이 80개를 넘으면 소스 쪽 변경으로 보고 보내지 않습니다(도배 방지).
- 알림마다 "등록 플랫폼"에 Replicate·Runware·fal.ai 등록 여부를 표시합니다. (주소는 실제 목록에 있는 것만 허용)
- 같은 모델은 출처가 여러 곳이어도 30일 안에 한 번만 보냅니다. 단, 그 뒤 우리 공급처(Replicate·Runware)에 새로 올라오면 `[후속]` 한 줄 알림을 보냅니다. (fal.ai·HF 등록은 다시 보내지 않음)
- 공식 경량화·고속 버전은 보내고, 다른 곳이 만든 경량화 버전은 보내지 않습니다.

## 주간 정리 (매주 월요일 09:00 KST)
- 데일리로 보낸 새 모델 소식을 `state/weekly/<주 시작 월요일>.json` 에 모아 둡니다(최근 8주). 제공 종료 공지는 넣지 않습니다.
- 별도 예약 실행이 `bot/WEEKLY.md` 절차로 지난주(월~일) 소식을 데일리 기록과 웹 검색으로 모아, 가장 중요한 새 모델 최대 5개와 기존 서빙 모델 업데이트·출시 예정 레이더를 Confluence 페이지로 씁니다(`bot/weekly_rules.md`).
- 슬랙(`WEEKLY_SLACK_WEBHOOK_URL`)에는 새 모델 제목과 한 줄 요약, Confluence 링크만 보냅니다.
- Confluence 위치는 공개 저장소에 두지 않고 예약 실행 요청 메시지에만 둡니다.
- 보낸 주는 `state/weekly_sent.json` 에 기록해 두 번 보내지 않습니다.

## 클라우드 환경 설정
- 네트워크: Limited + Allow package managers + 아래 도메인 허용
  `api.fal.ai`, `runware.ai`, `replicate.com`, `huggingface.co`, `hooks.slack.com`,
  `deepmind.google`, `blog.google`, `openai.com`, `elevenlabs.io`, `qwenlm.github.io`, `blog.fal.ai`,
  `bfl.ai`, `runwayml.com`, `lumalabs.ai`, `www.minimax.io`, `ai.meta.com`, `www.recraft.ai`, `ltx.io`, `suno.com`
- 환경 변수: `SLACK_WEBHOOK_URL`(실시간), `WEEKLY_SLACK_WEBHOOK_URL`(주간 정리)

## 로컬 테스트
```
pip install -r requirements.txt
cd bot && python collect.py
# out/verdicts.json 작성 후
DRY_RUN=1 python publish.py
```
