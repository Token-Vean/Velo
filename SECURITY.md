# Security policy and local-use threat model

## Scope

Velo is designed for **strictly local and personal use** by a professional user on a workstation. Its default threat model is **not** a public web deployment, a multi-user service, or a network-facing document platform.

## Security assumptions

- The application binds to `127.0.0.1` only.
- Documents are processed on the local machine.
- The operator remains responsible for validating detections and exports.
- Derived outputs must be reviewed before external circulation.

## Hardening choices in this revision

- Local-only install with isolated `.venv`.
- No automatic remote Python bootstrap in the Windows installer.
- CSRF protection and same-origin checks.
- Security headers and `no-store` policy on dynamic responses.
- Rotating audit log under the configured workspace.
- Ephemeral visual sessions with stale-session cleanup.
- Explicit user action before applying redactions over the original-derived PDF.
- Demo sample replaced with clearly synthetic content.

## Known residual risks

- Document parsers remain complex third-party dependencies.
- OCR quality and bbox alignment may vary on degraded scans.
- This project does not sandbox parser execution at OS level.
- Local logs and reports remain sensitive and should be handled accordingly.

## Recommended operational controls

- Use on a dedicated professional workstation.
- Exclude `workspace/` from unnecessary cloud sync or consumer backup tools.
- Protect the OS account with full-disk encryption.
- Keep dependencies updated and monitor advisories.
- Avoid processing untrusted files from unknown sources without prior malware screening.
- Enable the repository hook path with `git config core.hooksPath .githooks`.

## Reporting

For sensitive security findings, do not publish exploit details in public issue threads before mitigation is prepared.
