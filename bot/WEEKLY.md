# 주간 정리 절차 (매주 월요일 09:00 KST)

아래 순서를 그대로 따르세요. Confluence 사이트와 페이지를 만들 상위 폴더 ID 는 실행 요청 메시지에 있습니다.
모든 명령은 저장소 최상위 폴더에서 실행합니다.

**절대 하지 말 것**
- 드롭샷 커넥터에서 `list_models` 말고 다른 도구 호출 (생성 도구는 크레딧이 나갑니다)
- Confluence 에서 페이지 만들기·읽기 말고 다른 작업 (기존 페이지 수정·삭제·댓글 금지)
- 서비스 모델 이름, Confluence 주소, 폴더 ID 를 저장소 파일에 쓰거나 커밋하기 (공개 저장소입니다. `out/` 은 커밋되지 않습니다)

## 순서
1. 패키지 설치: `python -m pip install -q -r requirements.txt`
2. 우리 서비스 모델 목록: 드롭샷 커넥터의 `list_models` 를 한 번 호출해서, `modelList` 의 `name`, `displayName`, `provider`, `type` 만 `out/served_models.json` 에 저장합니다. 결과가 파일로 저장되면 그 파일에서 jq 로 뽑습니다. 실패하면 "기존 서빙 모델 업데이트" 절을 빼고 진행합니다. 이때 `(cd bot && python alert.py weekly_list_models "<테스트면 [테스트] >드롭샷 list_models 실패: <오류 내용 한 줄>")` 로 관리자에게 알립니다.
3. 준비: `(cd bot && python weekly.py prepare)`. 출력의 `WEEK`, `TITLE`, `CATALOG_OK` 를 확인합니다.
   - 실행 요청이 테스트 실행이면 이 단계부터 `WEEKLY_TEST=1` 을 붙여 실행합니다(제목·메시지에 테스트 표시).
4. 조사·작성: `bot/weekly_rules.md` 를 읽고 그대로 따라 페이지 본문을 `out/weekly_page.md` 에 씁니다.
5. 같은 제목의 페이지가 이미 있는지 확인: Atlassian 커넥터 `executeRead` 로 `getConfluenceContentDescendants` (contentId=상위 폴더 ID, depth=1, limit=250) 를 호출해 제목이 `TITLE` 과 같은 페이지를 찾습니다.
   - 있으면 새로 만들지 말고 그 페이지 주소를 씁니다.
   - 없으면 `createConfluenceContent` 로 만듭니다: contentType=`live_doc`, parent=`{"parentContentId": "<상위 폴더 ID>"}`, title=`TITLE`, body=`{"format": "markdown", "value": <out/weekly_page.md 내용>}`. 만들기 전에 도구 설명이 요구하는 형식 안내(`getContentFormatGuide`)와 스페이스 안내를 `executeRead` 로 확인합니다.
   - 응답의 페이지 주소(webUrl)를 확인합니다.
   - 페이지를 만들지 못하면 `(cd bot && python alert.py weekly_confluence "<테스트면 [테스트] >Confluence 페이지 생성 실패: <오류 내용 한 줄>")` 로 관리자에게 알리고 멈춥니다.
6. `out/weekly_digest.json` 작성 (형식은 `bot/weekly_rules.md` 끝) 후 전송: `(cd bot && python weekly.py send)`
   - 형식 오류면 고쳐서 최대 2번 다시 실행합니다.
   - 그래도 실패하거나 슬랙 전송이 실패하면 `(cd bot && python alert.py weekly_send "<테스트면 [테스트] >주간 슬랙 전송 실패: <오류 내용 한 줄>")` 로 관리자에게 알립니다.
7. 기록 저장 (테스트 실행이면 건너뜀): `state/weekly_sent.json` 에 변경이 있으면
   `git add state/weekly_sent.json && git commit -m "weekly digest sent" && git pull --rebase origin main && git push origin HEAD:main`
   다른 파일은 커밋하지 마세요. 푸시가 끝내 실패하면 `(cd bot && python alert.py weekly_push "주간 기록 푸시 실패: <오류 내용 한 줄>")` 로 알립니다.
8. 끝에 한 줄로 결과를 남깁니다: 대상 주, 데일리 기록 수, 웹에서 찾은 후보 수, 페이지 생성 여부, 슬랙 전송 여부, 실패한 단계.
