# Filarmonica Giuseppe Verdi · Lecco

Il sito usa **Flask**, template **Jinja** e un database **SQLite**. Eventi, notizie, album, fotografie, insegnanti e schede introduttive si aggiornano dal pannello `/admin`, dove puoi anche scegliere i contenuti in evidenza nella homepage. Le modifiche salvate sono subito visibili sul sito, senza rigenerare le pagine.

Il sito pubblico conserva gli indirizzi esistenti, la grafica e le gallerie. Il collegamento al pannello non compare nei menu pubblici: per accedere occorre conoscere l’indirizzo e autenticarsi.

## Primo avvio

Serve Python 3.11 o successivo. Dalla cartella del progetto, su Linux o macOS:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app app create-admin
.venv/bin/python -m flask --app app run --port 8080
```

Su Windows crea l’ambiente con `py -m venv .venv` e sostituisci `.venv/bin/python` con `.venv\Scripts\python.exe` nei comandi successivi.

Apri [http://127.0.0.1:8080](http://127.0.0.1:8080). Per amministrare il sito visita [http://127.0.0.1:8080/admin](http://127.0.0.1:8080/admin).

Il comando `create-admin` chiede soltanto la password, con conferma. La password non viene mostrata mentre la digiti. **Non esistono credenziali predefinite**. Puoi ripetere il comando per creare altri amministratori.

La pagina `/admin` richiede soltanto la password. Non vengono memorizzati nomi utente. Usa password diverse per amministratori diversi: se più account condividono la stessa password, l’accesso viene associato al primo account creato.

Per cambiare la password di un account esistente:

```bash
.venv/bin/python -m flask --app app create-admin --reset-password
```

Il cambio password revoca le sessioni già aperte dell’account. Il comando opera sullo stesso database usato dal sito: in produzione imposta anche qui `CMS_INSTANCE_PATH` con il percorso del servizio.

Se esistono più amministratori, il comando elenca gli ID disponibili: aggiungi `--admin-id ID` per scegliere quale password cambiare. I database precedenti vengono aggiornati automaticamente all’avvio, eliminando i nomi utente e conservando password e sessioni.

Il server locale ascolta solo sul computer. Per provarlo da un telefono nella stessa rete:

```bash
.venv/bin/python -m flask --app app run --host 0.0.0.0 --port 8080
```

Apri sul telefono `http://IP-DEL-COMPUTER:8080`. Per cambiare porta sostituisci `8080` con quella desiderata. Arresta il server con `Ctrl+C`.

Le modifiche ai template HTML vengono rilevate alla richiesta successiva anche senza debug: salva il file e aggiorna la pagina. Per ricaricare automaticamente anche il codice Python, avvialo con `.venv/bin/python -m flask --app app run --debug --port 8080`. Usa questa modalità soltanto sul tuo computer, mantenendo l’indirizzo predefinito `127.0.0.1`.

## Usare il pannello

Prima dell’accesso, `/admin` mostra il modulo di login. Dopo l’accesso lo stesso indirizzo mostra il riepilogo con i collegamenti alle aree di gestione.

| Area | Contenuti modificabili |
| --- | --- |
| Eventi | Titolo, indirizzo breve, data, luogo, descrizione e orario |
| Notizie | Titolo, indirizzo breve, data, sommario, testo formattato, immagine ed eventuale articolo esterno |
| Foto | Album, una o più date, descrizione e crediti, copertina, cartella Drive e fotografie di ciascun album |
| Homepage | Appuntamenti da mostrare e una notizia in evidenza |
| Scopri la Filarmonica | Titolo della sezione e schede con testi, collegamenti e ordine |
| I nostri insegnanti | Nomi, strumenti, fotografie, descrizioni delle immagini e ordine |

Le aree dei contenuti permettono di aggiungere, modificare ed eliminare le schede. L’opzione **Nascosto** controlla la visibilità: attivala per conservare una bozza. L’eliminazione richiede una conferma e non dispone di annullamento dal pannello; per recuperare dati eliminati serve un backup.

Dopo il salvataggio rimani nel modulo di modifica, con un messaggio di conferma. Anche un nuovo contenuto si apre nel proprio modulo, così puoi continuare a modificarlo senza crearne una copia. Per un album, usa **Gestisci le foto** per passare alle fotografie.

L’**indirizzo breve** deve essere univoco nell’area e usare lettere minuscole, numeri e trattini. Per le notizie e gli album diventa parte dell’URL, per esempio `/blog/concerto-autunno.html` e `/foto/concerto-autunno.html`. Mantienilo invariato quando un collegamento è già stato condiviso.

Per eventi e notizie puoi indicare una data completa `AAAA-MM-GG` oppure soltanto mese e anno `AAAA-MM`. Anche gli album accettano entrambi i formati e possono avere più date separate da virgole, per esempio `2026-10-06, 2026-10-07`. Le date vengono ordinate e i duplicati rimossi; la prima data determina l’ordinamento e l’anno dell’album nell’archivio. Tutte le date compaiono nella scheda e nella galleria. Gli album esistenti con solo mese e anno restano validi.

Sul sito le date sono abbreviate senza ripetere mese e anno comuni: `6 - 7 ottobre 2026`, `6 ottobre - 6 novembre 2026`, oppure `31 dicembre 2026 - 2 gennaio 2027`. Nel modulo si continuano a inserire le date complete separate da virgole.

In **Homepage** (`/admin/home`) seleziona quanti appuntamenti vuoi e una sola notizia per “Ultime notizie”. Puoi anche lasciare entrambe le sezioni senza selezioni. Gli eventi scelti sono mostrati in ordine cronologico, senza limite di numero; rimangono selezionati anche dopo la loro data. Le bozze e i contenuti eliminati non vengono mostrati né sostituiti automaticamente.

Fino al primo salvataggio di questa pagina resta la selezione automatica precedente: tre prossimi eventi e la notizia pubblicata più recente. Il salvataggio passa alla selezione manuale.

In **Scopri la Filarmonica** (`/admin/musica-insieme`) puoi cambiare “La musica si vive insieme.” nel campo **Titolo nella home**, aggiungere o modificare le schede. In **I nostri insegnanti** (`/admin/insegnanti`) puoi gestire le schede degli insegnanti e caricare le fotografie. Usa le frecce ↑ e ↓ negli elenchi per spostare una scheda di una posizione: le nuove schede vengono aggiunte in fondo e modificarle non ne cambia l’ordine. Per una scheda condivisa, scrivi ogni nome su una riga distinta.

Il testo delle notizie dispone di comandi di formattazione. Il server ammette paragrafi, titoli, elenchi, collegamenti e immagini e pulisce l’HTML al salvataggio. Inserendo un **Link articolo esterno**, la scheda pubblica collega direttamente la fonte esterna.

La casella **Nascosto** si trova negli elenchi di eventi, notizie, album, schede e insegnanti: selezionata nasconde la voce e la rende sbiadita nel pannello, deselezionata la pubblica. Salva automaticamente senza ricaricare la pagina. I nuovi contenuti sono pubblicati; le modifiche ai testi non cambiano lo stato di pubblicazione.

## Album e fotografie

Crea un album dall’area Foto e poi apri **Gestisci le foto**. Puoi caricare una fotografia, indicare un URL HTTPS, cambiare la descrizione, sostituire l’immagine o rimuoverla dall’album. Le nuove foto vengono aggiunte in fondo; modificare una foto non ne cambia la posizione. La copertina dell’album si modifica separatamente.

I caricamenti accettano JPG, PNG, WebP e GIF, fino a **16 MB per richiesta** e **30 megapixel per immagine**. Il server applica l’orientamento della foto, riduce il lato maggiore a 3200 pixel quando necessario e salva una copia WebP. Le GIF diventano immagini statiche. Il download delle immagini caricate restituisce questa copia elaborata; conserva separatamente i file originali se ti servono alla risoluzione iniziale.

Le immagini possono anche usare percorsi già presenti nel sito, come `/assets/foto/copertina.jpg`, o URL HTTPS. Il pannello converte i collegamenti ai singoli file Google Drive in URL visualizzabili.

Eliminare una fotografia dal pannello elimina il suo riferimento nell’album. I file già caricati in `uploads/` vengono conservati, anche quando un riferimento viene rimosso o sostituito.

Per nascondere una fotografia senza eliminarla, attiva **Nascondi** sulla sua scheda nella gestione delle foto: la scelta si salva subito e l’immagine appare attenuata. Disattiva la casella per mostrarla di nuovo. Senza JavaScript usa **Salva visibilità**. La stessa opzione resta disponibile in **Modifica**. La sincronizzazione Drive conserva questa scelta per le foto ancora presenti nell’album. I collegamenti diretti ai file e la copertina dell’album restano invariati.

### Sincronizzare Google Drive

1. Rendi la cartella e le fotografie accessibili a chiunque abbia il collegamento.
2. Salva il link della cartella nel campo dell’album dedicato a Google Drive.
3. Apri la gestione delle fotografie e premi **Sincronizza foto**.

La sincronizzazione legge anche le sottocartelle ed esclude i video. Aggiorna soltanto l’album selezionato: le foto Drive già presenti mantengono descrizioni e ordine, quelle non più presenti nella cartella vengono rimosse dall’album e le nuove vengono aggiunte in fondo, ordinate per nome. Le foto caricate dal computer e i collegamenti aggiunti manualmente restano conservati. Il primo import in un album vuoto segue l’ordine dei nomi dei file.

Un errore durante la lettura di Drive conserva la galleria precedente. Le fotografie restano ospitate su Drive: l’importazione salva i collegamenti, non scarica i file. Per vedere le immagini esterne serve una connessione Internet. Le modifiche fatte su Drive compaiono nel sito soltanto dopo una nuova sincronizzazione dal pannello.

Se necessario, configura `GOOGLE_DRIVE_API_KEY` nell’ambiente del processo del sito, con Drive API abilitata nel relativo progetto Google Cloud. La chiave rimane sul server. La cache degli elenchi è in `.cache/drive/`; il comando del pannello verifica comunque gli aggiornamenti remoti.

## Template e struttura del progetto

| Percorso | Ruolo |
| --- | --- |
| `app/__init__.py` | Applicazione Flask, pagine pubbliche, configurazione e comandi amministrativi |
| `app/admin.py` | Login, sessioni e pagine del pannello |
| `app/editorial.py` | Selezioni della homepage, schede introduttive e insegnanti |
| `app/content.py` | Validazione dei contenuti, salvataggi e sincronizzazione Drive |
| `app/drive.py` | Lettura delle cartelle Google Drive e cache, in Python |
| `app/templates/base.html` | Struttura HTML comune delle pagine pubbliche |
| `app/templates/public/` | Template delle pagine, header, footer e componenti condivisi |
| `app/templates/admin/` | Template del pannello |
| `app/schema.sql` | Schema SQLite: contenuti, account, sessioni e metadati |
| `public/styles.css` e `public/admin.css` | Stili del sito e del pannello |
| `public/gallery.js` | Ingrandimento, navigazione e download nelle gallerie |
| `public/assets/` | Immagini e risorse originali |
| `public/_redirects` | Reindirizzamenti degli indirizzi precedenti, applicati da Flask |
| `instance/` | Database, immagini caricate e chiave delle sessioni; esclusi da Git |

Le pagine usano `{% extends "base.html" %}`, blocchi Jinja e componenti condivisi. Per cambiare la navigazione modifica `app/templates/public/_header.html`; per il footer modifica `app/templates/public/_footer.html`.

I campi dei moduli, le etichette e i testi di aiuto del pannello sono nei file HTML in `app/templates/admin/`; i messaggi di esito e validazione sono in `app/templates/admin/_messaggi.html`. Python gestisce dati e controlli, senza generare i moduli o definirne i testi.

I contenuti non gestiti dal pannello, come storia, contatti e tariffe della scuola, rimangono nei template pubblici. Le schede “Scopri la Filarmonica” e “I nostri insegnanti” sono invece memorizzate nel database e si modificano dal pannello; etichette e istruzioni dei moduli restano nei template HTML.

### Contenuti del sito

Una nuova installazione parte senza eventi, notizie o album: aggiungili dal pannello. Le tre schede introduttive e le sei schede degli insegnanti già presenti nel sito vengono inserite una sola volta nelle nuove tabelle, per conservarne la presentazione durante il passaggio alla gestione dal pannello. I riavvii non ripristinano le schede eliminate né sovrascrivono le modifiche. Gli altri contenuti esistenti rimangono invariati.

Per trasferire i contenuti su un’altra installazione, conserva il database e le immagini caricate come descritto sotto. Le pagine statiche rimangono nei template in `app/templates/`.

## Dati persistenti e backup

Il percorso predefinito è `instance/` nella cartella del progetto:

- `site.sqlite3`: database dei contenuti, account e sessioni;
- `uploads/`: immagini caricate dal pannello;
- `secret.key`: chiave creata automaticamente al primo avvio, se `SECRET_KEY` non è già configurata nell’ambiente.

Per usare una cartella persistente esterna al checkout, imposta `CMS_INSTANCE_PATH` **prima** di creare l’amministratore o avviare il sito. La cartella deve essere scrivibile dall’utente del servizio. Tutte le istanze dello stesso sito devono utilizzare gli stessi dati e la stessa chiave.

Esempio di backup coerente del database, anche mentre il sito è in esecuzione:

```bash
.venv/bin/python -m flask --app app backup-db /percorso/backup/site-2026-10-06.sqlite3
```

La directory di destinazione deve esistere e il nome del file deve essere nuovo. Imposta lo stesso `CMS_INSTANCE_PATH` del servizio anche quando esegui questo comando. Il backup include i dati già confermati nel journal SQLite; evita di copiare soltanto `site.sqlite3` a mano mentre l’applicazione è attiva.

Copia anche `uploads/` e conserva la chiave delle sessioni o il valore di `SECRET_KEY`. Salva i backup fuori dalla cartella pubblica e dal repository. Per un ripristino, arresta il servizio, conserva una copia dell’istanza corrente e ripristina database e immagini nella cartella persistente prima di riavviarlo. Il backup del database non contiene le fotografie remote di Google Drive.

## Esecuzione in produzione

Il sito richiede un processo Python persistente e un disco scrivibile. Un hosting che serve soltanto file statici non esegue il CMS.

Installa le dipendenze sul server, scegli una cartella persistente e crea l’account amministratore nello stesso ambiente. Per avviare Waitress dietro il reverse proxy Nginx fornito:

```bash
export CMS_INSTANCE_PATH=/var/lib/filarmonica
export CMS_HTTPS=1
export CMS_TRUST_PROXY=1
.venv/bin/python -m flask --app app serve --host 127.0.0.1 --port 8080
```

Il comando Flask `serve` avvia Waitress; host e porta predefiniti sono `127.0.0.1:8080`. Usa un gestore di servizi per mantenerlo attivo e riavviarlo dopo il riavvio del server. Il comando `flask run` è destinato allo sviluppo locale.

Il file `nginx.conf` inoltra le richieste a Waitress e imposta il limite di caricamento e il timeout per la sincronizzazione. Adatta dominio e certificato e configura **HTTPS** sul proxy: il file fornito non installa un certificato e non abilita TLS automaticamente.

`CMS_HTTPS=1` rende sicuri i cookie di sessione per l’uso con HTTPS. Non impostarlo nell’anteprima locale su HTTP, altrimenti il browser non invierà il cookie necessario al login.

Abilita `CMS_TRUST_PROXY=1` soltanto quando Waitress è raggiungibile esclusivamente tramite il proxy controllato, come nella configurazione fornita: Nginx sovrascrive gli header dell’indirizzo client e dello schema. In questo modo il limite dei tentativi di accesso distingue i visitatori reali dietro il proxy.

La cartella persistente deve sopravvivere agli aggiornamenti del codice e alle nuove distribuzioni. SQLite è adatto a questa installazione su un singolo server; non collocare istanze indipendenti su dischi effimeri aspettandoti che condividano i contenuti.

La configurazione di produzione è preparata nel repository; la pubblicazione sul server e la configurazione del dominio restano operazioni da eseguire sull’hosting scelto.

## Verifiche

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m flask --app app check-templates
```

Il primo comando esegue i test Python dell’applicazione e della sincronizzazione Drive, inclusi avvio con database vuoto, gestione dei contenuti e conservazione dei dati ai riavvii. I test usano dati di prova isolati dal database del sito.

`check-templates` compila e verifica i template Jinja; il sito rende le pagine a ogni richiesta. Come gli altri comandi Flask, inizializza il database configurato se è ancora assente.

Per eseguire anche il controllo facoltativo nel browser:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/browser_smoke.py
```

Il controllo avvia un’istanza temporanea separata dal database del sito, verifica le pagine e il percorso di gestione dal login alla pubblicazione e salva le schermate in `test-results/`. Usa Chromium già installato quando disponibile, oppure quello installato da Playwright. Per scegliere un eseguibile diverso imposta `BROWSER_PATH` con il percorso del browser.
