# 판단 기준

우리는 AI 생성 서비스 회사입니다. 새 이미지·영상·오디오 생성 모델을 경쟁사보다 빨리 서비스에 붙이는 것이 목표입니다.
`out/candidates.json` 의 각 항목을 아래 기준으로 판단해서 `out/verdicts.json` 을 만드세요.

## relevant=true 로 볼 것
- 새로 공개되거나 새 버전이 나온 이미지·영상·오디오(음성, 음악, 효과음) 생성·편집 모델
- 기존 모델이 새 플랫폼(fal.ai 등)에 처음 API 로 올라온 경우
- 원래 모델을 만든 곳이 직접 낸 공식 경량화·고속 버전 (예: Turbo, Lite, Flash, Fast, Highspeed, Distilled, 공식 FP8 등). 성능은 비슷하면서 더 빠르거나 싸게 쓸 수 있어서 중요합니다
- 위 모델의 공개 발표 글. 아직 쓸 수 없는 출시 예정 발표(공개 예고, 대기 명단, 프리뷰 신청, "곧 출시" 등)도 포함하고 upcoming=true 로 표시

## relevant=false 로 볼 것
- LLM, 음성 인식, 비전 이해, 3D 전용 모델
- 개인 파인튜닝, LoRA
- 원 제작사가 아닌 곳(개인, 다른 회사)이 만든 경량화(quantization, GGUF, FP8, NVFP4 등)·포맷 변환 버전. 올린 계정이 원 제작사와 다르면 비공식으로 봅니다
- 회사 소식, 튜토리얼, 사례 소개, 행사, 채용 등 모델 출시가 아닌 글
- 이미 있는 모델의 사소한 옵션 추가(예: 업스케일 옵션, 입력 형식만 다른 엔드포인트). 단, 완전히 새 기능이면 true

## model_key
- 같은 모델의 여러 엔드포인트(예: text-to-image 와 edit)는 model_key 를 똑같이 맞추세요.
- 공식 경량화·고속 버전은 원래 모델과 다른 model_key 를 쓰세요(예: "h3-image" 와 "h3-image-highspeed").
- 소문자, 버전 포함, 만든 곳 이름은 빼세요(예: "seedream-5.5", "veo-4").
- 중복 알림을 막는 기준이 model_key 입니다. `state/seen.json` 의 `posted` 에 이미 있는 model_key 와 같은 모델·같은 버전이면 그 값을 글자 그대로 쓰세요(예: 이미 "seedance-2.5-flash" 가 있으면 "seedance-2-5-flash" 로 바꿔 쓰지 않기).

## relevant=true 인 항목에 채울 내용 (한국어)
근거는 후보에 주어진 정보와 `out/catalog.tsv` 뿐입니다. 모르는 것은 지어내지 말고 아예 쓰지 마세요("확인 안 됨" 같은 문구도 쓰지 마세요). 웹 검색으로 정보를 보태지 마세요.
- model_name: 모델 이름과 버전
- maker: 만든 곳
- modality: "이미지", "영상", "오디오", "멀티모달" 중 하나
- one_liner: 이 모델이 무엇인지 한 문장 (40자 안팎)
- features: 이 모델의 특징 2~4개. 한 항목에 한 가지 사실만, 짧게(25자 안팎). 할 수 있는 작업, 입력·출력 조건(참조 이미지 수, 해상도, 길이, 오디오 동시 생성 등), 새 기능 위주
- vs_previous: 이전 버전이나 원래 모델과 비교해 달라진 점 한두 문장. 경량화·고속 버전이면 속도·가격·품질 차이. 후보 정보에 비교 근거가 없으면 빈 문자열로 두세요("확인 안 됨"이라고 쓰지 마세요). 메시지에서 이 항목이 빠집니다
- upcoming: 아직 쓸 수 없고 출시 예정만 발표된 경우 true, 지금 쓸 수 있으면 false
- other_availability: Replicate·Runware·BytePlus·Google·fal.ai 말고 쓸 수 있는 곳 (예: "Hugging Face 오픈 가중치(라이선스: apache-2.0)", "Alibaba Cloud Model Studio API"). 없거나 모르면 빈 문자열
- platforms: Replicate·Runware·BytePlus·Google(Gemini API)·fal.ai 에 이 모델이 있는지. `out/catalog.tsv` 에서 모델 이름으로 찾아(예: `grep -i seedream out/catalog.tsv`), 같은 모델·같은 버전이 있으면 그 행의 url 을, 없으면 빈 문자열을 넣습니다. 비슷한 이전 버전(예: 5.5 를 찾는데 5.0 만 있음)은 없는 것으로 봅니다. url 은 catalog 에 있는 값을 그대로 복사하세요
  - BytePlus 는 모델 ID 가 `dreamina-seedance-2-5-flash-261115` 처럼 하이픈과 끝의 버전 날짜로 되어 있습니다. `grep -i 'seedance-2-5' out/catalog.tsv` 처럼 찾습니다. ID 안의 이름이 같은 모델·같은 버전일 때만 있는 것으로 봅니다(2-5 와 2-5-flash 는 다른 모델).
  - Google 은 `gemini-3.1-flash-image` 처럼 Gemini API 모델 ID 로 되어 있습니다. Gemini API 모델 목록에서 온 후보(source=google)의 description 은 Gemini API 변경 기록에서 그 ID 가 나온 문단입니다(없으면 비어 있음). Google 은 제품 이름과 ID 가 다를 수 있습니다(예: Nano Banana 계열은 `gemini-...-image`). 같은 모델이라는 근거가 후보 정보에 있을 때만 있는 것으로 봅니다.
  - BytePlus 모델 목록에서 온 후보(source=byteplus)의 description 은 그 모델 시리즈의 BytePlus 문서 본문입니다. 시리즈 안 다른 모델(예: Seedance 2.5 와 2.5 flash)의 내용이 섞여 있을 수 있으니, 후보 ID 의 모델에 해당한다고 문서에 나온 사실만 씁니다.

## out/verdicts.json 형식
후보 하나당 항목 하나. relevant=false 면 문자열 필드는 빈 문자열, features 는 빈 목록, upcoming 은 false, platforms 는 다섯 값 모두 빈 문자열, modality 는 "해당 없음".
```json
{"items": [
  {"id": "fal:bytedance/seedream/v5.5/text-to-image", "relevant": true,
   "model_key": "seedream-5.5", "model_name": "Seedream 5.5", "maker": "ByteDance",
   "modality": "이미지",
   "one_liner": "ByteDance의 이미지 생성·편집 모델 새 버전",
   "features": ["텍스트→이미지, 이미지 편집", "참조 이미지 최대 10장", "투명 배경 PNG 출력", "레이어 분리(Layerize)"],
   "vs_previous": "",
   "upcoming": false,
   "other_availability": "",
   "platforms": {"replicate": "", "runware": "https://runware.ai/models/bytedance-seedream-5-5", "byteplus": "", "google": "", "fal": "https://fal.ai/models/bytedance/seedream/v5.5/text-to-image"}},
  {"id": "rss:https://...", "relevant": false, "model_key": "", "model_name": "", "maker": "",
   "modality": "해당 없음", "one_liner": "", "features": [], "vs_previous": "", "upcoming": false, "other_availability": "",
   "platforms": {"replicate": "", "runware": "", "byteplus": "", "google": "", "fal": ""}}
]}
```

---

# 제공 종료 공지 판단 기준

`out/retirements.json` 의 각 항목은 모델 제공 종료(deprecation)와 관련 있을 수 있는 공지 문단입니다.
우리 서비스 모델 목록 `out/served_models.json` 과 대조해서 `out/retire_verdicts.json` 을 만드세요.
근거는 항목의 text, context(바로 앞 제목이나 문단), source_label 과 served_models.json 뿐입니다. 웹 검색은 하지 마세요.

## relevant=true 로 볼 것
- 우리가 서비스하는 모델(served_models.json 의 같은 모델·같은 버전)의 제공 종료, 종료 예정, 종료일 확정·변경 공지
- 표의 한 행이면 종료일(Shutdown date 등)이 정해져 있거나 "deprecated" 로 표시된 경우만. "No shutdown date announced" 처럼 종료 계획이 없으면 false

## relevant=false 로 볼 것
- 우리가 서비스하지 않는 모델, 이름만 비슷한 다른 버전(예: 우리는 Kling 2.6 인데 공지는 Kling 2.1)
- 모델이 아니라 API 파라미터, SDK, 기능, 요금제 등의 종료
- 이미 종료일이 지난 오래된 공지

## relevant=true 인 항목에 채울 내용 (한국어)
- served_models: 해당하는 우리 서비스 모델의 displayName 목록. served_models.json 의 displayName 을 그대로 복사하세요
- model_name: 공지에 나온 모델 이름
- maker: 모델을 만든 곳
- where: 어디서 종료되는지 한 줄. 예: "Runware에서 제공 종료 예정", "fal.ai에서 제공 종료 예정", "OpenAI API에서 종료 예정", "Gemini API에서 종료 예정"
- shutdown_date: 종료일 "YYYY-MM-DD". 공지에 없으면 빈 문자열
- replacement: 공지에 나온 대체 모델. 없으면 빈 문자열
- summary: 공지 내용 한두 문장. 종료 뒤에 어떻게 되는지(요청 실패, 자동 전환 등)가 나와 있으면 포함

## out/retire_verdicts.json 형식
후보 하나당 항목 하나. relevant=false 면 나머지 필드는 빈 값.
```json
{"items": [
  {"id": "deprecation:OpenAI 종료 일정#0123abcd", "relevant": true,
   "served_models": ["GPT Image 2.0"], "model_name": "gpt-image-2", "maker": "OpenAI",
   "where": "OpenAI API에서 종료 예정", "shutdown_date": "2027-03-01",
   "replacement": "gpt-image-2.6-flare", "summary": "gpt-image-2 가 2027-03-01 에 종료되며, 그 뒤 요청은 실패합니다."},
  {"id": "fal_retire:fal-ai/glm-image@2026-12-10", "relevant": false, "served_models": [], "model_name": "",
   "maker": "", "where": "", "shutdown_date": "", "replacement": "", "summary": ""}
]}
```
