---
title: SSO login troubleshooting
category: login_issue
tags: [sso, saml, okta, login, 502]
summary: Diagnose SAML and OIDC sign-in failures and callback errors.
---

# SSO login troubleshooting

## Symptoms
Users are redirected back to CloudDesk with a 502 or "invalid assertion" error after authenticating with the identity provider.

## Check service status first
If the status page shows an active SSO incident, sign-in failures on the callback step are caused by CloudDesk, not by the customer configuration. Do not ask the customer to change identity provider settings during an active incident.

## Customer-side checks
1. Confirm the ACS URL and entity ID in the identity provider match the values in workspace SSO settings.
2. Confirm the signing certificate has not expired or been rotated without updating CloudDesk.
3. Check that the user's email in the identity provider matches their CloudDesk email.

## Workaround
Workspace admins can sign in with a password from the admin recovery link while SSO is degraded. Enterprise outages are escalated to the Identity on-call team.
