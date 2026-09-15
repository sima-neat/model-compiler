# 비공개 업스트림 변경 기록

컴포넌트 스캐너는 확정된 매니페스트를 워크플로 시작 시 캡처한 정확한 `develop` SHA와 비교합니다. `component-updates.*.*.upstream`은 패키지 이름을 Jenkins 작업 및 Bitbucket 저장소에 연결합니다. 버전 전환이 같으면 두 아키텍처가 보고서를 공유합니다. 사용자 지정 소스의 드라이런은 선택한 소스 SHA를 기준으로 비교합니다.

완료된 Jenkins 빌드, 소스 리비전, 중복을 제거한 커밋은 `model-compiler/build-records/records/`에 저장됩니다. 비교 결과는 기준 SHA와 확정된 매니페스트의 SHA-256을 키로 사용하여 `model-compiler/build-records/comparisons/`에 저장됩니다. 실행 중인 빌드는 캐시하지 않습니다. 누락된 기록과 리비전, 브랜치 간 비교, 확인되지 않은 SCM 출처를 명시합니다. 공유 Jenkins 라이브러리 커밋은 컴포넌트 변경으로 표시하지 않으며 출처가 불명확한 항목은 비공개 첨부 파일에 별도로 표시합니다.

상세 보고서는 짧은 발췌문과 Markdown 파일로 Slack에만 전송합니다. 이는 후보 버전 확정 결과이며 빌드 성공 알림이 아닙니다. 기존 빌드 결과 알림은 별도로 유지됩니다. 변경 기록을 GitHub 아티팩트, 작업 요약, PR, Git 또는 Vulcan 공개 아티팩트에 게시하지 않습니다. 실패 시에도 임시 파일을 삭제합니다. 드라이런에서는 기록 업로드와 Slack 전송을 하지 않습니다.

## 배포

저장소 시크릿 `JENKINS_USERNAME`, `JENKINS_API_TOKEN`, `SLACK_BOT_TOKEN`을 설정합니다. Slack 봇에는 `files:write`와 `SLACK_VULCAN_EVENT_CHANNEL_ID` 채널 접근 권한이 필요합니다. 내부 macOS 스캐너가 Jenkins를 조회합니다.

관련 Vulcan 변경을 적용하여 CloudFront와 S3 정책에서 `model-compiler/build-records`의 공개 읽기를 차단한 후 `UPSTREAM_CHANGELOG_ENABLED=true`를 설정합니다. 기존 Vulcan 설정에서 버킷, 역할, 리전, KMS 키를 가져옵니다. 역할에는 버킷 정책 및 공개 접근 차단 확인, 비공개 경로 읽기/쓰기, KMS 권한이 필요합니다. 모든 S3 공개 접근 차단과 무조건적인 CloudFront 거부를 확인하지 못하면 저장을 중단합니다. 업로드는 KMS 암호화를 사용하며 공개 인덱스를 변경하지 않습니다.

저장을 비활성화해도 Slack 전송은 가능하지만 Jenkins에 남아 있는 기록만 사용할 수 있습니다. Jenkins 장애는 불완전한 근거로 표시합니다. Slack 전송 또는 설정된 저장소 오류는 스캔을 실패시킵니다. 단위 테스트는 실제 전송이나 인프라 배포를 수행하지 않습니다.

워커 배포 시 기본 브랜치의 `update-components.yml`에도 `id-token: write` 권한 변경을 반영해야 합니다. 재사용 워크플로는 호출자의 권한을 높일 수 없습니다.
