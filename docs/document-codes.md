# Document codes

`document_code` in `data/measures/measures.csv` is a short, stable code for the certificate, licence, registration or standard a measure points at. The codes are defined here, not by any authority, and do not change once published. A blank code means the measure carries no specific document (for example a plain `import_policy` row).

| Code | Meaning | Used with |
|---|---|---|
| `BIS-ISI` | BIS Scheme I: ISI-mark certification under a Quality Control Order that is in force or withdrawn | `bis_isi_qco` |
| `BIS-ISI-UPCOMING` | As `BIS-ISI`, for a QCO that is notified and not yet enforced (`status=upcoming`, `valid_from` is the enforcement date) | `bis_upcoming_qco` |
| `BIS-ISI-OPT2` | BIS Option-2 (simplified procedure) list | `bis_isi_qco` |
| `BIS-CRS` | BIS Compulsory Registration Scheme (Scheme II), including the non-MeitY Scheme II list | `bis_crs` |
| `BIS-SCHEME-X` | BIS Scheme X: electrical equipment type testing | `bis_scheme_x` |
| `BIS-SCHEME-IV` | BIS Scheme IV: essential-requirement or input-material certification | `other_condition` |
| `BIS-STD` | The ITC(HS) text requires conformity to an IS number (or Indian Standards generally) that no BIS compulsory-certification list carries; a standard, not a certificate | `other_condition` |
| `TEC-MTCTE` | Mandatory Testing and Certification of Telecom Equipment (TEC) | `tec_mtcte` |
| `BEE-LABEL` | BEE star label | `bee_label` |
| `DGFT-LIC` | The condition text refers to a DGFT import licence or authorisation | `policy_condition` |
| `SIMS` | Steel Import Monitoring System registration | `import_monitoring` |
| `CHIMS` | Chip Import Monitoring System registration | `import_monitoring` |
| `NFMIMS` | Non-Ferrous Metals Import Monitoring System registration | `import_monitoring` |
| `PIMS` | Paper Import Monitoring System registration | `import_monitoring` |
| `IMS` | Another import monitoring system named in the text (`measure_value` carries its name) | `import_monitoring` |
| `WPC-ETA` | Wireless Planning and Coordination approval (keyword candidate) | `other_condition` |
| `LEGAL-METROLOGY` | Legal Metrology requirements (keyword candidate) | `other_condition` |
| `EPR` | Extended Producer Responsibility registration (keyword candidate) | `other_condition` |
| `CDSCO` | Central Drugs Standard Control Organisation requirements (keyword candidate) | `other_condition` |
| `FSSAI` | Food Safety and Standards Authority requirements (keyword candidate) | `other_condition` |

Codes are assigned from the list a measure comes from or from the words of the official text. A code states which document the text points at; it does not say the document is held, valid or applicable to a given consignment. Not legal advice: confirm with the issuing authority.
