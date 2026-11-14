# Ton komentara na PR

Pravila za korak koji nalaz pretvara u komentar. Agent ih slijedi i ne mijenja. Korisnik ih prije prvog reviewa može prilagoditi svom stilu.

Korisnik svaki komentar odobri ili uredi. Ovaj fajl određuje samo **kako se formulira**, ne smije li se poslati.

## Osnovno
- **Hrvatski.** Kod-identifikatori ostaju engleski, proza je hrvatska.
- **Prijedlog ili pitanje, ne naredba:** *"bi li bilo bolje…"*, *"ima li smisla…"*, *"možda…"*.
- **Iskreno o nesigurnosti:** *"nisam provjerio izvođenjem, ali analiza upućuje na bug"*.
- **Direktno na stvar**, bez općenitih savjeta.

## Dužina
- **Sitnica ili pitanje:** jedan red.
- **Pravi bug:** puna analiza, po redu ispod.

## Komentar za pravi bug
1. **Otvarač** s razinom sigurnosti: *"Ovo će potencijalno baciti NullReferenceException"*.
2. **Mehanizam:** zašto se događa, precizno.
3. **Kako reproducirati:** realan scenario.
4. **Točan simptom:** doslovni tekst iznimke kad ga znaš.
5. **Fix + test:** kratki fix i test koji dokazuje bug.

Primjer:
> Nisam provjerio izvođenjem, ali `FindAsync` vraća `null` kad zapis ne postoji, a ova linija rezultat koristi bez provjere,
> pa pukne s `NullReferenceException`. Kako reproducirati: pozovi akciju s nepostojećim id-em. Test: `…`

## Test u komentaru
- Bug ide s testom, **cijelim u tijelu komentara**, kad repo ima harness za taj kod. Ako ga nema, reci to i napiši kako ručno provjeriti.
- Test koji nije pokrenut označi kao skicu.
- Kad testa još nema u repou, reci to i napiši u koji test-projekt ide.
- **Najviše jedan kratak test** po komentaru, onaj koji pada kad se fix vrati ili se ključna linija pokvari.
- O testovima se govori kroz ponašanje i dokaz: *"s vraćenim starim uvjetom test i dalje prolazi"*.

## Nalaz s posljedicom, bez buga
Kratak odlomak: što je problem, što košta i prijedlog. Bez koraka za reprodukciju i bez testa.

## Odgovor u postojećoj niti
Piši u svoje ime i dodaj samo ono što nit još nema. Ne odgovaraj u ime autora.

## Komentar mora stajati sam
- **Objasni pojmove.** Ne samo "treba biti idempotentno", nego "dva ista poziva moraju dati isti rezultat". Imena klasa ostaju kakva jesu.
- Veži se na točan `file:line` i konkretan slučaj.
- Ne tvrdi ono što nisi provjerio.

## Primjeri: predloženo → kako bih ja napisao
Parovi koje je korisnik ispravio. Piši kao desna strana.

- Zahtjev postaje opušteno pitanje:
  > ~~Molim kratak komentar s primjerom vrijednosti ovdje, da je ugovor s vanjskim servisom vidljiv u modelu.~~
  > Jel ok nadodat komentar s primjerom vrijednosti ovdje, da je ugovor s vanjskim servisom vidljiv u modelu?
