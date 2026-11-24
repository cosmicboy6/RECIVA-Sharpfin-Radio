# Third-party / upstream Sharpfin-Artefakte

Dieser Ordner enthält **unveränderte bzw. minimal umbenannte Upstream-Dateien**
von Sharpfin / dliw / der Reciva-Community. Sie wurden auf ausdrücklichen
Wunsch des Repository-Inhabers hier abgelegt, damit das Deployment-Paket
komplett reproduzierbar ist.

Diese Dateien sind **nicht** von diesem Projekt geschrieben worden. Urheberrecht
und Lizenz liegen bei den jeweiligen Upstream-Autoren. Bitte die Lizenzlage vor
weiterer Weitergabe prüfen. Bekannt:

- `philsmd/sharpfin` steht unter **GPL-3.0** und liefert historischen
  C++-Patchserver-Quellcode.
- Die hier verwendete `server`-Binary stammt aus **dliw**'s Build; dessen
  Quellcode wurde nach unserem Wissen nie veröffentlicht (siehe
  [`../README.md`](../README.md), Credits/Abschnitt 9). Für GPL-konforme
  Weitergabe bitte an den Upstream wenden.
- Die `.install`-Dateien kommen von Sharpfin / megapico bzw. David.

Es werden **keine gerätebezogenen Geheimnisse** mitgeliefert: Der DES-Key wird
zur Laufzeit aus `.env` in `configure_gui.sh` injiziert, die Seriennummer bleibt
ein Platzhalter.

## Dateien und Prüfsummen

| Datei | SHA256 | MD5 / Anmerkung |
|---|---|---|
| `RecivaServer/server` | `2d899b010d4f5544a62183fe401a34e7970b189a4ddaaf99d6808b63f31689d0` | gepatchte Binary mit 30er-Clamp |
| `RecivaServer/server.bak-noClamp` | `94ae9c257cbcca04e7739e0cd216271a61c670bdd04673e7e2c1e465b2a23a41` | Original-Binary ohne Clamp |
| `files/sharpfin-base_0.3_IPdio.patch` | `f6260d6db972e9e8efbb00fab83326bf4f9adc379363539bb64dd30a890966bf` | MD5 `043934970007ed0e83ad62ecb8d54b02`, 204.896 B |
| `files/sharpfin-base_0.3_generic.patch` | `fb374a863cc798f736059b9daa36da04ed01e6eedb158a035f4749d506727ada` | MD5 `da6ffd368350f575dc5e706ee1727e4e`, Generik-Variante |
| `files/sharpfin-ep2.install` | `0d043a2d19cd3c72315c5ac2e8793f8e2194725529645c6b9d97a223178808e3` | MD5 `0fb48bcb3b490829347cce8d0ae11a06` |
| `files/media-server-1.0.install` | `45285fabfe4954acb8df8a8d069d7c754b6662fda953da69155712841d0dbee2` | MD5 `aaceefaed14bcc8b3b0fbc0d8c76b28d`; Kopie von `Sharpfin-media-server-1.0.install`, kleingeschrieben für die HTTP-URL |
| `files/media-server-2.1.2.install` | `f76ff020c0808baa289f32fd59b5919239e6b7d018d16c976c69f50828756d05` | MD5 `7d40a138ac65e680ce3a7a612f1a34f0`; Fallback, nicht installiert |

## Quellen

- https://www.sharpf.in/
- https://www.megapico.co.uk/sharpfin/
- https://github.com/philsmd/sharpfin (GPL-3.0)
- https://github.com/jisotalo/reciva-radio-patching (IPdio-Patches)
- https://web.archive.org/web/20250107210502/https://iradioforum.net/forum/index.php?topic=2968.0 (dliw: „Some findings“)

Die Installation und Verifikation dieser Dateien erfolgt ausschließlich über
`./scripts/install.sh` und `./scripts/verify.sh`; das Radio wird dabei nicht
angefasst.
