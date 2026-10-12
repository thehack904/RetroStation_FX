# Security Policy

## Supported versions

RSFX follows a rolling release model. Security fixes are provided for the
current public release series. Users should stay on the latest release, and
security fixes will be included in the next patch release when practical.

| Version | Supported |
| --- | --- |
| 0.1.x (latest) | Supported |
| Private prototype / pre-release builds | Not supported |

There have been no earlier public RSFX releases.

## Reporting a vulnerability

Use GitHub's **Private vulnerability reporting** or **private security
advisory** workflow from the repository's **Security** tab. Do not report
suspected vulnerabilities in public issues or discussions.

Please include the following information when possible:

- Description of the suspected vulnerability
- Steps to reproduce it
- Affected RSFX version(s)
- Potential impact
- Suggested remediation, if available

Do not include passwords, tokens, or other secrets in a report. Redact
credentials and sensitive personal information from logs and reproduction
materials.

Please allow time for investigation and coordinated remediation. Do not publish
exploit details or other information that would enable exploitation before a
fix or mitigation is available.

## Scope and deployment

RSFX is designed for trusted or controlled network use. Its management
interface has no authentication and is not intended to be exposed directly to
the public internet without additional protections. Use a restricted trusted
network, VPN, or an authenticated reverse proxy with appropriate firewall
controls.

Reports should identify a software vulnerability in RSFX or a dependency.
Deployment and configuration problems alone—such as exposing the unauthenticated
interface without additional protections or misconfigured firewalls, VPNs, or
reverse proxies—are not software vulnerabilities. If a software flaw enables
exploitation beyond the intended behavior, report it privately.

## Secrets accidentally committed to a public repository

Treat any credential or secret committed to a public repository as compromised,
even if the commit or file is later removed. Revoke or rotate it immediately
with the issuing service, remove the exposure from the repository and its
history where practical, and check for other uses of the same secret. Do not
repeat the secret in a report; use GitHub's private vulnerability reporting
workflow and provide only the affected file or commit details needed to locate
the exposure.
