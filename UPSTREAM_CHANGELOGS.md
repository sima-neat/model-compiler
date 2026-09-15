# Private upstream changes

The component scanner compares its resolved manifest with the exact source SHA captured from `develop` at workflow start. `component-updates.*.*.upstream` maps package names to Jenkins job segments and Bitbucket repositories. Both architectures share a report when their version transitions match. Custom-source dry runs compare against the selected source SHA instead.

Jenkins records are collected before retention removes them. Completed build records, source revisions, and deduplicated commits are retained under `model-compiler/build-records/records/`; comparisons are keyed by baseline SHA and canonical resolved-manifest SHA-256 under `model-compiler/build-records/comparisons/`. Running records are never cached. Missing builds, missing revisions, cross-branch comparisons, and unverified SCM attribution are explicit. Shared Jenkins-library commits are not presented as component changes. Other unattributed entries are included separately in the private attachment.

The detailed Markdown report is sent only as a Slack file, with a bounded excerpt. It describes candidate resolution, not build success. The existing daily build-result notification remains separate. No discovered changelog is uploaded as a GitHub artifact, added to a job summary or PR, committed to Git, or published through Vulcan's public artifact workflow. Temporary private files are removed even when steps fail. Dry runs neither upload history nor send Slack messages.

## Deployment

Configure repository secrets `JENKINS_USERNAME`, `JENKINS_API_TOKEN`, and `SLACK_BOT_TOKEN`. The Slack bot needs `files:write` and access to the channel selected by `SLACK_VULCAN_EVENT_CHANNEL_ID`. The existing internal macOS scanner queries Jenkins; GitHub-hosted runners do not need internal network access.

Apply the companion Vulcan change that blocks `model-compiler/build-records` at CloudFront and explicitly denies CloudFront S3 reads. The publisher role must be able to inspect bucket policy and public-access blocks, read/write the private prefix, and use the bucket KMS key. Only then set `UPSTREAM_CHANGELOG_ENABLED=true`. The existing Vulcan configuration resolver supplies the bucket, publisher role, region, and KMS key. Storage checks fail closed unless all S3 public-access blocks and the unconditional CloudFront deny for this prefix are present. Uploads request KMS encryption and never update public artifact indexes.

With persistence disabled, Slack delivery still works, but only currently retained Jenkins records are available. Do not enable persistence against a public prefix. Jenkins outages produce incomplete-evidence reports; Slack delivery and configured storage failures fail the scan rather than silently discard evidence. No real Slack message or infrastructure deployment is performed by unit tests.

Translations: [日本語](UPSTREAM_CHANGELOGS.ja.md), [한국어](UPSTREAM_CHANGELOGS.ko.md), [繁體中文](UPSTREAM_CHANGELOGS.zh-Hant.md), [Українська](UPSTREAM_CHANGELOGS.uk.md).

The default-branch `update-components.yml` wrapper must also receive the `id-token: write` permission change when deploying the worker; reusable workflows cannot elevate caller permissions.
