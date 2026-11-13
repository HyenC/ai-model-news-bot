# 예약 실행 절차

매 실행마다 아래 순서를 그대로 따르세요. 순서를 바꾸거나 단계를 건너뛰지 마세요.
웹 검색이나 다른 조사는 하지 마세요. 판단 근거는 후보에 담긴 정보뿐입니다.

모든 명령은 저장소 최상위 폴더에서 실행합니다.

1. 패키지 설치: `python -m pip install -q -r requirements.txt`
2. 우리 서비스 모델 목록 받기:
   - 드롭샷 커넥터의 `list_models` 도구를 한 번만 호출합니다. 드롭샷 커넥터의 다른 도구(이미지·영상 생성, 업로드 등)는 절대 호출하지 마세요. 크레딧이 나갑니다.
   - 결과의 `modelList` 에서 각 모델의 `name`, `displayName`, `provider`, `type` 만 뽑아 `out/served_models.json` 에 JSON 목록으로 저장합니다. 결과가 길어 파일로 저장되면 그 파일에서 python 이나 jq 로 뽑습니다.
   - 커넥터가 없거나 호출이 실패하면 파일을 만들지 말고 다음 단계로 갑니다. (이번 회차의 종료 공지 판단은 다음 회차로 미뤄집니다)
3. 수집: `(cd bot && python collect.py)`. fal.ai 목록을 읽느라 2~3분 걸리니 끝날 때까지 기다립니다.
   - 마지막 두 줄의 `CANDIDATES=<개수>`, `RETIREMENTS=<개수>` 를 확인합니다.
4. 둘 다 0개면 6단계로 갑니다.
5. 하나라도 1개 이상이면 `bot/rules.md` 를 읽고:
   1. CANDIDATES 가 1개 이상이면 `out/candidates.json` 의 모든 후보를 판단해서 `out/verdicts.json` 을 씁니다.
   2. RETIREMENTS 가 1개 이상이고 `out/served_models.json` 이 있으면 `out/retirements.json` 의 모든 후보를 판단해서 `out/retire_verdicts.json` 을 씁니다.
   3. 후보 하나도 빠뜨리지 마세요.
   4. `(cd bot && python publish.py)` 를 실행합니다.
   5. 형식 오류가 나오면 오류 내용대로 판단 파일을 고쳐서 다시 실행합니다. 최대 2번까지 다시 시도하고, 그래도 실패하면 6단계로 가지 말고 멈춥니다.
6. 기록 저장: `state/` 에 변경이 있으면 main 브랜치에 바로 커밋하고 푸시합니다.
   - `git add state/ && git commit -m "update seen state" && git push origin HEAD:main`
   - 다른 브랜치를 만들거나 PR 을 열지 마세요. 다른 파일은 커밋하지 마세요.
7. 끝에 한 줄로 결과를 남깁니다: 새 모델 후보·전송 건수, 종료 공지 후보·전송 건수, 서비스 모델 목록을 받았는지, 실패한 소스.
