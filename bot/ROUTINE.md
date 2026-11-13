# 예약 실행 절차

매 실행마다 아래 순서를 그대로 따르세요. 순서를 바꾸거나 단계를 건너뛰지 마세요.
웹 검색이나 다른 조사는 하지 마세요. 판단 근거는 후보에 담긴 정보뿐입니다.

모든 명령은 저장소 최상위 폴더에서 실행합니다.

1. 패키지 설치: `python -m pip install -q -r requirements.txt`
2. 수집: `(cd bot && python collect.py)`. fal.ai 목록을 읽느라 2~3분 걸리니 끝날 때까지 기다립니다.
   - 마지막 줄의 `CANDIDATES=<개수>` 를 확인합니다.
3. 후보가 0개면 5단계로 갑니다.
4. 후보가 1개 이상이면:
   1. `bot/rules.md` 를 읽습니다.
   2. `out/candidates.json` 의 모든 후보를 기준에 따라 판단해서 `out/verdicts.json` 을 씁니다. 후보 하나도 빠뜨리지 마세요.
   3. `(cd bot && python publish.py)` 를 실행합니다.
   4. 형식 오류가 나오면 오류 내용대로 `out/verdicts.json` 을 고쳐서 다시 실행합니다. 최대 2번까지 다시 시도하고, 그래도 실패하면 5단계로 가지 말고 멈춥니다.
5. 기록 저장: `state/` 에 변경이 있으면 main 브랜치에 바로 커밋하고 푸시합니다.
   - `git add state/ && git commit -m "update seen state" && git push origin HEAD:main`
   - 다른 브랜치를 만들거나 PR 을 열지 마세요. 다른 파일은 커밋하지 마세요.
6. 끝에 한 줄로 결과를 남깁니다: 후보 개수, 전송 건수, 실패한 소스.
