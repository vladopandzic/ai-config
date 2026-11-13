# shop-api

Primjer bilješki za jedan repo. Pravi fajl je `repos\<repo>.md` (git ga ignorira) i čitaju ga lensovi `testovi`, `sigurnost`, `bugs` i `perf`. Sve tri sekcije su neobavezne; što fali, lens radi po općim pravilima.

## Kritičnost

Kritičan tok: `OrderController` → `CheckoutService` → `PaymentGateway.ChargeAsync` → vanjski servis za plaćanje.

| Nivo | Područje | Putanje | Test koji ima smisla |
|---|---|---|---|
| K | Naplata | `src/Shop.Api/Payments/**` | mock gatewaya: točan iznos i valuta koji odlaze u naplatu; greška gatewaya ne označi narudžbu plaćenom |
| K | Autorizacija | `src/Shop.Api/Auth/**`, `[Authorize]` na kontrolerima | korisnik drugog tenanta dobije 404 |
| K | Migracije | `src/Shop.Infrastructure/Migrations/*.cs` (ne `*.Designer.cs`) | seed starog oblika → migriraj → provjeri |
| S | Izvještaji | `src/Shop.Api/Reports/**` | ručno izračunat primjer za jedan dan |
| N | Izgled | `**/*.css`, `wwwroot/**` | ne tražiti |

## Pokretanje testova

- Solucija `Shop.sln`, test projekti `tests/*.Tests`. NUnit, NSubstitute, FluentAssertions.
- CI: `.github/workflows/ci.yml`, `ubuntu-latest` (UTC, invariant kultura), `dotnet test -c Release`.
- Integracijski testovi trebaju Docker (Testcontainers, `postgres:16-alpine`).
- Lokalna zona i kultura za provjeru razlike prema CI-u: `-e TZ=Europe/Berlin -e LANG=de_DE.UTF-8`.

## Prijetnje

- Napadač je ulogiran korisnik jednog tenanta koji pokušava čitati ili mijenjati narudžbe drugog tenanta.
- Naplata i povrat novca su operacije s vanjskim učinkom; neovlašteno pokretanje je ozbiljno.
