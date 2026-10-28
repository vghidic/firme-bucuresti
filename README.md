# Firme Bucuresti

### Echipa: Oprea Marina, Ghidic Vladislav, Suciu Delia Bianca, Stoian Robert Alin

# Schema

Un rând reprezintă o firmă identificată prin `cui`. Fișierul este construit de `extract_firme.py` sau poate fi restaurat din cache cu `restore_firme_from_cache.py`.

| Câmp                      | Tip / valori                 | Descriere                                                                                                              |
| ------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `cui`                     | text numeric                 | Identificator fiscal normalizat, fără prefixul `RO`.                                                                   |
| `data_interogare`         | `YYYY-MM-DD`                 | Data trimisă către API-ul ANAF pentru interogarea generală.                                                            |
| `colectat_la`             | timestamp ISO 8601           | Momentul colectării răspunsului salvat.                                                                                |
| `status_extragere`        | `gasit`, `negasit`, `eroare` | Rezultatul extragerii generale pentru CUI.                                                                             |
| `denumire`                | text sau gol                 | Denumirea returnată de ANAF.                                                                                           |
| `nr_reg_com`              | text sau gol                 | Numărul de registru comercial.                                                                                         |
| `cod_caen`                | text sau gol                 | Codul CAEN returnat de ANAF. Nu se derivează automat o secțiune CAEN.                                                  |
| `forma_juridica`          | text sau gol                 | Forma juridică returnată de ANAF.                                                                                      |
| `forma_organizare`        | text sau gol                 | Forma de organizare returnată de ANAF.                                                                                 |
| `stare_inregistrare_anaf` | text sau gol                 | Starea textuală ANAF, de exemplu `INREGISTRAT`, `RADIERE` sau `TRANSFER`. Nu este o enumerație normalizată în prezent. |
| `data_inregistrare_anaf`  | `YYYY-MM-DD` sau gol         | Data înregistrării returnată de ANAF; este folosită pentru filtrarea CUI-urilor eligibile pentru bilanțuri.            |
| `platitor_tva`            | boolean sau gol              | Statutul `scpTVA`.                                                                                                     |
| `tva_incasare`            | boolean sau gol              | Statutul TVA la încasare.                                                                                              |
| `inactiv_fiscal`          | boolean sau gol              | Statutul de inactivitate fiscală.                                                                                      |
| `data_inactivare`         | dată sau gol                 | Data inactivării, dacă este furnizată.                                                                                 |
| `data_reactivare`         | dată sau gol                 | Data reactivării, dacă este furnizată.                                                                                 |
| `adresa`                  | text sau gol                 | Adresa generală returnată de ANAF.                                                                                     |
| `judet`                   | text sau gol                 | Județul sau municipiul returnat de ANAF.                                                                               |
| `localitate`              | text sau gol                 | Localitatea returnată de ANAF.                                                                                         |
| `strada`                  | text sau gol                 | Strada sediului social.                                                                                                |
| `numar`                   | text sau gol                 | Numărul străzii.                                                                                                       |
| `cod_postal`              | text sau gol                 | Codul poștal.                                                                                                          |
| `detalii_adresa`          | text sau gol                 | Detalii suplimentare ale adresei.                                                                                      |

## Scopul

Construim un set tabelar cu firmele din municipiul București (~445.800 de CUI-uri colectate până acum), îmbogățit cu date publice ANAF despre fiecare firmă și, separat, cu indicatori de bilanț pe an. Setul este construit în jurul unei chei comune: `cui`.

Datele generale includ denumirea, starea de înregistrare ANAF, forma juridică, codul CAEN, adresa sediului social și informațiile TVA. Datele de bilanț sunt salvate câte un rând pentru fiecare combinație CUI-an, cu indicatorii financiari în coloane separate.

**Modelul:** predicția evoluției financiare a unei firme într-un an ulterior, folosind datele generale și unul sau mai mulți ani de bilanț anteriori. Exemple de ținte:

- predicția valorii unui indicator financiar în anul următor, de exemplu cifra de afaceri, veniturile totale, cheltuielile totale, profitul net sau pierderea netă;
- predicția variației unui indicator: creștere, stagnare sau scădere;
- predicția disponibilității bilanțului într-un an ulterior, cu atenție la faptul că lipsa unui bilanț poate însemna lipsă de depunere, lipsă în API sau inactivitate, nu neapărat un eveniment economic;
- predicția unei categorii de performanță, de exemplu „câștig bun”, „câștig slab”, „pierdere” sau „date insuficiente”, definită prin reguli explicite aplicate indicatorilor disponibili.

**Cine l-ar folosi:** cercetători și jurnaliști (studii despre economia Capitalei și dinamica firmelor), analiști de piață (comparații pe CAEN și sectoare, după ce aceste câmpuri sunt derivate), studenți (curățare, deduplicare și analiză longitudinală) și cei care antrenează modele de regresie, clasificare sau serii temporale.
