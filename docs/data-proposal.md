# Data proposal — Firme din București

**Echipa:** Firme Bucuresti

## 1. De ce acest dataset?

Construim un set tabelar cu **toate firmele înregistrate în municipiul București** (~445.800 de CUI-uri colectate până acum), îmbogățit cu date publice despre fiecare firmă: stare (activă / radiată), plătitor de TVA, adresă normalizată (sector, stradă), formă juridică, an de înființare, cod CAEN și, sediul actual, indicatori din bilanț (cifră de afaceri, nr. angajați).

**Scopul modelului:** setul este construit pentru a antrena un model care estimează în cât timp o firmă va da faliment.

**Cum definim „faliment":** nu orice radiere înseamnă faliment (multe sunt dizolvări voluntare). De aceea păstrăm **trei evenimente distincte**: `insolventa` (deschiderea procedurii), `radiere_faliment` (radiere în urma insolvenței) și `radiere_alta` (voluntară, fuziune etc.). Ținta principală este `insolventa`/`radiere_faliment`; `radiere_alta` este tratată ca risc concurent.

**Cine l-ar folosi:** cercetători și jurnaliști (studii despre economia Capitalei, firme-fantomă, concentrare pe sectoare), analiști de piață (hărți de densitate pe domenii CAEN), studenți (exerciții de curățare, deduplicare, geocodare), precum și cei care antrenează modele pentru potrivire de entități sau clasificare CAEN din denumire.

**Ce există deja și de ce nu ajunge:**

- _data.gov.ro / ONRC_ publică liste de firme, dar nestandardizate, fără istoric de stare, fără filtrare pe localitate gata făcută și cu adrese în text liber.
- _ANAF_ oferă date doar prin interogare per CUI, nu ca set descărcabil.
- _totalfirme.ro, listafirme.ro_ etc. au date utile, dar sunt comerciale, fără licență de reutilizare și fără export.

Contribuția noastră: un set curat, deduplicat, cu schemă fixă și proveniență clară, limitat la București, care combină mai multe surse sub o singură cheie (CUI) și normalizează adresele și codurile CAEN. Un set nou e necesar pentru că niciuna dintre sursele existente nu oferă această combinație într-un format reutilizabil fără contra cost .

## 2. Surse

| Sursă                                                                                                     | Ce furnizează                                                       | Licență / condiții                                                                                                                                                                               | Dimensiune aprox.                               |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| totalfirme.ro, listă pe județ (`/judet-BUCUREȘTI`) — **deja extras** cu `src/scrape_totalfirme/scarep.py` | doar lista de CUI-uri                                               | Site comercial; fără licență explicită. Folosim **doar CUI-ul** (identificator public) pentru a construi lista, nu conținutul site-ului. Termenii de utilizare se verifică înainte de publicare. | 445.800 rânduri, ~4,4 MB                        |
| ANAF — API public „Platitor TVA” (`webservicesp.anaf.ro`)                                                 | denumire, adresă, stare, TVA, CAEN, formă juridică, dată înființare | Date publice ale statului, furnizate pentru uz public (Legea 544/2001 și OUG 41/2016 privind datele deschise). Cereri în loturi de max. 100 CUI, cu limită de rată.                              | ~445.800 înregistrări, ~150–250 MB JSON brut    |
| ANAF — API bilanț (`webservicesp.anaf.ro/bilant`)                                                         | cifră de afaceri, profit, nr. angajați per an                       | Idem                                                                                                                                                                                             | un an per cerere; probabil doar ultimii 1–3 ani |
| data.gov.ro — seturile ONRC de firme (completare / verificare încrucișată)                                | data înmatriculării, stare                                          | Open Government Licence 1.0 România                                                                                                                                                              | zeci de MB                                      |
| BPI — Buletinul Procedurilor de Insolvență (`bpi.ro`) / portal.just.ro (de verificat)                     | data deschiderii insolvenței, tip procedură (etichete pentru țintă) | De verificat: accesul la BPI este parțial plătit; alternativ, data radierii + starea din ANAF ca proxy. Dacă nu există licență clară, folosim doar ANAF/ONRC.                                    | zeci de mii de dosare, la nivel național        |

## 3. Date sensibile

- **Persoane juridice (SRL, SA etc.):** denumirea, adresa sediului și CUI-ul sunt date publice de registru, nu date personale.
- **Persoane fizice autorizate (PFA, II, IF):** denumirea conține adesea numele unei persoane, iar adresa poate fi domiciliul. Acestea sunt date personale.
  - Detectăm forma juridică; pentru PFA/II/IF **eliminăm denumirea și păstrăm doar CUI-ul, sectorul și codul CAEN** (adresa se reduce la sector).
  - Nu colectăm CNP, telefon, e-mail, asociați sau administratori.
- **Date brute:** răspunsurile JSON ANAF
- Colectarea se face la ritm redus, cu respectarea limitelor de rată ale sursei.

## 4. Schema

Un rând = o firmă, cheie primară `cui`.

```json
{
  "cui": "int, 6–10 cifre, unic",
  "denumire": "str | null  (null pentru PFA/II/IF)",
  "forma_juridica": "enum: SRL | SA | SNC | SCS | PFA | II | IF | ONG | altele",
  "stare": "enum: activa | inactiva | radiata | suspendata",
  "an_infiintare": "int | null",
  "platitor_tva": "bool",
  "cod_caen": "str, 4 cifre | null",
  "domeniu_caen": "str  (secțiunea CAEN, A–U, derivată)",
  "sector": "int 1–6",
  "strada": "str | null  (normalizată; null pentru PFA/II/IF)",
  "cifra_afaceri": "float RON | null  (ultimul an disponibil)",
  "nr_angajati": "int | null",
  "an_bilant": "int | null",
  "data_infiintare": "date | null",
  "data_eveniment": "date | null  (insolvență / radiere; null = cenzurat)",
  "tip_eveniment": "enum: insolventa | radiere_faliment | radiere_alta | niciunul",
  "durata_zile": "int  (data_eveniment sau data_colectare minus data_infiintare)",
  "event": "bool  (true dacă a avut loc evenimentul țintă)"
}
```

Cifra de afaceri și angajații se păstrează pe an (tabel lung `cui, an, cifra_afaceri, nr_angajati, profit`), pentru ca modelul să vadă traiectoria firmei, nu doar ultimul an. Trăsăturile se calculează doar din datele anterioare datei de predicție.

**Exemple** (valori ilustrative, nu date reale; câmpurile vor fi completate din ANAF în etapa următoare):

```json
{"cui": 11111111, "denumire": "EXEMPLU CONSULTING SRL", "forma_juridica": "SRL", "stare": "activa", "an_infiintare": 2016, "platitor_tva": true, "cod_caen": "6201", "domeniu_caen": "J", "sector": 3, "strada": "Calea Dudesti", "cifra_afaceri": 1250000.0, "nr_angajati": 8, "an_bilant": 2024}
{"cui": 22222222, "denumire": "EXEMPLU TRANSPORT SA", "forma_juridica": "SA", "stare": "radiata", "an_infiintare": 1994, "platitor_tva": false, "cod_caen": "4941", "domeniu_caen": "H", "sector": 1, "strada": "Soseaua Chitilei", "cifra_afaceri": null, "nr_angajati": null, "an_bilant": null}
{"cui": 33333333, "denumire": null, "forma_juridica": "PFA", "stare": "activa", "an_infiintare": 2021, "platitor_tva": false, "cod_caen": "7420", "domeniu_caen": "M", "sector": 5, "strada": null, "cifra_afaceri": null, "nr_angajati": null, "an_bilant": null}
```

## 5. Cum arătăm că setul e util

Antrenăm un model de supraviețuire (Cox, apoi gradient boosting survival) și îl comparăm cu o linie de bază care folosește doar vârsta, forma juridică și domeniul CAEN. Utilitatea se măsoară pe un set de test împărțit în timp (antrenare pe firme/ani vechi, test pe ani recenți) cu C-index și AUC la 1, 2 și 3 ani. Dacă trăsăturile financiare și cele din setul curățat îmbunătățesc aceste metrici, setul e util.

**Riscuri cunoscute:** (1) lista de CUI din totalfirme poate conține puține firme demult radiate, deci setul poate fi părtinit spre supraviețuitori; verificăm câte sunt radiate și completăm din ONRC; (2) bilanțurile lipsesc la firmele foarte mici sau cele care nu le depun; (3) evenimentele de faliment sunt rare, deci raportăm și metrici adaptate dezechilibrului (PR-AUC).
