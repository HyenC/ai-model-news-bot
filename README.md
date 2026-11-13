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
- 같은 모델은 소스별로 30일 안에 한 번만 보냅니다. (예: HF 공개 후 fal.ai 등록은 따로 알림)
- 공식 경량화·고속 버전은 보내고, 다른 곳이 만든 경량화 버전은 보내지 않습니다.

## 클라우드 환경 설정
- 네트워크: Limited + Allow package managers + 아래 도메인 허용
  `api.fal.ai`, `runware.ai`, `replicate.com`, `huggingface.co`, `hooks.slack.com`,
  `deepmind.google`, `blog.google`, `openai.com`, `elevenlabs.io`, `qwenlm.github.io`, `blog.fal.ai`,
  `bfl.ai`, `runwayml.com`, `lumalabs.ai`, `www.minimax.io`, `ai.meta.com`, `www.recraft.ai`, `ltx.io`, `suno.com`
- 환경 변수: `SLACK_WEBHOOK_URL`

## 로컬 테스트
```
pip install -r requirements.txt
cd bot && python collect.py
# out/verdicts.json 작성 후
DRY_RUN=1 python publish.py
```
