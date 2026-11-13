# pr-review

Claude Code skill za review PR-ova na GitHubu, Bitbucketu i Azure DevOpsu (cloud i Server): 9 nezavisnih perspektiva, jedan rangiran izvještaj, gotovi
draft komentari. Bugovi se dokazuju pokrenutim testom. Ništa ne ide na PR bez tvoje potvrde.

## Što treba
- PowerShell 7 (`pwsh`)
- lokalni klon svakog repoa koji reviewaš
- GitHub: `gh` CLI, ulogiran s računom koji vidi repo
- Bitbucket: API token sa scopeovima, u environment varijablama (vidi ispod)
- Azure DevOps: personal access token (PAT) u environment varijabli koju imenuje `tokenVariable` (vidi ispod)
- Docker, za testove u CI okolini (UTC, invariant kultura)
- Jira connector, samo za `ticket-fit`; bez njega taj lens javi da nema pristup tiketu

## Postavljanje
1. Skill je u `%USERPROFILE%\.claude\skills\pr-review` (install.ps1 iz ai-configa ga poveže; inače kopiraj folder tamo).
2. Pokreni `/pr-review postavi`: Claude nađe git repoe u folderu s projektima, pita koje reviewaš i zapiše
   `config.local.ps1`. Može i ručno: kopiraj `config.example.ps1` u `config.local.ps1` i upiši svoje repoe. Git ignorira
   `config.local.ps1`.
3. Po želji za svaki repo napiši `repos\<repo>.md` po uzoru na `repo-notes.example.md`: što je u tom repou kritično, kako se
   vrte testovi, tko bi ga mogao napasti. Bez toga lensovi rade po općim pravilima. Git ignorira i `repos\`.
4. Prilagodi `references\ton-komentara.md` svom stilu, komentari idu pod tvojim imenom.
5. Za Bitbucket postavi environment varijable (`<WORKSPACE>` = ime workspacea velikim slovima, sve osim slova i brojki u `_`):
   ```powershell
   [Environment]::SetEnvironmentVariable('BITBUCKET_<WORKSPACE>_EMAIL', '<mail Atlassian računa>', 'User')
   [Environment]::SetEnvironmentVariable('BITBUCKET_<WORKSPACE>_TOKEN', '<token>', 'User')        # read:user:bitbucket, read:repository:bitbucket, read:pullrequest:bitbucket
   [Environment]::SetEnvironmentVariable('BITBUCKET_<WORKSPACE>_TOKEN_WRITE', '<token>', 'User')  # write:pullrequest:bitbucket, samo za objavu
   ```
   Token napravi u Atlassian postavkama računa (API tokens, "Create API token with scopes"). Upiši ga u svom terminalu, ne u chat.
6. Za Azure DevOps napravi PAT (User settings, Personal access tokens) sa scopeom Code (Read), ili Code (Read & write) ako
   ćeš objavljivati komentare, i spremi ga u varijablu čije ime upišeš kao `tokenVariable`:
   ```powershell
   [Environment]::SetEnvironmentVariable('AZURE_DEVOPS_EXAMPLE_PAT', '<token>', 'User')
   ```
   Isto vrijedi za cloud (`https://dev.azure.com/<org>`) i za Azure DevOps Server (`https://<server>/<kolekcija>`). Diff PR-a
   skripta računa lokalno, iz grana koje fetcha u klon; fetch šalje isti PAT, pa ne treba Windows prijava na server.
   Ako `git clone` na Azure DevOps Serveru javi "Authentication failed" (server nudi NTLM, a računalo nije u domeni),
   kloniraj s PAT-om upisanim u skriveni upit, bez spremanja:
   ```powershell
   $s = Read-Host 'PAT' -AsSecureString
   $t = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
   $b = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes(":$t"))
   git -c core.longpaths=true -c "http.extraHeader=Authorization: Basic $b" clone <adresa repoa> <folder>
   Remove-Variable s, t, b
   ```
7. Provjeri:
   ```
   pwsh -NoProfile -File "$HOME/.claude/skills/pr-review/scripts/pr-harvest.ps1" -List -Pretty
   ```

## Korištenje
| Komanda | Što radi |
|---|---|
| `/pr-review` | ponudi otvorene PR-ove svih repoa iz configa |
| `/pr-review shop-api 42` | puni review, ili delta ako si već reviewao |
| `/pr-review 42` | isto, kad je u configu samo jedan repo |
| `/pr-review shop-api 42 full` | cijeli PR iznova |
| `/pr-review shop-api 42 quick` | bugs + arhitektura + testovi, bez builda |
| `/pr-review shop-api 42 only bugs,sigurnost` | samo navedene perspektive |
| `/pr-review objavi shop-api 42 1,3` | preview komentara #1 i #3, pa objava tek nakon "da" |

Puni review pušta 9 subagenata i gradi kod, pa troši dosta tokena i traje. Za brzi prolaz koristi `quick`.

Sve spremljeno ide u `%USERPROFILE%\pr-review\` (mijenja se u `config.local.ps1`).

## Fajlovi
- `SKILL.md`: tijek reviewa
- `config.example.ps1`: primjer configa; tvoj je `config.local.ps1`
- `repo-notes.example.md`: primjer bilješki za jedan repo; tvoje su u `repos\`
- `scripts\`: dohvat PR-a i objava komentara
- `lenses\`: po jedan fajl za svaku perspektivu
- `references\`: ton komentara, karta kritičnosti, napomene za pokretanje testova, vizualni preview
