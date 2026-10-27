# Data proposal — Firme din București

**Echipa:** Firme Bucuresti

## 1. De ce acest dataset?

Construim un set tabelar cu firmele din municipiul București (~445.800 de CUI-uri colectate până acum), îmbogățit cu date publice ANAF despre fiecare firmă și, separat, cu indicatori de bilanț pe an. Setul este construit în jurul unei chei comune: `cui`.

Datele generale includ denumirea, starea de înregistrare ANAF, forma juridică, codul CAEN, adresa sediului social și informațiile TVA. Datele de bilanț sunt salvate câte un rând pentru fiecare combinație CUI-an, cu indicatorii financiari în coloane separate.

**Scopul principal al modelului:** predicția evoluției financiare a unei firme într-un an ulterior, folosind datele generale și unul sau mai mulți ani de bilanț anteriori. Exemple de ținte:

- predicția valorii unui indicator financiar în anul următor, de exemplu cifra de afaceri, veniturile totale, cheltuielile totale, profitul net sau pierderea netă;
- predicția variației unui indicator: creștere, stagnare sau scădere;
- predicția disponibilității bilanțului într-un an ulterior, cu atenție la faptul că lipsa unui bilanț poate însemna lipsă de depunere, lipsă în API sau inactivitate, nu neapărat un eveniment economic;
- predicția unei categorii de performanță, de exemplu „câștig bun”, „câștig slab”, „pierdere” sau „date insuficiente”, definită prin reguli explicite aplicate indicatorilor disponibili.

**Propunere secundară, opțională:** clasificarea riscului de insolvență sau predicția deschiderii unei proceduri de insolvență. Aceasta nu poate fi antrenată corect doar din câmpurile actuale, deoarece `firme.csv` nu conține un eveniment de insolvență confirmat. Pentru această variantă ar fi necesare etichete istorice din BPI, ONRC sau o altă sursă verificabilă. Radierea și starea ANAF nu trebuie tratate automat ca insolvență.

**Cine l-ar folosi:** cercetători și jurnaliști (studii despre economia Capitalei și dinamica firmelor), analiști de piață (comparații pe CAEN și sectoare, după ce aceste câmpuri sunt derivate), studenți (curățare, deduplicare și analiză longitudinală) și cei care antrenează modele de regresie, clasificare sau serii temporale.

**Ce există deja și de ce nu ajunge:**

- _data.gov.ro / ONRC_ publică liste de firme, dar nestandardizate pentru acest flux și fără bilanțurile ANAF aliniate după CUI și an.
- _ANAF_ oferă datele prin interogare per CUI sau per lot, nu ca set descărcabil complet.
- _totalfirme.ro, listafirme.ro_ etc. au date utile, dar sunt comerciale, fără licență de reutilizare și fără export garantat.

Contribuția noastră: un set deduplicat după CUI, cu schemă fixă, proveniență clară și date financiare organizate longitudinal. Un set nou este necesar pentru că niciuna dintre sursele folosite nu oferă această combinație într-un format reutilizabil fără prelucrare suplimentară.

## 2. Surse

| Sursă | Ce furnizează | Licență / condiții | Dimensiune aprox. |
| --- | --- | --- | --- |
| totalfirme.ro, listă pe județ (`/judet-BUCUREȘTI`) — **deja extras** cu `src/scrape_totalfirme/scarep.py` | lista inițială de CUI-uri | Site comercial; fără licență explicită. Folosim doar CUI-ul pentru construirea listei. Termenii de utilizare se verifică înainte de publicare. | 445.800 rânduri |
| ANAF — API public „Platitor TVA” (`webservicesp.anaf.ro`) | datele din `firme.csv`: denumire, număr de registru, CAEN, formă juridică, stare de înregistrare, data înregistrării ANAF, TVA și adresa sediului social | Date publice furnizate de un serviciu public; se respectă limitele de rată și termenii sursei. | ~445.800 CUI-uri |
| ANAF — API bilanț (`webservicesp.anaf.ro/bilant`) | indicatori financiari pentru un CUI și un an solicitat | Se interoghează separat pentru fiecare CUI și an, cu cache separat pe an. | depinde de an și de disponibilitatea datelor |
| data.gov.ro — seturile ONRC de firme (completare / verificare încrucișată) | eventual data înmatriculării și starea | Open Government Licence 1.0 România, dacă setul utilizat permite reutilizarea. | de verificat |
| BPI — Buletinul Procedurilor de Insolvență / portal.just.ro (opțional) | etichete pentru deschiderea procedurii de insolvență | De verificat: accesul, licența și acoperirea istorică. Nu este necesar pentru obiectivul financiar principal. | de verificat |

## 3. Date sensibile și limitări

- CUI-ul, denumirea, adresa sediului și starea de înregistrare sunt date publice de registru, dar trebuie folosite conform condițiilor sursei.
- Unele denumiri sau adrese pot conține nume de persoane, în special pentru PFA, II sau IF. În schema actuală aceste valori sunt păstrate de API; anonimizarea sau eliminarea lor trebuie decisă înainte de publicare.
- Nu colectăm CNP, telefon, e-mail, asociați sau administratori prin aceste scripturi.
- Cache-ul conține răspunsuri JSON brute de la ANAF și trebuie tratat separat de fișierele CSV publicabile.
- Bilanțul poate lipsi pentru firme mici, firme inactive sau ani pentru care API-ul nu returnează indicatori. Lipsa datelor este o valoare necunoscută, nu automat zero și nu automat insolvență.

## 4. Schema efectivă a datelor

### 4.1 `firme.csv`

Un rând reprezintă o firmă identificată prin `cui`. Fișierul este construit de `extract_firme.py` sau poate fi restaurat din cache cu `restore_firme_from_cache.py`.

| Câmp | Tip / valori | Descriere |
| --- | --- | --- |
| `cui` | text numeric | Identificator fiscal normalizat, fără prefixul `RO`. |
| `data_interogare` | `YYYY-MM-DD` | Data trimisă către API-ul ANAF pentru interogarea generală. |
| `colectat_la` | timestamp ISO 8601 | Momentul colectării răspunsului salvat. |
| `status_extragere` | `gasit`, `negasit`, `eroare` | Rezultatul extragerii generale pentru CUI. |
| `denumire` | text sau gol | Denumirea returnată de ANAF. |
| `nr_reg_com` | text sau gol | Numărul de registru comercial. |
| `cod_caen` | text sau gol | Codul CAEN returnat de ANAF. Nu se derivează automat o secțiune CAEN. |
| `forma_juridica` | text sau gol | Forma juridică returnată de ANAF. |
| `forma_organizare` | text sau gol | Forma de organizare returnată de ANAF. |
| `stare_inregistrare_anaf` | text sau gol | Starea textuală ANAF, de exemplu `INREGISTRAT`, `RADIERE` sau `TRANSFER`. Nu este o enumerație normalizată în prezent. |
| `data_inregistrare_anaf` | `YYYY-MM-DD` sau gol | Data înregistrării returnată de ANAF; este folosită pentru filtrarea CUI-urilor eligibile pentru bilanțuri. |
| `platitor_tva` | boolean sau gol | Statutul `scpTVA`. |
| `tva_incasare` | boolean sau gol | Statutul TVA la încasare. |
| `inactiv_fiscal` | boolean sau gol | Statutul de inactivitate fiscală. |
| `data_inactivare` | dată sau gol | Data inactivării, dacă este furnizată. |
| `data_reactivare` | dată sau gol | Data reactivării, dacă este furnizată. |
| `adresa` | text sau gol | Adresa generală returnată de ANAF. |
| `judet` | text sau gol | Județul sau municipiul returnat de ANAF. |
| `localitate` | text sau gol | Localitatea returnată de ANAF. |
| `strada` | text sau gol | Strada sediului social. |
| `numar` | text sau gol | Numărul străzii. |
| `cod_postal` | text sau gol | Codul poștal. |
| `detalii_adresa` | text sau gol | Detalii suplimentare ale adresei. |

Fișierul nu conține în prezent câmpuri separate `stare`, `sector`, `domeniu_caen`, `an_infiintare`, `event` sau `tip_eveniment`. Acestea nu trebuie folosite în experimente fără o etapă explicită de derivare și validare.

### 4.2 `bilanturi_<an>.csv`

Se creează câte un fișier pentru fiecare an cerut, de exemplu `bilanturi_2023.csv` și `bilanturi_2024.csv`. Un rând reprezintă un CUI pentru anul respectiv; indicatorii returnați de aceeași cerere sunt puși în aceeași linie.

| Câmp | Tip / valori | Descriere |
| --- | --- | --- |
| `cui` | text numeric | Cheie de legătură cu `firme.csv`. |
| `an` | întreg | Anul bilanțului. |
| `colectat_la` | timestamp ISO 8601 | Momentul colectării răspunsului. |
| `denumire` | text sau gol | Denumirea returnată de endpoint-ul de bilanț; poate lipsi chiar dacă există în `firme.csv`. |
| `cod_caen` | text sau gol | Codul CAEN din răspunsul de bilanț. |
| indicatorii de mai jos | număr, text numeric sau gol | Valoarea `val_indicator` pentru denumirea `val_den_indicator` corespunzătoare. |

Coloanele indicatorilor sunt:

```text
ACTIVE IMOBILIZATE - TOTAL
ACTIVE CIRCULANTE - TOTAL, din care:
Stocuri
Creante
Casa şi conturi la bănci
CHELTUIELI IN AVANS
DATORII
VENITURI IN AVANS
PROVIZIOANE
CAPITALURI - TOTAL, din care:
Capital subscris varsat
Patrimoniul regiei
Cifra de afaceri neta
VENITURI TOTALE
CHELTUIELI TOTALE
Profit brut
Pierdere bruta
Profit net
Pierdere neta
Numar mediu de salariati
```

Valorile indicatorilor nu trebuie convertite automat la zero când lipsesc. Pentru modelare, conversia numerică, semnul și lipsa trebuie documentate separat.

### 4.3 Cache și erori

Răspunsurile generale sunt cache-uite în `.cache_anaf`, iar bilanțurile în directoare cu an, de exemplu `.cache_anaf_bilant_2024`. Erorile sunt scrise în `erori.csv` pentru date generale sau `erori_bilant.csv` pentru bilanțuri, cu coloanele `cui`, `etapa`, `an`, `eroare`.

## 5. Cum arătăm că setul e util

### Obiectiv principal: predicție financiară

Construim o masă longitudinală prin unirea `firme.csv` cu mai multe fișiere `bilanturi_<an>.csv` pe `cui` și `an`. Pentru un an de predicție `t`, trăsăturile folosesc numai anii anteriori lui `t`, de exemplu `t-1`, `t-2` și `t-3`.

Ținte posibile, în ordinea priorității:

1. **Regresie pentru pierderi sau profit:** `Pierdere neta`, `Profit net`, `Profit brut`, `VENITURI TOTALE` sau `CHELTUIELI TOTALE` în anul `t`.
2. **Predicția bilanțului:** valorile indicatorilor disponibili în `bilanturi_t.csv`, inclusiv `Cifra de afaceri neta` și `Numar mediu de salariati`.
3. **Predicția creșterii firmei:** variația procentuală sau diferența anuală pentru cifra de afaceri, venituri, profit și numărul mediu de salariați. Pentru valori zero sau lipsă se definesc reguli explicite.
4. **Clasificarea performanței:** categorii precum `castig_bun`, `castig_slab`, `pierdere`, `stagnare` și `date_insuficiente`, definite din indicatorii anului țintă și fără folosirea informațiilor viitoare ca trăsături.

Rezultatele se evaluează prin împărțire temporală: anii mai vechi pentru antrenare și ani mai recenți pentru test. Pentru regresie raportăm MAE, RMSE și, când scara permite, MAPE/SMAPE; pentru clasificare raportăm balanced accuracy, macro-F1, ROC-AUC sau PR-AUC, în funcție de dezechilibrul claselor. Comparam cu linii de bază simple, cum ar fi ultima valoare cunoscută, media ultimilor ani și predicția majoritară.

### Obiectiv opțional: insolvență

Adăugăm această variantă numai dacă obținem etichete istorice verificabile pentru data deschiderii procedurii. Ținta ar fi `insolventa_in_urmatorii_N_ani`, nu „firmă radiată”. Radierea voluntară, fuziunea și lipsa unui bilanț rămân evenimente sau valori distincte. Pentru acest obiectiv folosim modele de clasificare sau survival, cu evaluare temporală și PR-AUC/C-index, și raportăm separat rata de etichete lipsă.

**Riscuri cunoscute:** 
(1) lista inițială de CUI-uri poate fi părtinită spre firmele vizibile în sursa de pornire; <br>
(2) bilanțurile lipsesc la firmele foarte mici sau pentru anii fără date în API; <br>
(3) valorile financiare pot avea distribuții foarte asimetrice și valori zero; <br>
(4) categoriile de performanță depind de praguri și trebuie stabilite înaintea evaluării; <br>
(5) etichetele de insolvență sunt rare și necesită o sursă separată. Nu interpretăm lipsa datelor ca pierdere, insolvență sau zero fără justificare.
