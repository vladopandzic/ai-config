# Karta kritičnosti (za `lenses/testovi.md`)

Nije lens (orkestrator ga ne spawna), nego referenca test-lensu za korak 1 (K/S/N).

**Kako koristiti**
1. Ako harvest vrati `notesPath`, pročitaj njegov dio *Kritičnost*: tamo je karta za taj repo (kritičan tok, putanje po nivou,
   koji test ima smisla, okolina CI-a). Ona ima prednost pred općim pravilima ispod.
2. Promijenjeni fajl smjesti u red po **ponašanju** koje mijenja, ne po ekstenziji ni imenu projekta. Najspecifičniji red
   pobjeđuje; ako pada u više redova, uzmi viši nivo. UI komponenta koja računa ili sprema ulaz u K tok penje se, handler koji
   samo prosljeđuje spušta se.
3. **K**: promjena ili fix bez testa koji *pada kad se ponašanje pokvari* je nalaz, a test mora štititi u okolini CI-a i
   produkcije. **S**: test samo za netrivijalnu logiku (grananje, izračun, datumi, upit s rubom), inače je dovoljno
   "ručno provjereno: …" u opisu PR-a; nalaz najviše med. **N**: test se ne traži; testovi koje PR tu doda kandidati su za
   MAKNI/SPOJI (low).
4. Repo nema bilješke ili područje nije u njima → *Opća pravila* ispod. Odluku napiši u jednoj rečenici da je reviewer može
   osporiti.

## Opća pravila
1. Što je najgore ako ovo tiho pogriješi: fizička akcija ili sigurnost ljudi > novac > pristup > trajni podaci (migracije, sync, brisanje) > prikaz na kojem netko odlučuje > kozmetika.
2. Znakovi za K: piše prema uređaju ili vanjskom sustavu; računa novac, energiju ili jedinice; odlučuje o dozvoli; mijenja shemu ili podatke; radi s TZ/DST/granicom dana; parsira vanjski format; dira autorizaciju ili tokene; generator koda i njegov ulaz (generirani izlaz nije K).
3. Znakovi za N: samo izgled; dev, design-time, mock, primjer (provjeri DI: registrira se samo iza dev
   prekidača); generirani kod; docs, tooling.
4. Sve između je S. Penji ako je kod jedini čuvar ulaza u K tok, izvor podatka koji K tok čita (cache konfiguracije,
   mapiranje id-eva), ili je od njega do ruba (DB write, HTTP write, uređaj) najviše 2–3 koraka bez ljudske provjere.
   Spuštaj ako je čisti passthrough.
5. Ime projekta ne odlučuje: slijedi pozive do ruba.
6. Okolina je dio ocjene: CI (OS, TZ, kultura, Docker/DB, `[Ignore]`/`[Explicit]`, je li projekt u onome što CI vrti) i
   produkcija.

Kad za repo nema bilješki, a karta bi pomogla iduće put, na kraju trijaže predloži korisniku par redaka za
`repos/<repo>.md` (u obliku `repo-notes.example.md`). Ne piši ih sam.
