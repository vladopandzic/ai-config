# Vizualni preview draft komentara

Cilj: vidjeti komentare kao da su već na GitHubu ili Bitbucketu, inline u diffu, a ne tekst iz skripte. Ništa se ne šalje.

## Ulaz
- Manifest `<reviewsDir>/<repo>-<pr>.md` (blokovi `## PR-COMMENT n | inline|general|reply | path ili id niti | line | posted=…`). Opcijski filter brojeva.
- Snapshot `<reviewsDir>/<repo>-<pr>.harvest.json` → `source` (PR grana) i `diffPath`.

## Kod oko komentara — uvijek s PR grane, NIKAD iz working treea
Glavni checkout je na tvojoj grani, pa `pr-post.ps1` dry-run bez fetchane grane zna pokazati krive linije. Za svaki inline komentar:
- `git -C <localPath> show pr-<n>:<path>`. Ako ref fali, prvo `git fetch` (bez checkouta).
- Uzmi ~3 linije iznad i ~2 ispod ciljane linije. Linije koje PR dodaje (iz diffa, `+`) označi zelenom pozadinom. Duge linije skrati s `...`.
- Više komentara u istom fajlu ide u isti blok fajla, svaki ispod svoje linije, redom po liniji.

## Render
`mcp__visualize__show_widget` (prije prvog poziva u sessionu tiho `mcp__visualize__read_me` s `["mockup"]`). Oblik:
- Po fajlu kartica: zaglavlje s putanjom (mono, 12px), linije koda s brojem linije (mono 12px, `white-space: pre`, `overflow:hidden`), pa kartica komentara uvučena ispod ciljane linije.
- Kartica komentara: `#n · linija L` (muted), oznaka `draft` (warning tint) ili `objavljeno` kad `posted` nije `no`. Tijelo je **renderiran Markdown**: ``` blok → `<pre>`, inline code → `<code>`, odlomci → `<p>`. Tekst doslovno iz manifesta, ništa ne preformuliraj.
- Općeniti komentari: na kraju zasebna kartica "Rasprava na PR-u (općenit komentar)".
- Odgovori u niti: uz liniju početnog komentara, s kratkim citatom tog komentara iznad odgovora.
- Samo CSS varijable (dark mode), bez naslova i proze u widgetu, `title` npr. `<repo>_<pr>_draft_comments_preview`.

## Poslije widgeta (tekst)
Najviše 2-3 kratke rečenice: koliko komentara i gdje sjedaju, napomena ako nešto nije očito, i akcija `/pr-review objavi <repo> <pr> [brojevi]`. Ne ponavljaj tekst komentara.

## Fallback
Ako `show_widget` nije dostupan (terminal, cloud): dry-run `pr-post.ps1` i stdout kao Markdown, uz napomenu da je kontekst koda iz working treea možda kriv.
