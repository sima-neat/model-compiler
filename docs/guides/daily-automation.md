# Daily Model Compiler automation

`Schedule Component Updates` runs at 00:17, 04:17, 08:17, 12:17, 16:17, and
20:17 UTC. GitHub reads the schedule from main, but the wrapper calls
`update-components.yml@develop`. Both the updater code and the manifest are
loaded from the resolved develop commit. Manual dispatch uses the same develop
workflow. There is no duplicate daily schedule on main.

The updater publishes candidates to `daily`. Its ordinary Build packages,
installs, tests, and publishes both architectures. Build summaries expose the
actual resolved component versions. Identical candidates do not rebuild;
changes in develop refresh daily even without dependency pin changes.

The default-branch completion listeners create a tested daily-to-develop PR
and notify neat-vulcan-events on successful or failed daily builds, including
cancelled builds. Slack uses the organization's SLACK_BOT_TOKEN secret and
SLACK_VULCAN_EVENT_CHANNEL_ID variable. Notification and PR-summary scripts
run from trusted main code, not from downloaded artifacts.

The develop implementation must be merged before activating the wrapper.
This promotion only deploys automation; it does not promote unrelated compiler
or container changes to main.
