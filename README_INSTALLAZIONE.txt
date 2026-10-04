JARVIS SECRETARY V2

CONTENUTO
- app.py
- requirements.txt

FUNZIONI PRINCIPALI
- Allievi e scheda dati
- Pacchetti lezioni
- Lezioni, calendario, completate/annullate
- Pagamenti e residuo economico
- Serate di ballo
- Attività/promemoria
- Bozze Instagram, Facebook e sito
- Jarvis AI con conferma obbligatoria prima delle modifiche
- Backup JSON
- PIN opzionale

INSTALLAZIONE SU GITHUB / RENDER
1. Nel repository Jarvis sostituisci app.py con questo app.py.
2. Sostituisci requirements.txt con quello incluso.
3. Commit changes.
4. Render: Manual Deploy -> Deploy latest commit.

VARIABILI RENDER CONSIGLIATE
OPENAI_API_KEY = la tua chiave già configurata
JARVIS_ADMIN_PIN = un PIN scelto da te (esempio: 4-8 cifre)
JARVIS_SECRET_KEY = una stringa lunga casuale
JARVIS_DB_PATH = percorso del database persistente

IMPORTANTE SULL'ARCHIVIO
Se JARVIS_DB_PATH non è configurato su uno storage persistente, il database locale può andare perso a un redeploy/restart del servizio.
Per questo la UI mostra un avviso finché non configuriamo lo storage persistente.
Non inserire ancora dati reali importanti finché non completiamo quel passaggio.

PUBBLICAZIONE SOCIAL
La V2 genera e gestisce le bozze per Instagram, Facebook e sito.
La pubblicazione automatica reale verrà collegata in una fase successiva agli account Meta e alle API del sito.
