# Security Policy

EmComm Control can be used during real-world emergency-communications operations, so operational data must be treated carefully.

## Do not publish

Do not include any of the following in GitHub issues, pull requests, screenshots, or example logs:

- Credentials, API keys, MQTT credentials, or access tokens
- Private node databases or unpublished node identifiers
- Sensitive location information
- Personally identifiable information
- Protected medical information
- Real emergency traffic that should not be made public
- Served-agency information that is not approved for public release

## LIVE mode

LIVE mode must be enabled locally with `--mode live --confirm-live`. Inbound mesh traffic cannot enable it. Simulated injects are blocked while LIVE.

The script logs operator-supplied traffic locally. Operators are responsible for following applicable laws, radio-service rules, local emergency plans, served-agency procedures, and information-security requirements.

## Reporting a vulnerability

For security-sensitive reports, contact the repository owner privately through an appropriate GitHub contact method instead of opening a public issue.
