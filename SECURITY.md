# Security

This repository is a **demo**: a hospital chain's data architecture on a local Exasol Personal database, with
synthetic patients. It is not clinical software and must never be pointed at real patient data.

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue: on GitHub, open the repository's **Security** tab
and choose **Report a vulnerability**. You will get an answer within a few working days.

## What the demo does with secrets and access

- The branch systems' passwords, the two named database users' passwords and the read-only S3 key are generated during
  the build into `secrets/` (git-ignored, mode 600) and never printed. No password is written in the code.
- The S3 key belongs to a read-only IAM user limited to this demo's part of one bucket. It is long-lived:
  `setup/uninstall.sh --yes --aws` deletes it.
- Connections to Exasol Personal use TLS **without verifying the certificate** (`nocertcheck`, `-k`), because it serves
  a self-signed certificate on this machine. Never copy that to a connection to a real Exasol cluster.
- The Streamlit fallback console listens on `127.0.0.1` only; it has no login and must not be exposed.
- Images are shown through presigned S3 links that expire after 15 minutes.
