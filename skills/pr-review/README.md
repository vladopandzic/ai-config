# pr-review

Claude Code skill za review PR-ova na GitHubu i Bitbucketu: 9 nezavisnih perspektiva, jedan rangiran izvještaj, gotovi
draft komentari. Bugovi se dokazuju pokrenutim testom. Ništa ne ide na PR bez tvoje potvrde.

## Što treba
- PowerShell 7 (`pwsh`)
- lokalni klon svakog repoa koji reviewaš
- GitHub: `gh` CLI, ulogiran s računom koji vidi repo
- Bitbucket: API token sa scopeovima, u environment varijablama (vidi ispod)
- Docker, za testove u CI okolini (UTC, invariant kultura)
- Jira connector, samo za `ticket-fit`; bez njega taj lens javi da nema pristup tiketu

## Postavljanje
1. Skill je u `%USERPROFILE%\.claude\skills\pr-review` (install.ps1 iz ai-configa ga poveže; inače kopiraj folder tamo).
2. Kopiraj `config.example.ps1` u `config.local.ps1` i upiši svoje repoe. Git ignorira `config.local.ps1`.
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
6. Provjeri:
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
