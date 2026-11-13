# Verify-mode gotchas — pokretanje testova

Bug-, test-, sigurnost- i perf-lens u verify modu neka OVO pretpostave umjesto da otkrivaju iznova. Ako harvest vrati
`notesPath`, pročitaj i njegov dio *Pokretanje testova* (solucija, test projekti, SDK, CI, Docker): on ima prednost.

## Repo i grana
- **Glavni checkout (`localPath`) se ne dira:** ne checkoutaj grane i ne mijenjaj working tree. PR ref: `git -C <localPath> fetch origin <baza> <fetchSpec>` (`fetchSpec` i baza = `dest` iz harvesta); čitanje `git show pr-<n>:<path>`.
- **Diff:** prema bazi `git diff origin/<baza>...pr-<n>` (lokalna baza može zaostajati pa uvući druge PR-ove). Između rundi `git diff <stari-head> <novi-head>`: nakon force-pusha `git log stari..novi` vuče i commitove s baze. Stari head mora postojati lokalno; ako ga nema, probaj `git fetch origin <puni-sha>`.
- **Radni dir:** `git -C <localPath> archive <sha> | tar -x -C <scratchpad>/<ime>` (samo ako repo nema submodula; folder obriši na kraju) ili `git worktree add <scratchpad>/<ime> <ref>` pa obavezno `git worktree remove --force`.
- **Sporo:** gađaj samo relevantni test-projekt, nikad cijelu soluciju.

## Build (.NET)
- SDK: pogledaj `global.json`, `TargetFramework` test projekata i verziju u CI konfiguraciji. Ako build javi grešku jezika (npr. `CS0854`), probaj noviji SDK (`dotnet --list-sdks`).
- Build u zaseban folder: `dotnet build <Proj> -c Release -o <dir>/out-<x>`. Projekt koji referencira web projekt s static web assetima obično treba i `-p:StaticWebAssetsEnabled=false`.
- Ako CI builda s `--warnaserror` (ili `Directory.Build.props` ima `EnforceCodeStyleInBuild`), kad tvrdiš da novi test prolazi CI, dodaj `-warnaserror`; noviji SDK može javiti koje upozorenje više od CI-a, to provjeri prije nego ga pripišeš testu.
- `dotnet test <dll> --list-tests` potvrdi da je test otkriven.

## CI paritet (zona i kultura)
CI (`ubuntu-latest`) i Linux kontejneri su obično UTC + invariant kultura, a dev mašina često nije. .NET na Windowsu ignorira `TZ`, a sistemsku zonu i kulturu **nikad ne mijenjaj**. Gotov DLL vrti u kontejneru SDK-a iste verzije (ima runtime i ICU):
```
# PowerShell, iz <dir>
docker run --rm -v "${PWD}:/w" mcr.microsoft.com/dotnet/sdk:<verzija> dotnet test /w/out-<x>/<Proj>.dll --filter "FullyQualifiedName~<Klasa>"
```
Bez `-e` kontejner je `Etc/UTC` + invariant (`12.5`), kao CI. Lokalnu okolinu dobiješ s `-e TZ=<zona> -e LANG=<locale>.UTF-8` (vrijednosti iz bilješki repoa, ili one korisnikove mašine).

Testcontainers i `WebApplicationFactory` testovi vrte se s hosta (Docker mora raditi), ne iz kontejnera. Prvi run je spor. Ako Docker ne radi, testovi padnu u fixtureu — to nije nalaz.

## Mutacijska provjera
- **Revert = semantika koda prije fixa**, doslovno iz `git show <commit-prije-fixa>:<path>`, ne najbliži mutant koji se kompajlira. Ako fix usput restrukturira kod, prvo pročitaj stari commit pa tek onda biraj mutant.
- **Vrati ponašanje, ne API.** Stari fajl u cijelosti se često ne kompajlira jer fix uvodi helper koji koristi i drugi kod. Vrati samo uvjete koji mijenjaju ponašanje.
- **Jedan mutant po buildu**, zaseban `-o out-mut-<n>`. Original vraćaj s `git -C <repo> show <ref>:<path> > <path>`. `mv`, `cp -p` i PowerShell `Copy-Item` zadrže stari mtime, pa MSBuild preskoči kompilaciju i testiraš stari mutant: nakon njih `touch <path>`, ili `dotnet build --no-incremental` pa `dotnet test --no-build`.
- Po mutantu zapiši liniju, izmjenu i koliko je testova palo; spremi mutant kao diff (`git diff --no-index <orig> <mut>`) i doslovne `Passed!/Failed!` linije **prije** brisanja exporta.
- Redoslijed iz baze ili timing: 3 pokretanja; jedan zeleni prolaz ništa ne dokazuje.

## Alat koji repo nema
Ako za dokaz buga treba test-alat kojeg repo nema (npr. bUnit za render bug), smije se dodati **samo u worktree** i samo za dokaz (`lenses/bugs.md`), i to se OBAVEZNO prijavi korisniku. Test-lens novi alat ne predlaže: logika se iz komponente izvlači u običnu klasu i testira ona.

## Higijena
- **Spremi test + fix diff na trajnu putanju PRIJE `worktree remove`** (vidi `lenses/bugs.md`, verify korak 7), inače se briše s worktreejem.
- Nakon dokaza vrati izmjene i `git worktree remove <path> --force`. Provjeri da glavni repo ostaje čist (pred-postojeće izmjene u working treeju nisu tvoje, ne diraj ih).
