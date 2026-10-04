# Filarmonica Giuseppe Verdi · Lecco

Sito in HTML e CSS. Tutti i contenuti sono nei file di `public/`: nessun database o pannello admin. Un piccolo script condiviso gestisce la visualizzazione e il download delle fotografie nelle gallerie.

## Aprire il sito

Per aprire il sito senza server, esegui `npm run build` e apri **`dist/index.html`** nel browser. Le pagine generate includono header e footer e funzionano anche senza connessione; le fotografie degli album vengono caricate da Google Drive e richiedono Internet.

Per un'anteprima locale con Node.js 22 o successivo:

```bash
npm run dev
```

Sul computer apri http://127.0.0.1:8080. Sul telefono collegato alla stessa rete Wi-Fi, apri l’indirizzo indicato come `Nella rete locale` nel terminale, completo di `http://` e porta `8080`. Lascia il server acceso mentre navighi dal telefono.

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
| Album fotografici e relativi collegamenti | `public/foto.html` |
| Fotografie di ciascun album | `public/foto/*.html` |
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

Le pagine **La Filarmonica** e **Scuola allievi** raccolgono i contenuti in sezioni. L’indice iniziale usa collegamenti come `href="#storia"`, che puntano alla sezione con `id="storia"`. Per aggiungere una sezione, copia un blocco `<section class="section content-block">`, scegli un `id` unico e aggiungi il relativo link nell’indice. I vecchi indirizzi sono elencati in `public/_redirects` e rimandano alle sezioni corrispondenti.

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

In `public/foto.html`, ogni album è un blocco `<article class="album-card">`. Le copertine sono in `public/assets/foto/`: modifica `src` per cambiare la foto e `object-position` per regolare il ritaglio. L’attributo `href` apre la pagina dell’album nella cartella `foto/`. Per aggiungerne uno, copia un blocco nell’anno corrispondente e aggiorna titolo, mese, luogo, credito e `aria-label`. Per aggiungere un anno, copia una sezione `album-year`, aggiorna il titolo e i relativi identificatori e inserisci il collegamento nell’indice iniziale, nascosto sui telefoni.

Ogni file di `public/foto/` contiene le proprie fotografie come normali elementi HTML. Per aggiungere una foto, copia un link `<a class="gallery-photo">` e sostituisci l’ID di Google Drive sia in `href` (immagine grande, `=s1600`) sia nel `src` dell’immagine (miniatura, `=s640`). Aggiorna `alt` e `aria-label`. Le immagini devono essere condivise pubblicamente su Drive; puoi anche usare immagini locali sostituendo entrambi i percorsi. Il visualizzatore usa `public/gallery.js`, senza librerie esterne: supporta i pulsanti avanti/indietro, le frecce della tastiera e il tasto Esc per chiudere. L’icona di download accanto alla chiusura scarica il file originale da Drive; per indicare un originale diverso, aggiungi `data-original="percorso-del-file"` al link della foto.

Per aggiungere una pagina, copia un file HTML dalla stessa cartella e mantieni i due commenti `include`. Per modificare il menu, aggiorna solo `public/partials/header.html`, nelle versioni desktop e mobile. Per modificare il footer, aggiorna solo `public/partials/footer.html`. Nei file condivisi scrivi i percorsi rispetto a `public/`, per esempio `index.html` e `assets/Logo_filarmonica.svg`: i percorsi delle pagine in sottocartelle e l’indicazione della pagina corrente vengono adattati automaticamente.

La pagina contatti usa collegamenti email e telefono. Il pulsante email apre il programma di posta del visitatore; il sito non raccoglie messaggi.

## Pubblicare

Genera il sito e carica il **contenuto** di `dist/` su un qualsiasi hosting statico. L'homepage deve essere `index.html` nella cartella pubblica dell'hosting.

```bash
npm run build
```

Questo comando copia i file pubblici in `dist/` e inserisce header e footer nelle pagine, generando HTML completo. Non modificare direttamente `dist/`: viene rigenerata a ogni build. `public/_redirects` mantiene i vecchi indirizzi senza `.html` sugli hosting che supportano questo file e nel server di anteprima. Su altri hosting, configura i redirect equivalenti se ti servono i vecchi link.

Le precedenti credenziali in `.dev.vars` e gli archivi locali in `.wrangler/`, se presenti, non sono più usati e non vengono copiati in `dist/`.
