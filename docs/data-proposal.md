# Data proposal — Firme din București

**Echipa:** Oprea Marina, Ghidic Vladislav, Suciu Delia Bianca, Stoian Robert Alin

## 1. De ce acest dataset?

Construim un set tabelar cu firmele din municipiul București cu profilul firmei (denumire, formă juridică, CAEN, stare ANAF, TVA, adresă) și bilanțul anual 2009–2025.

- **La ce e bun:** predicția evoluției financiare a unei firme în anul următor (cifră de afaceri, profit/pierdere, număr de salariați), predicția creșterii/scăderii și analize longitudinale pe sectoare (CAEN) și sectoare ale Capitalei.
- **Cine l-ar folosi:** cercetători și jurnaliști, analiști de piață, cei care antrenează modele de regresie/clasificare.
- **Ce există deja și de ce nu ajunge:**
  - _data.gov.ro_ (bilanțuri MFP): fișiere separate pe an, cu nume de coloane și formate inconsistente între ani (`CUI`/`cui`, `CAEN`/`caen`), fără profilul firmei și fără filtrare.
  - _ANAF_ (API „Plătitor TVA”): date pe CUI, nu este un set descărcabil.
  - _totalfirme.ro, listafirme.ro_: planuri comerciale, cu limită de utilizare fără plată.

- **Valoarea adăugată**: un set unificat pe `cui` care combină profilul și seria de bilanțuri într-un format direct utilizabil.

## 2. Surse

| Sursă                                                                                          | Conținut                          | Dimensiune                                               |
| ---------------------------------------------------------------------------------------------- | --------------------------------- | -------------------------------------------------------- |
| [totalfirme.ro](https://www.totalfirme.ro) (listă `/judet-BUCUREȘTI`), `src/scrape_totalfirme` | doar lista de CUI-uri             | 445.759 CUI                                              |
| [ANAF — API Plătitor TVA](https://webservicesp.anaf.ro) (`src/extract_details`)                | profilul firmei (`firme.csv`)     | 445.759 rânduri, ~165 MB CSV                             |
| [data.gov.ro — Situații financiare (Min. Finanțelor)](https://data.gov.ro)                     | bilanțuri anuale, 2008–2025       | ~147 MB; ~407.000 rânduri CUI-an în fișierele `BL_BS_SL` |
| ANAF — API bilanț (opțional, completări)                                                       | indicatori pentru un CUI și un an | variabilă                                                |

Limitări: numărul de rânduri pe an scade de la ~71.000 (2014) la ~7–10.000 (2015+) în fișierele de bilanț, urmează să verificăm dacă e o diferență reală de acoperire sau un efect al sursei/filtrării.

## 3. Date sensibile

- Datele sunt de registru public, fără CNP, telefon, e-mail, asociați sau administratori.
- Risc: la PFA/II/IF și unele ONG-uri, `denumire` și `adresa` pot conține numele unei persoane fizice și adresa de domiciliu. Plan: în setul publicat păstrăm doar persoanele juridice (SRL, SA etc.) și excludem/anonimizăm rândurile de tip PFA/II/IF (hash pe `denumire`, adresă redusă la sector). Eșantionul atașat conține doar SRL/SA.

## 4. Schema

Un rând reprezintă o firmă (`firme`) sau o pereche firmă–an (`bilanturi`), legate prin `cui`.

**`firme`**

| Câmp                                                             | Tip            | Descriere                                |
| ---------------------------------------------------------------- | -------------- | ---------------------------------------- |
| `cui`                                                            | string (cheie) | identificator fiscal, fără prefix `RO`   |
| `denumire`                                                       | string         | denumirea firmei                         |
| `nr_reg_com`                                                     | string \| null | număr registrul comerțului               |
| `cod_caen`                                                       | string \| null | cod CAEN (ex. `5811`)                    |
| `forma_juridica`                                                 | string         | ex. SRL, SA                              |
| `stare_inregistrare_anaf`                                        | string         | ex. `INREGISTRAT`, `RADIERE`, `TRANSFER` |
| `data_inregistrare_anaf`                                         | date \| null   |                                          |
| `platitor_tva`, `tva_incasare`, `inactiv_fiscal`                 | bool \| null   | statut fiscal                            |
| `adresa`, `judet`, `localitate`, `strada`, `numar`, `cod_postal` | string \| null | sediul social                            |
| `status_extragere`, `data_interogare`, `colectat_la`             | meta           | proveniența colectării                   |

**`bilanturi`**

| Câmp                                                           | Tip            | Descriere                                       |
| -------------------------------------------------------------- | -------------- | ----------------------------------------------- |
| `an`                                                           | int            | anul raportării                                 |
| `Active imobilizate  -  total`                                 | number \| null | indicator financiar (RON)                       |
| `Active circulante  -  total`                                  | number \| null | indicator financiar (RON)                       |
| `Cheltuieli in avans`                                          | number \| null | indicator financiar (RON)                       |
| `Datorii ce trebuie platite intr-o perioada de pana la un an`  | number \| null | indicator financiar (RON)                       |
| `Active circulante nete, respectiv datorii curente nete`       | number \| null | indicator financiar (RON)                       |
| `Total active minus datorii curente`                           | number \| null | indicator financiar (RON)                       |
| `Datorii ce trebuie platite intr-o perioada mai mare de un an` | number \| null | indicator financiar (RON)                       |
| `...`                                                          | number \| null | restul indicatorilor din set, păstrați ca atare |

Lipsa unei valori înseamnă „necunoscut”, nu zero.

**Exemple** (din eșantion):

```json
{
  "cui": "29668874",
  "denumire": "GERLACH EUROPEAN SERVICES SRL",
  "cod_caen": "5226",
  "forma_juridica": "SOCIETATE COMERCIALĂ CU RĂSPUNDERE LIMITATĂ",
  "stare_inregistrare_anaf": "INREGISTRAT din data 10.02.2012",
  "platitor_tva": true,
  "localitate": "Sector 6 Mun. București",
  "bilant": {
    "an": 2024,
    "Active imobilizate  -  total": 115493383,
    "Active circulante  -  total": 510830,
    "Cheltuieli in avans": 50
  }
}
```

## 5. Cum arătăm că setul e util

**Împărțire temporală**: antrenare pe ani vechi, test pe anul cel mai recent. Predicem profit/pierdere și cifra de afaceri la anul `t` din profil + bilanțurile `t-1…t-3`, și comparăm cu baze simple (ultima valoare, media ultimilor ani). Dacă profilul (CAEN, sector, formă juridică) și seria multianuală reduc MAE/RMSE față de baze, setul își dovedește utilitatea. Lipsa bilanțului nu este tratată ca zero sau insolvență.

_Pentru etapele următoare:_ pașii de pipeline (deduplicare, outlieri, tagging CAEN) și proveniența fiecărui câmp (original/derivat/AI/manual).
