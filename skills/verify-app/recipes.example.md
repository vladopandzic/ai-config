# How to run apps locally

Copy this file to `recipes.local.md` (not in git) and add a section per repo whose own repository has no run skill. Prefer a run skill inside the repo when the team can share it.

## <repo name>

- **Path:** `C:\sources\<repo>`
- **Build:** the exact command, SDK version and flags (for example a private feed that needs `-p:NuGetAudit=false`).
- **Run:** command, environment variables and port. Prefer fake or in-memory data and a development login bypass.
- **Wait for:** the log line or URL that means it is up.
- **Login:** where the local test user comes from (user-secrets key, seed file); never the values themselves.
- **Data:** which database it uses and what may be changed during a check.
- **Before version:** anything special for the base build (submodules, a fixed port).
- **Known traps:** what breaks and how to get around it.
