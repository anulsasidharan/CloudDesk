---
title: Slack integration troubleshooting
category: integration
tags: [slack, integration, notifications, webhook]
summary: Fixing a Slack integration that stopped posting notifications.
---

# Slack integration troubleshooting

## Common causes
The Slack channel was renamed or archived, the bot was removed from the channel, or the authorisation token was revoked by a Slack admin.

## Steps
1. Open Integrations and choose Slack.
2. Disconnect and reconnect, authorising the workspace again.
3. Re-select the channel, invite the CloudDesk bot, and send a test notification.

## Service issues
Check the status page for delayed webhooks before asking the customer to reconfigure.
