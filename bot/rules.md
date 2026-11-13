# 판단 기준

우리는 AI 생성 서비스 회사입니다. 새 이미지·영상·오디오 생성 모델을 경쟁사보다 빨리 서비스에 붙이는 것이 목표입니다.
`out/candidates.json` 의 각 항목을 아래 기준으로 판단해서 `out/verdicts.json` 을 만드세요.

## relevant=true 로 볼 것
- 새로 공개되거나 새 버전이 나온 이미지·영상·오디오(음성, 음악, 효과음) 생성·편집 모델
- 기존 모델이 새 플랫폼(fal.ai 등)에 처음 API 로 올라온 경우
- 원래 모델을 만든 곳이 직접 낸 공식 경량화·고속 버전 (예: Turbo, Lite, Flash, Fast, Highspeed, Distilled, 공식 FP8 등). 성능은 비슷하면서 더 빠르거나 싸게 쓸 수 있어서 중요합니다
- 위 모델의 공개 발표 글

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

## relevant=true 인 항목에 채울 내용 (한국어)
근거는 후보에 주어진 정보뿐입니다. 모르는 것은 지어내지 말고 "확인 안 됨"이라고 쓰세요. 웹 검색으로 정보를 보태지 마세요.
- model_name: 모델 이름과 버전
- maker: 만든 곳
- modality: "이미지", "영상", "오디오", "멀티모달" 중 하나
- summary_ko: 무엇을 할 수 있는지, 이전 버전이나 다른 모델과 비교해 무엇이 새로운지 2~3문장. 경량화·고속 버전이면 원래 모델 대비 속도·가격·품질 차이를 정보에 있는 만큼 쓰세요
- availability: 지금 어디서 쓸 수 있는지 (예: "fal.ai API", "Hugging Face 오픈 가중치(라이선스: apache-2.0)", "발표만, 공개 일정 확인 안 됨")

## out/verdicts.json 형식
후보 하나당 항목 하나. relevant=false 면 나머지 필드는 빈 문자열, modality 는 "해당 없음".
```json
{"items": [
  {"id": "fal:bytedance/seedream/v5.5/text-to-image", "relevant": true,
   "model_key": "seedream-5.5", "model_name": "Seedream 5.5", "maker": "ByteDance",
   "modality": "이미지", "summary_ko": "...", "availability": "fal.ai API"},
  {"id": "rss:https://...", "relevant": false, "model_key": "", "model_name": "",
   "maker": "", "modality": "해당 없음", "summary_ko": "", "availability": ""}
]}
```
