<#
  Kopiraj ovaj fajl u config.local.ps1 (git ga ignorira) i upiši repoe koje reviewaš.
  pr-harvest.ps1 i pr-post.ps1 čitaju samo config.local.ps1.

  Jedan red po repou; ključ je ime repoa kako piše na GitHubu ili Bitbucketu.
    host        'github' ili 'bitbucket'
    owner       GitHub korisnik ili organizacija (samo github)
    workspace   Bitbucket workspace (samo bitbucket)
    ghAccount   gh račun koji vidi repo; prazno = aktivni gh račun (samo github)
    localPath   lokalni klon repoa (obavezno za review)
    ticketRegex ključ tiketa u grani ili naslovu; prazno = bilo koji ključ u Jira obliku (ABC-123)
    bitbucketAccountId  tvoj Bitbucket account id; treba samo ako read token nema scope read:user:bitbucket,
                        inače skripta ne zna koji su komentari i approve tvoji (samo bitbucket)

  Bilješke koje vrijede samo za jedan repo (što je kritično, kako se vrte testovi, tko bi ga mogao napasti)
  idu u repos\<repo>.md pokraj ovog fajla, u obliku repo-notes.example.md. Git ignorira taj folder.
#>

$ReviewRepos = @{
  'shop-api' = @{ host = 'github'; owner = 'example-org'; ghAccount = ''; localPath = 'C:\code\shop-api'; ticketRegex = '\bSHOP-\d+\b' }
  'billing'  = @{ host = 'bitbucket'; workspace = 'example-workspace'; localPath = 'C:\code\billing'; ticketRegex = '' }
}

$ReviewsDir = Join-Path $HOME 'pr-review'
