# Filarmonica Giuseppe Verdi · Lecco

Sito in HTML e CSS. I contenuti sono nei file di `public/` e `data/`: nessun database o pannello admin. Un piccolo script condiviso gestisce la visualizzazione e il download delle fotografie nelle gallerie.

## Aprire il sito

Per aprire il sito senza server, esegui `npm run build` e apri **`dist/index.html`** nel browser. Le pagine generate includono header e footer e funzionano anche senza connessione; le fotografie degli album vengono caricate da Google Drive e richiedono Internet.

Per un'anteprima locale con Node.js 22 o successivo:

```bash
npm run dev
```

Sul computer apri http://127.0.0.1:8080. Sul telefono collegato alla stessa rete Wi-Fi, usa l’IP locale del computer, completo di `http://` e porta `8080`, per esempio `http://192.168.1.59:8080`. Puoi trovare l’IP nelle impostazioni di rete del computer. Lascia il server acceso mentre navighi dal telefono.

Dopo una modifica, salva il file e aggiorna la pagina. Arresta il server con `Ctrl+C`.

Il server accetta già connessioni dalla rete locale. Per cambiare porta o limitarlo al solo computer:

```bash
npm run dev -- --port 3000
npm run dev -- --ip 127.0.0.1
```

## Dove modificare i contenuti

| Contenuto | File |
| --- | --- |
| Homepage, riepilogo eventi, notizia in evidenza | `public/index.html` |
| Calendario completo | `public/prossimi-eventi.html` |
| Elenco delle notizie | `public/blog.html` |
| Testo di ogni notizia | `public/blog/*.html` |
| Titoli, date, descrizioni, cartelle Drive e copertine degli album | `data/albums.json` |
| Impaginazione della pagina Foto e delle gallerie | `templates/foto.html`, `templates/album.html` |
| Visualizzatore delle fotografie | `public/gallery.js` |
| Storia, direttivo, maestro e servizi | `public/la-filarmonica.html` |
| Scuola, insegnanti e Pronti, settembre, via! | `public/scuola-allievi.html` |
| Donazioni e contatti | `public/sostienici.html`, `public/contatti.html` |
| Colori, caratteri, spazi e layout mobile | `public/styles.css` |
| Fotografie | `public/assets/` |
| Header e menu desktop/mobile | `public/partials/header.html` |
| Footer condiviso | `public/partials/footer.html` |

Ogni pagina richiama le parti condivise con `<!-- include: header -->` e `<!-- include: footer -->`. Il server locale e la build inseriscono automaticamente i due file di `public/partials/`. Cerca il commento `CONTENUTO` per trovare la parte da modificare. I colori principali sono raccolti nelle variabili all’inizio di `public/styles.css`.

I testi sono dentro tag come `<h1>`, `<h2>` e `<p>`; i collegamenti sono nell'attributo `href` e le immagini nell'attributo `src`.

Le pagine **La Filarmonica** e **Scuola allievi** raccolgono i contenuti in sezioni. L’indice iniziale usa collegamenti come `href="#storia"`, che puntano alla sezione con `id="storia"`. Per aggiungere una sezione, copia un blocco `<section class="section content-block">`, scegli un `id` unico e aggiungi il relativo link nell’indice. Le sezioni di contenuto direttamente dentro `<main>` con classe `section` alternano automaticamente sfondo chiaro e più scuro, iniziando dal chiaro. Il banner iniziale è escluso dal conteggio; non servono classi di colore manuali. I vecchi indirizzi sono elencati in `public/_redirects` e rimandano alle sezioni corrispondenti.

### Aggiungere un evento

In `public/prossimi-eventi.html`, copia un blocco `<article class="event-card" ...>...</article>` e modifica data, titolo, luogo e descrizione. Assegna un `id` diverso e disponi gli eventi nell'ordine desiderato. La data è divisa in `date-number` (giorno) e `date-month` (mese e anno); per una data ancora da definire puoi scrivere il mese abbreviato al posto del giorno.

```html
<article class="event-card" id="nome-evento">
  <div class="event-date">
    <span class="date-number">08</span>
    <span class="date-month">Novembre<br />2026</span>
  </div>
  <div>
    <h2>Titolo del concerto</h2>
    <p><strong>Luogo</strong></p>
    <p>Orario e informazioni utili.</p>
  </div>
</article>
```

Aggiorna anche i tre appuntamenti in `public/index.html`: il riepilogo è scritto a mano, quindi non si aggiorna automaticamente.

### Aggiungere una notizia

1. Copia una pagina di `public/blog/`, per esempio in `public/blog/nuovo-concerto.html`.
2. Cambia titolo, descrizione nel `<head>`, data, foto e testo dentro `<main>`.
3. Copia un blocco `<article>` in `public/blog.html` e collega la nuova pagina con `href="blog/nuovo-concerto.html"`.
4. Se vuoi metterla in evidenza, aggiorna anche il riquadro in `public/index.html`.

### Cambiare una foto o aggiungere una pagina

Metti la foto in `public/assets/` e modifica `src` e `alt` nell'HTML. Nelle pagine principali usa `src="assets/foto.jpg"`; nelle notizie dentro `blog/` usa `src="../assets/foto.jpg"`.

### Album fotografici automatici

La pagina **Foto**, il suo indice per anno e tutte le gallerie sono generati da `data/albums.json`. Aggiungi un elemento all’array `albums`:

```json
{
  "slug": "concerto-autunno-2026",
  "title": "Concerto d’autunno",
  "date": "2026-10",
  "description": "Lecco · Foto di Nome Cognome",
  "folder": "",
  "cover": ""
}
```

- `slug`: nome univoco usato nell’indirizzo `foto/concerto-autunno-2026.html`. Usa lettere minuscole, numeri e trattini. Mantienilo invariato per conservare il collegamento.
- `date`: mese e anno nel formato `YYYY-MM`. L’elenco mostra automaticamente gli album più recenti per primi.
- `folder`: link della cartella pubblica Google Drive, per esempio `https://drive.google.com/drive/folders/ID_CARTELLA`. Puoi lasciarlo vuoto per gli album ancora da completare. La galleria include le immagini della cartella e delle sue sottocartelle, ordinate per nome; i video sono esclusi e le fotografie duplicate compaiono una volta sola.
- `cover`: collegamento separato alla foto per la pagina Foto. Accetta un link pubblico Google Drive a un singolo file, un URL HTTPS diretto a un’immagine, oppure un percorso locale come `assets/foto/copertina.jpg`. Una stringa vuota mostra una copertina provvisoria.
- `coverAlt` e `coverPosition` sono facoltativi: testo alternativo e ritaglio, per esempio `"50% 30%"`.

Con `folder` vuoto, l’album mostra «Le fotografie saranno disponibili a breve». Inserendo un link, la galleria viene generata dalle fotografie della cartella.

Con `npm run dev`, salva il JSON: il browser si aggiorna automaticamente. In alternativa esegui `npm run build`: vengono create sia `dist/foto.html` sia le pagine in `dist/foto/`. Non devi creare HTML o aggiornare l’indice a mano. Titolo e descrizione sono testo semplice, senza tag HTML. Per cambiare l’impaginazione modifica i due file in `templates/`.

Le cartelle e le immagini devono essere accessibili a chiunque abbia il link. Il generatore legge la vista pubblica di Drive; per gli elenchi oltre i primi 50 elementi usa la vista pubblica incorporabile completa. Se le viste pubbliche non sono leggibili, puoi configurare la variabile d’ambiente `GOOGLE_DRIVE_API_KEY` con una chiave di un progetto Google Cloud con Drive API abilitata. La chiave viene usata solo durante la generazione, non è inclusa nel sito. Con l’API il generatore segue tutte le pagine dell’elenco. Un errore di accesso interrompe la build prima di sostituire la precedente, evitando di pubblicare un album incompleto. Vedi la [documentazione Google sulla ricerca dei file](https://developers.google.com/workspace/drive/api/guides/search-files).

Il server di anteprima osserva `data/albums.json`, anche quando l’editor lo salva sostituendo il file. Le pagine aperte si ricaricano automaticamente. Questo aggiornamento è attivo solo con `npm run dev`; i file statici pubblicati richiedono una nuova build. In anteprima l’elenco di ciascuna cartella viene tenuto in memoria per un minuto. Sul sito pubblicato, per aggiungere o togliere foto dalla galleria occorre rigenerare e ricaricare `dist/`. Le fotografie rimangono su Drive e richiedono Internet. Il visualizzatore mantiene ingrandimento, navigazione con tastiera e download dell’originale.

Per aggiungere una pagina, copia un file HTML dalla stessa cartella e mantieni i due commenti `include`. Per modificare il menu, aggiorna solo `public/partials/header.html`, nelle versioni desktop e mobile. Per modificare il footer, aggiorna solo `public/partials/footer.html`. Nei file condivisi scrivi i percorsi rispetto a `public/`, per esempio `index.html` e `assets/Logo_filarmonica.svg`: i percorsi delle pagine in sottocartelle e l’indicazione della pagina corrente vengono adattati automaticamente.

La pagina contatti usa collegamenti email e telefono. Il pulsante email apre il programma di posta del visitatore; il sito non raccoglie messaggi.

## Pubblicare

Genera il sito e carica il **contenuto** di `dist/` su un qualsiasi hosting statico. L'homepage deve essere `index.html` nella cartella pubblica dell'hosting.

```bash
npm run build
```

Questo comando sincronizza i file pubblici in `dist/`, genera la pagina Foto e le gallerie dal JSON e inserisce header e footer nelle pagine, generando HTML completo. Scrive soltanto i file il cui contenuto è cambiato e rimuove quelli che non fanno più parte del sito. Non modificare direttamente `dist/`: la build gestisce tutto il suo contenuto. `public/_redirects` mantiene i vecchi indirizzi senza `.html` sugli hosting che supportano questo file e nel server di anteprima. Su altri hosting, configura i redirect equivalenti se ti servono i vecchi link.

### Build più veloci e cache di Drive

La build normale controlla tutte le cartelle Drive, incluse le sottocartelle, con un massimo di sei richieste contemporanee. Gli elenchi sono salvati in `.cache/drive/` e aggiornati soltanto quando cambiano nomi, file o sottocartelle. Una cartella condivisa da più album viene controllata una sola volta nella stessa build. Anche se la cartella principale è invariata, le sottocartelle vengono controllate per rilevare aggiunte e rimozioni.

Le pagine pubbliche di Drive non espongono un indicatore affidabile di modifica: il controllo normale deve comunque leggere gli elenchi. La cache non significa che la build normale possa sapere se una cartella è cambiata senza contattare Drive. I file delle fotografie non vengono scaricati durante la build.

Quando cambi solo testi, HTML o CSS, puoi riutilizzare gli elenchi già salvati:

```bash
npm run build -- --cached-drive
```

Questa modalità non contatta Drive per le cartelle presenti nella cache. Le cartelle nuove o prive di cache vengono scaricate normalmente. **Le modifiche fatte su Drive dopo l’ultimo controllo non sono rilevate in questa modalità**: per importarle esegui `npm run build` senza opzioni, soprattutto prima di pubblicare.

La cache è locale, esclusa da Git e dalla pubblicazione; non contiene la chiave API. Puoi cancellare `.cache/drive/` per ricostruirla. Gli errori di accesso nella build normale interrompono la generazione prima di aggiornare `dist/`, senza usare silenziosamente dati vecchi. Il riepilogo finale mostra quante cartelle sono state verificate o lette dalla cache e quanti file sono stati aggiornati.

Le precedenti credenziali in `.dev.vars` e gli archivi locali in `.wrangler/`, se presenti, non sono più usati e non vengono copiati in `dist/`.

I link ricevuti che non espongono un elenco pubblico di fotografie sono conservati in `data/unavailable-folders.json` per completarli in seguito. Questo file è un promemoria e non viene usato per generare le gallerie.
