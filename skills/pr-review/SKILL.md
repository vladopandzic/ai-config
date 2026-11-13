---
name: pr-review
description: Multi-perspective PR review za GitHub, Bitbucket i Azure DevOps repoe iz config.local.ps1. Harvesta PR (diff, komentari, CI, tiket), paralelno pušta nezavisne perspektive (bugs/arhitektura/testovi/sigurnost/perf/konvencije/ticket-fit/neriješeni komentari/dizajn), svaku provjerenu u lokalnom repou, i spaja ih u jedan rangiran izvještaj s gotovim draft komentarima. Bug nalazi se dokazuju pokrenutim testom. Ništa se ne objavljuje na PR bez izričite potvrde.
user-invocable: true
---

# pr-review — multi-perspective PR review

Harvest jednog PR-a → paralelne perspektive (svaka svoj subagent + lens fajl) → jedan objedinjeni, rangiran izvještaj s
gotovim komentarima. **Ništa se ne objavljuje na PR bez potvrde.**

Argumenti: prazno = izbor PR-a · `[<repo>] <broj>` · `[<repo>] <broj> delta|full|quick|only <lens,...>` ·
`objavi [<repo>] <broj> [brojevi]` · `postavi`. `<repo>` smije izostati kad je u configu samo jedan repo.

Putanje u ovom fajlu kreću od foldera skilla, `$HOME/.claude/skills/pr-review/`. Repoi, hostovi i lokalni klonovi su u
`config.local.ps1`. Ako skripta javi da ga nema, napravi ga kroz `postavi` i tek onda nastavi.

## Postavi → složi config.local.ps1

1. Ako `config.local.ps1` već postoji, pročitaj ga: dodaješ repoe koji fale, postojeće ne diraš.
2. Pitaj u kojem folderu korisnik drži projekte i pričekaj odgovor; folder ne pogađaj. U njemu, do dvije razine dubine, nađi git repoe čiji `origin` vodi na
   `github.com` ili `bitbucket.org`, i iz adrese izvuci ime repoa te `owner` (GitHub) ili `workspace` (Bitbucket).
   Azure DevOps prepoznaješ po `dev.azure.com`, `*.visualstudio.com` ili `/_git/` u adresi (server u firmi):
   `https://<host>/<put>/<project>/_git/<repo>` daje `azureUrl = https://<host>/<put>` (organizacija ili kolekcija),
   `project` i ime repoa; SSH `git@ssh.dev.azure.com:v3/<org>/<project>/<repo>` daje `https://dev.azure.com/<org>`.
   Korisničko ime ispred `@` u adresi ne ide u `azureUrl`.
   Preskoči submodule (`.git` je fajl, ne folder), worktreeje i drugi klon istog repoa; ostaje klon na najvišoj razini.
3. Pokaži popis (repo, host, owner ili workspace, lokalni folder) i pitaj koje reviewa. Ništa ne upisuj bez tog izbora.
4. Za svaki izabrani repo:
   - `ticketRegex`: ključ tiketa koji se najčešće pojavljuje u zadnjih 200 commit poruka osnovne grane
     (`git log origin/<base> -200 --format=%s`), npr. `\bABC-\d+\b`; ako ga nema, prazno. Imena grana su lošiji izvor,
     jer stare grane često nose ključ koji se više ne koristi.
   - `ghAccount` (GitHub): ako je u `gh` prijavljeno više računa, onaj koji vidi repo
     (`GH_TOKEN=$(gh auth token --user <račun>) gh repo view <owner>/<repo>`); s jednim računom prazno.
5. Pitaj gdje se spremaju reviewi (`$ReviewsDir`); ako nema želje, ostaje kao u primjeru. Zapiši `config.local.ps1` u
   obliku `config.example.ps1`, sa zaglavljem iz njega, i pokaži korisniku što je upisano.
6. Za svaki Bitbucket workspace reci koje varijable trebaju (`BITBUCKET_<WORKSPACE>_EMAIL`, `_TOKEN`, a `_TOKEN_WRITE`
   samo za objavu komentara), koje dozvole token treba (README u folderu skilla) i kako ih korisnik sam upiše u svom
   terminalu: `[Environment]::SetEnvironmentVariable('<ime>', '<vrijednost>', 'User')`. Token nikad ne traži u chatu.
   Kad su varijable upisane, provjeri `GET /2.0/user`. Ako vrati 403, token nema `read:user:bitbucket`, pa skripta ne
   zna koji su komentari i approve korisnikovi: ili neka doda taj scope, ili u sudionicima zadnjih PR-ova tog workspacea
   nađi `account_id` čiji je `display_name` jednak korisnikovom `git config user.name`, pokaži ga i nakon potvrde upiši
   kao `bitbucketAccountId`.
7. Za svaki Azure DevOps repo pitaj u kojoj environment varijabli drži PAT za tu organizaciju ili server i upiši njeno
   ime kao `tokenVariable`. Ako je još nema, reci koji scope treba (README) i kako je sam upiše u svom terminalu, kao
   gore. Token nikad ne traži u chatu. Kad je upisana, provjeri `-List` za taj repo.
8. Pokreni `check-setup.ps1` iz korijena ai-config repoa (dva foldera iznad pravog foldera skilla) i pokaži što još fali.

## 0. Bez argumenta → izbor PR-a

```
pwsh -NoProfile -File "$HOME/.claude/skills/pr-review/scripts/pr-harvest.ps1" -List -Pretty
```
Ispiše otvorene PR-ove svih repoa iz configa, po repou.
- Ako je otvorenih PR-ova **≤ 4** → AskUserQuestion s opcijama `<repo> #N — <naslov>`.
- Ako ih je **> 4** → ispiši tablicu i pitaj koji.
- Više PR-ova odjednom radi **sekvencijalno**, jasno odvojeni izvještaji.

**Nikad ne nagađaj PR sam.**

## 1. Harvest (jedan poziv)
```
pwsh -NoProfile -File "$HOME/.claude/skills/pr-review/scripts/pr-harvest.ps1" -Repo <repo> -Pr <n> -ScratchDir "<scratchpad>"
```
Vraća JSON: `repo, host, pr, url, title, description, author, source, dest, state, headSha, approvals[], ci[], ticketKey,
comments[], fetchSpec, diffPath, diffLines, previousReview{…}, me, localPath, reviewsDir, notesPath`. Ako vrati `{error}`, reci
korisniku što piše i stani. `localPath` je lokalni klon, `reviewsDir` folder za sve spremljeno (kreiraj ga ako fali), a
`notesPath` bilješke za taj repo (`repos/<repo>.md`: kritičnost, pokretanje testova, prijetnje) ili `null`.

- **Fetchaj PR granu lokalno, bez checkouta** (glavni checkout ostaje na svojoj grani):
  `git -C <localPath> fetch origin <dest> <fetchSpec>`. **Ne** `gh pr checkout` ni `git checkout`, oni prebace granu glavnog
  checkouta. Perspektive čitaju preko `git show pr-<n>:<path>`, a build i mutacije idu u export ili worktree u scratchpadu
  (vidi `references/verify-gotchas.md`).
- **Komentari:** `comments[]` ima opće i inline komentare (inline s `path`, `line`, `id`, `replyTo`; na GitHubu `outdated`
  znači da je `line` iz starije verzije fajla, na Azure DevOpsu da se fajl mijenjao nakon komentara; tamo je `id` oblika
  `<nit>-<komentar>`); trebaju ih dedup (3),
  `nerijeseni-komentari` i `testovi`. Commit poruke: `git -C <localPath> log --format='%h %aI %B' origin/<dest>..pr-<n>`.
- **Re-review (nova runda):** harvest to već izračuna u `previousReview`: `at` (tvoja zadnja aktivnost), `baseSha` (head koji
  si reviewao; izvor `baseSource` = `notes` iz `objasnjenje.md` ili `github-review`), `headSha`,
  `deltaAvailable`/`deltaReason`, `deltaDiffPath` (+`deltaDiffLines`), `changedFiles`, `commitsSince` i `myCommentIds`
  (id-evi tvojih reviewa ili komentara). Na Bitbucketu i Azure DevOpsu head prošle runde postoji samo iz `objasnjenje.md`.
  Delta je sužena na fajlove koje PR stvarno mijenja prema ciljnoj grani, pa merge ciljne grane u PR nije šum.
- **⚠️ SNIMI harvest snapshot na disk:** cijeli JSON u `<reviewsDir>/<repo>-<pr>.harvest.json`. Iz njega čitaju dedup
  i iduća runda.

## 2. Fan-out — perspektive PARALELNO (Agent tool, `run_in_background`)
Za svaku perspektivu spawnaj **jedan subagent** (`general-purpose`) čiji je mandat **njezin lens fajl**. Proslijedi: lens path
+ `references/ton-komentara.md` + `references/verify-gotchas.md` (za verify) + `notesPath` ako nije `null` + harvestani
kontekst (repo, host, `localPath`, `reviewsDir`, `fetchSpec`, PR grana, naslov/opis, komentari, CI, diffPath) + upute da
**provjeri u lokalnom repou** i vrati nalaze u formatu svog lensa. `testovi` dodatno dobiva `references/kriticnost.md` (karta
K/S/N; nije lens i ne spawna se), commit poruke, prošli manifest `<reviewsDir>/<repo>-<pr>*.md` i head prošle runde ako
postoje. U novoj rundi `testovi` gleda deltu plus otvorene kritične nalaze iz prošle runde, i kad nisu u delti.

Perspektive (`lenses/`):
`bugs.md` · `arhitektura.md` · `testovi.md` · `sigurnost.md` · `perf.md` · `konvencije.md` · `ticket-fit.md` ·
`nerijeseni-komentari.md` · `dizajn.md`

- **Verify-capable** (bugs, testovi, sigurnost, perf): worktree ili `git archive` export PR grane, **pokreni** testove, spremi
  artefakt u scratchpad **prije** čišćenja. **bugs/sigurnost/perf:** dokaz je crveni test na PR kodu. **testovi:** ne puni rupe
  zelenim testovima; dokaz je da test pada na revertu fixa ili mutantu, i to u CI okolini, a novi test piše samo za kritičan
  rizik bez testa (TRAŽI), najviše 2 po PR-u. Build je spor pa teče paralelno.
- **ticket-fit**: ako je `ticketKey` prazan → odmah vrati "nema linkanog tiketa". Ako postoji → dohvati ga preko Jira
  connectora; ako connectora nema, vrati "tiket <key> postoji, ali nemam pristup trackeru".
- **nerijeseni-komentari**: proslijedi mu `comments[]` i commit poruke s vremenima; provjeri je li traženo stvarno u kodu.
- **dizajn** (❓): ne dokazuje ništa i ne builda; vraća kratka pitanja autoru. Pitanja nisu blocker (najviše med) i ne
  ulaze u presudu o approveu, osim ako ih korisnik sam tako označi.

**Runda (argument `delta` / `full`):**
- **`delta`** (ili bez argumenta kad je `previousReview.deltaAvailable` `true`) → svaka perspektiva dobiva `deltaDiffPath` +
  `changedFiles` + `commitsSince` umjesto punog diffa, plus **tvoje** objavljene komentare (iz `comments[]`, po autoru `me`
  iz harvesta) i odgovore na njih. Puni diff ostaje samo za kontekst. `nerijeseni-komentari` je u delti obavezan.
- **`full`** → cijeli PR iznova, i kad postoji prethodna runda.
- `deltaAvailable=false` → reci zašto (`deltaReason`) u jednoj rečenici i radi full.
- U izvještaju na vrhu napiši od kojeg do kojeg heada je delta (`baseSha → headSha`, izvor) i koliko commitova autora je u njoj.

**Depth (argument):**
- default → svih 9 perspektiva.
- `quick` → samo `bugs` + `arhitektura` + `testovi`, **bez builda i bez pokretanja testova**. Svaki od tih lensova ima pravila za
  quick mod u svom fajlu.
- `only <lens,...>` → samo navedene (npr. `/pr-review 42 only bugs,sigurnost`).

## 3. Merge — dedup, rangiraj, kompozicija
Kad se svi subagenti vrate:
- **⚠️ DEDUP PROTIV POSTOJEĆIH KOMENTARA (obavezno, prvo).** Za svaki nalaz provjeri komentare iz snapshota: postoji li već
  komentar na toj `path:line` (ili nit na istu temu za općenite)? **Ako da i kod se od tog komentara nije mijenjao → IZBACI
  nalaz.** Ne preoblikuj ga u "nadovezujem se". Nalaz zadržavaš SAMO ako (a) nitko ga nije spomenuo, ILI (b) imaš materijalno
  novi doprinos (dokazani test, konkretan fix) i tada ide kao **odgovor u toj niti** (tip `reply`, vidi korak 4). Kad nešto izbaciš, u izvještaju navedi
  "(preskočeno — već komentirano: <autor>)". (`pr-post.ps1` ima backup-guard za inline duplikate, ali primarno čišćenje je ovdje.)
- **Dedup** između perspektiva: isti nalaz iz dvije perspektive spoji u jednu stavku, navedi oba kuta.
- **🧪 nalazi se ne raspisuju po testu.** Trijaža test-lensa ide korisniku u izvještaj, a njezin PR-level sažetak na PR kao
  **jedan** općeniti komentar. Inline idu samo 🧪 med/high s dokazom (najviše ~5 po PR-u) i low koji odgovara na postojeće
  pitanje u niti. 🧪 bez izvršenog dokaza ne ide iznad low, osim rupe bez testa u `quick` modu (najviše med, vidi `lenses/testovi.md`); 🧪 na kodu nivoa N nikad iznad low i ne blokira approve. 🧪 skica
  koja je pala na PR kodu je 🐛. U cijelom manifestu najviše 2 nova testa iz 🧪 (confirming testovi iz 🐛 se ne broje).
- **Rangiraj po severity** (high → med → low), unutar iste razine po perspektivi. Označi stavku emojijem kuta (🐛🏛🧪🔒⚡📐🎯💬❓).
- **Verify status** vidljiv: 🐛 `✅ dokazano crvenim testom`, 🧪 linija dokaza (`PR kod ✅ | revert/mutant ❌ ili ✅ | CI okolina …`),
  sa stvarnim outputom, ili `⚠️ nije verificirano — razlog`. Zelen test sam po sebi nije dokaz.
- **Presuda** na vrhu: mergeati / ne + zašto (blokeri: high bug, otvoreni threadovi, CI, ne-approve).

## 4. Draft komentari (gated — NIŠTA se ne objavljuje automatski)
Za nalaze vrijedne komentara složi **gotove komentare** po `references/ton-komentara.md`: `file:line` (inline) ili general,
tekst kao prijedlog/pitanje, i **cijeli test unutar komentara** kad ga bug nalaz ili 🧪 TRAŽI ima. 🧪 komentar nosi **najviše
jedan** kratak test; POPRAVI/SPOJI/MAKNI nosi samo promijenjene linije ili nijedan kod, a PITAJ ne nosi kod testa. Numeriraj ih.

**SPREMI ih u uređiv manifest** `<reviewsDir>/<repo>-<pr>.md`, u formatu koji `pr-post.ps1` čita:
```
<!-- pr-review <repo>#<pr> -->

## PR-COMMENT 1 | inline | <path> | <line> | posted=no
<tekst komentara, može više linija, code-blokovi ok>

## PR-COMMENT 2 | general | - | - | posted=no
<tekst>

## PR-COMMENT 3 | reply | <id komentara> | - | posted=no
<tekst>
```

- **`inline`:** linija mora biti u diffu (`+` ili kontekst). Ako je stvarni problem izvan diffa, uzmi najbližu liniju diffa koja ga
  pokreće, a pravu lokaciju napiši u tekst. Ako takve nema, ide `general`.
- **`reply`:** id je iz `comments[]` u snapshotu. Na GitHubu samo za inline nit, i to id prvog komentara niti (`replyTo` ako
  postoji, inače `id`). Na Bitbucketu i Azure DevOpsu može na bilo koji komentar.
- Oznake (`severity`, `⚠️`) ostaju u izvještaju. U tekst komentara ide obična rečenica, npr. "nisam provjerio izvođenjem".

Akcije koje ponudiš: **`/pr-review objavi <repo> <n> [brojevi]`**, `uredi N` (korisnik doradi manifest rukom), `preskoči`.

## Output — uvijek ovim redom
1. **TLDR, 4 pitanja:**
   1. Je li autor riješio već objavljene review komentare? Ako nije, koje nije.
   2. Ima li novih stvari za komentirati?
   3. Može li se mergeati?
   4. Može li se dati approve? Ako ne, što točno mora biti riješeno.
2. **Tablica**, jedan red po nalazu: `#` · nalaz u par riječi · kritično · blokira approve · objavljeno · riješeno.
3. **Što PR radi**, 2–4 rečenice bez žargona.
4. **Po nalazu blok**, uvijek istim redom:
   - **Kritično:** da / srednje / ne (za 🧪: nivo K/S/N + dokaz u jednoj rečenici)
   - **Blokira approve:** da / ne (+ zašto)
   - **Riješeno:** da / ne
   - **Korak po korak:** konkretan primjer, što program napravi i gdje nastaje greška.
   - **Ukratko:** jedna rečenica.
   - **Fix:** jedna-dvije rečenice običnim riječima.
   - **Pun tekst komentara** kakav ide na PR. Test blokove smiješ zamijeniti s "+ test `<Ime>` (u manifestu)".
5. Akcije.

Isti sadržaj spremi u `<reviewsDir>/<repo>-<pr>.objasnjenje.md`. Na vrh napiši `Reviewano @ <head-sha>`, da iduća runda zna od
čega računa deltu.

Nalaze spremi i strojno u `<reviewsDir>/<repo>-<pr>.findings.json`, s punim head sha koji je reviewan, u formatu iz
`../pr-walkthrough/SKILL.md` (sekcija "Review findings format"), da ih `/pr-walkthrough` pokaže uz kod.

**Nakon izvještaja uvijek pokaži kako komentari izgledaju:** pun draft svakog komentara, s lokacijom (`file:line` u NOVOM fajlu,
"općenit" ili "odgovor u niti"), pa vizualni preview po `references/vizualni-preview.md`.

## Objava — `/pr-review objavi [<repo>] <n> [brojevi]`
Objava komentara je javna radnja u korisnikovo ime → **uvijek preview + jedno izričito "da". Nikad automatski.**
1. **Preview** (dry-run, ništa se ne šalje), prikaži izlaz doslovno:
   ```
   pwsh -NoProfile -File "$HOME/.claude/skills/pr-review/scripts/pr-post.ps1" -Repo <repo> -Pr <n> [-Only "1,3"]
   ```
2. **Potvrda:** pitaj "Objavljujem ovih N na `<repo>#<n>`? (da / ne / brojevi)". Bez izričitog "da" — STOP.
3. **Objava:** isti poziv s `-Post`. Skripta ispiše ✅/❌ po komentaru i osvježi manifest (`posted=<id>`), pa ponovni poziv ne
   duplira. Inline duplikat postojećeg komentara se preskače osim uz `-Force`. `reply` ide u postojeću nit i nije duplikat.
   Na GitHubu inline linija koja nije u diffu ide kao općeniti komentar s prefiksom `re: <path>:<line>`.

Nikad ne dodavaj `-Post` sam. Ne mijenjaj ništa u trackeru (Jira i slično).

## Pravila
- Ako nalaz ovisi o nečemu što se može pročitati u repou, pročitaj kod i potvrdi sam. Komentar smije biti pitanje samo za
  stvari kojih nema u kodu (namjera, deploy konfig izvan repoa).
- **⚠️ BROJ LINIJE ZA INLINE = linija u NOVOM fajlu, NE redak iz Read-a diff-fajla.** Diff ima header-linije prije sadržaja.
  Izračunaj pravu liniju iz hunk headera: `@@ -a,b +c,d @@`, nova strana kreće na `c`, pa broji SAMO ` ` i `+` linije. Provjeri
  par anchora prije objave.
- **Read-only prema PR-u** dok korisnik ne kaže `objavi`.
- Reci korisniku da par perspektiva gradi u worktreeju; `quick` to preskače.
- Svaka perspektiva ostaje u svom pojasu; merge rješava preklapanje.
