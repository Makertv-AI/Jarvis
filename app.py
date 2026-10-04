import os
import json
import sqlite3
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, jsonify, request, render_template_string,
    session, redirect, url_for, send_file
)
from openai import OpenAI

APP_TITLE = "Jarvis · Segreteria"
DB_PATH = os.environ.get("JARVIS_DB_PATH", os.path.join(os.path.dirname(__file__), "jarvis.db"))
ADMIN_PIN = os.environ.get("JARVIS_ADMIN_PIN", "").strip()

app = Flask(__name__)
app.secret_key = os.environ.get(
    "JARVIS_SECRET_KEY",
    os.environ.get("OPENAI_API_KEY", "jarvis-local-secret-change-me")
)

os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def today_iso():
    return datetime.now().date().isoformat()


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    con = get_db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        level TEXT DEFAULT '',
        lesson_type TEXT DEFAULT 'Privata',
        preferred_days TEXT DEFAULT '',
        goals TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        total_lessons INTEGER NOT NULL DEFAULT 0,
        duration_min INTEGER NOT NULL DEFAULT 60,
        price_total REAL NOT NULL DEFAULT 0,
        start_date TEXT DEFAULT '',
        expiry_date TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS lessons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        package_id INTEGER,
        starts_at TEXT NOT NULL,
        duration_min INTEGER NOT NULL DEFAULT 60,
        location TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'scheduled',
        kind TEXT NOT NULL DEFAULT 'standard',
        counts_package INTEGER NOT NULL DEFAULT 1,
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY(package_id) REFERENCES packages(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        package_id INTEGER,
        amount REAL NOT NULL,
        paid_at TEXT NOT NULL,
        method TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY(package_id) REFERENCES packages(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        starts_at TEXT NOT NULL,
        ends_at TEXT DEFAULT '',
        venue TEXT DEFAULT '',
        city TEXT DEFAULT '',
        address TEXT DEFAULT '',
        price_text TEXT DEFAULT '',
        description TEXT DEFAULT '',
        music TEXT DEFAULT '',
        dress_code TEXT DEFAULT '',
        contact TEXT DEFAULT '',
        image_url TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'planned',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        due_at TEXT DEFAULT '',
        category TEXT DEFAULT 'generale',
        priority TEXT DEFAULT 'media',
        status TEXT NOT NULL DEFAULT 'open',
        notes TEXT DEFAULT '',
        related_type TEXT DEFAULT '',
        related_id INTEGER,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS publications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER,
        channel TEXT NOT NULL,
        caption TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        scheduled_at TEXT DEFAULT '',
        published_at TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)
    con.commit()
    con.close()


init_db()


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if ADMIN_PIN and not session.get("jarvis_auth"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Autenticazione richiesta"}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def rowdict(row):
    return dict(row) if row else None


def log_activity(text):
    con = get_db()
    con.execute("INSERT INTO activity(text, created_at) VALUES(?,?)", (text, now_iso()))
    con.commit()
    con.close()


def student_summary(con, student_id):
    s = con.execute("SELECT * FROM students WHERE id=?", (student_id,)).fetchone()
    if not s:
        return None

    pkg = con.execute("""
        SELECT * FROM packages
        WHERE student_id=? AND active=1
        ORDER BY id DESC LIMIT 1
    """, (student_id,)).fetchone()

    out = dict(s)
    out["package"] = dict(pkg) if pkg else None

    if pkg:
        done = con.execute("""
            SELECT COUNT(*) AS n FROM lessons
            WHERE student_id=? AND package_id=? AND status='completed' AND counts_package=1
        """, (student_id, pkg["id"])).fetchone()["n"]
        paid = con.execute("""
            SELECT COALESCE(SUM(amount),0) AS total FROM payments
            WHERE student_id=? AND package_id=?
        """, (student_id, pkg["id"])).fetchone()["total"]
        out["done_lessons"] = done
        out["remaining_lessons"] = max(0, pkg["total_lessons"] - done)
        out["paid"] = float(paid or 0)
        out["due"] = max(0.0, float(pkg["price_total"] or 0) - float(paid or 0))
    else:
        out["done_lessons"] = 0
        out["remaining_lessons"] = 0
        out["paid"] = 0.0
        out["due"] = 0.0

    return out


LOGIN_PAGE = """
<!doctype html>
<html lang="it"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jarvis · Accesso</title>
<style>
body{margin:0;background:#07111f;color:white;font-family:Arial,sans-serif;display:grid;place-items:center;min-height:100vh}
.card{width:min(420px,90vw);background:#101b2d;padding:24px;border-radius:18px;border:1px solid #263750}
input,button{width:100%;box-sizing:border-box;padding:14px;border-radius:11px;font-size:17px;margin-top:10px}
input{background:#081524;color:white;border:1px solid #30445f}button{background:#2f6fed;color:white;border:0;font-weight:700}
.err{color:#ff9fa8;margin-top:8px}
</style></head><body>
<div class="card"><h1>Jarvis</h1><p>Inserisci il PIN della segreteria.</p>
<form method="post"><input name="pin" type="password" inputmode="numeric" autocomplete="current-password" autofocus>
<button type="submit">Entra</button></form>
{% if error %}<div class="err">{{error}}</div>{% endif %}
</div></body></html>
"""

PAGE = r"""
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#07111f">
<title>Jarvis · Segreteria</title>
<style>
:root{
  --bg:#07111f;
  --bg2:#0b1628;
  --panel:rgba(18,31,51,.88);
  --panel-solid:#111f34;
  --panel2:#182a44;
  --line:rgba(130,160,200,.17);
  --blue:#4f7cff;
  --blue2:#6d5dfc;
  --green:#20b87a;
  --red:#e05c68;
  --amber:#d79d3d;
  --text:#f7f9fd;
  --muted:#9aa9bf;
  --shadow:0 18px 45px rgba(0,0,0,.22);
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{
  margin:0;
  min-height:100vh;
  color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Arial,sans-serif;
  background:
    radial-gradient(circle at 10% -10%, rgba(79,124,255,.22), transparent 30%),
    radial-gradient(circle at 95% 5%, rgba(109,93,252,.16), transparent 26%),
    linear-gradient(180deg,#081221 0%,#07111f 45%,#060d18 100%);
}
.app{max-width:980px;margin:auto;padding:18px 14px 116px}
.top{
  display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:8px 2px 12px
}
.brand{display:flex;align-items:center;gap:12px}
.logo{
  width:46px;height:46px;border-radius:15px;display:grid;place-items:center;
  font-size:21px;font-weight:900;
  background:linear-gradient(145deg,var(--blue),var(--blue2));
  box-shadow:0 10px 28px rgba(79,124,255,.32)
}
.top h1{margin:0;font-size:27px;letter-spacing:-.6px}
.sub{font-size:12px;color:var(--muted);margin-top:2px}
.statusline{display:flex;align-items:center;gap:6px;margin-top:4px;font-size:11px;color:#aebbd0}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px rgba(32,184,122,.10)}
.tabs{
  display:flex;gap:8px;overflow:auto;padding:8px 0 8px;
  position:sticky;top:0;z-index:20;
  background:linear-gradient(180deg,rgba(7,17,31,.98),rgba(7,17,31,.90) 78%,transparent);
  backdrop-filter:blur(12px);
  scrollbar-width:none
}
.tabs::-webkit-scrollbar{display:none}
button{
  border:0;border-radius:13px;padding:11px 14px;
  background:linear-gradient(135deg,var(--blue),#3f69dd);
  color:white;font-size:14px;font-weight:750;cursor:pointer;
  box-shadow:0 6px 16px rgba(0,0,0,.12);
  transition:transform .12s ease,filter .12s ease,background .12s ease
}
button:active{transform:scale(.97)}
button.secondary,.tab{
  background:rgba(23,41,66,.92);
  border:1px solid var(--line);
  box-shadow:none
}
button.ok{background:linear-gradient(135deg,#1caf74,#13865a)}
button.danger{background:linear-gradient(135deg,#e05c68,#b84250)}
button.warn{background:linear-gradient(135deg,#d79d3d,#ad7622)}
.tab{white-space:nowrap;color:#b8c5d7}
.tab.active{
  color:white;
  background:linear-gradient(135deg,rgba(79,124,255,.98),rgba(109,93,252,.92));
  border-color:transparent;
  box-shadow:0 8px 24px rgba(79,124,255,.24)
}
.view{display:none}.view.active{display:block}
.hero{
  position:relative;overflow:hidden;
  background:linear-gradient(145deg,rgba(37,62,98,.95),rgba(21,38,66,.96));
  border:1px solid rgba(122,157,208,.17);
  border-radius:24px;padding:18px;margin:10px 0 13px;
  box-shadow:var(--shadow)
}
.hero:after{
  content:"";position:absolute;width:180px;height:180px;border-radius:50%;
  right:-75px;top:-85px;background:rgba(83,117,255,.16)
}
.hero h2{margin:0 0 4px;font-size:22px}.hero p{margin:0;color:#b7c4d7;font-size:13px;max-width:560px}
.quick{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:14px}
.quick button{
  min-height:58px;background:rgba(10,23,40,.62);border:1px solid var(--line);
  box-shadow:none;padding:8px;font-size:12px
}
.quick .qi{display:block;font-size:20px;margin-bottom:3px}
.card{
  background:linear-gradient(145deg,rgba(17,31,52,.94),rgba(13,25,43,.94));
  border:1px solid var(--line);border-radius:20px;padding:15px;margin:12px 0;
  box-shadow:0 12px 28px rgba(0,0,0,.14);
  backdrop-filter:blur(10px)
}
.card>b:first-child,.sectionTitle{font-size:15px;letter-spacing:.1px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}
.stat{
  position:relative;min-height:104px;overflow:hidden;
  background:linear-gradient(145deg,rgba(25,43,70,.98),rgba(16,30,50,.98));
  border:1px solid var(--line);border-radius:18px;padding:14px;
  box-shadow:0 10px 22px rgba(0,0,0,.13)
}
.stat:after{
  position:absolute;right:12px;top:11px;width:30px;height:30px;
  border-radius:10px;display:grid;place-items:center;font-size:15px;
  background:rgba(255,255,255,.06)
}
.stat:nth-child(1):after{content:"👥"}
.stat:nth-child(2):after{content:"📅"}
.stat:nth-child(3):after{content:"🎟️"}
.stat:nth-child(4):after{content:"€"}
.stat:nth-child(4){background:linear-gradient(145deg,rgba(62,37,52,.98),rgba(31,28,47,.98))}
.stat b{display:block;font-size:24px;margin-top:24px;letter-spacing:-.5px}
.stat span,.small{font-size:12px;color:var(--muted)}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.grow{flex:1}.stack{display:grid;gap:7px}
input,select,textarea{
  width:100%;background:rgba(7,19,34,.92);color:white;
  border:1px solid rgba(128,157,198,.22);border-radius:13px;
  padding:12px;font-size:15px;outline:none;transition:border .15s,box-shadow .15s
}
input:focus,select:focus,textarea:focus{
  border-color:rgba(79,124,255,.72);
  box-shadow:0 0 0 3px rgba(79,124,255,.10)
}
textarea{min-height:82px;resize:vertical}
.item{
  background:rgba(8,21,37,.48);border:1px solid rgba(125,153,190,.10);
  padding:12px;border-radius:15px;margin-top:9px
}
.item h3{margin:0 0 5px;font-size:16px}
.pill{
  display:inline-block;padding:5px 9px;border-radius:999px;
  background:#1a2c47;border:1px solid rgba(142,169,205,.10);
  font-size:11px;margin:2px 3px 2px 0;color:#cad4e2
}
.good{background:#123d31!important;color:#98e3c1!important}
.bad{background:#48232b!important;color:#ffb8c0!important}
.amber{background:#473718!important;color:#ffd890!important}
.chat{
  height:330px;overflow:auto;
  background:linear-gradient(180deg,rgba(6,18,32,.96),rgba(9,23,40,.96));
  border:1px solid var(--line);border-radius:18px;padding:11px
}
.msg{padding:11px 12px;border-radius:15px;margin:8px 0;white-space:pre-wrap;line-height:1.42}
.me{background:linear-gradient(135deg,#294f92,#2d4472);margin-left:12%}
.ai{background:#152840;margin-right:8%}
.confirm{
  border:1px solid rgba(215,157,61,.44);
  background:linear-gradient(145deg,rgba(54,43,21,.97),rgba(39,31,18,.97))
}
.empty{text-align:center;color:var(--muted);padding:24px}
.bottom{
  position:fixed;bottom:0;left:0;right:0;z-index:30;
  background:rgba(7,17,31,.88);border-top:1px solid var(--line);
  padding:9px 10px calc(9px + env(safe-area-inset-bottom));
  backdrop-filter:blur(18px)
}
.bottomin{max-width:980px;margin:auto;display:flex;gap:8px}
.bottomin .grow{
  background:linear-gradient(135deg,var(--blue),var(--blue2));
  box-shadow:0 8px 24px rgba(79,124,255,.28)
}
label{font-size:11px;color:#aebbd0;display:block;margin:7px 0 4px 2px;font-weight:650}
.two{display:grid;grid-template-columns:1fr 1fr;gap:9px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
.notice{
  padding:11px 12px;border-radius:14px;
  background:rgba(79,54,18,.72);border:1px solid rgba(218,161,61,.28);
  color:#ffe1a8;font-size:12px;margin:10px 0
}
#mic.listening{background:var(--red)}#voice.on{background:var(--green)}
.softTitle{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:8px}
.softTitle span{font-size:12px;color:var(--muted)}
@media(min-width:700px){
  .grid{grid-template-columns:repeat(4,1fr)}
  .stat{min-height:118px}.stat b{font-size:27px}
}
@media(max-width:560px){
  .two,.three{grid-template-columns:1fr}
  .quick{grid-template-columns:repeat(2,1fr)}
  .top h1{font-size:25px}
  .app{padding-left:12px;padding-right:12px}
}
</style>
</head>
<body>
<div class="app">
  <div class="top">
    <div class="brand">
      <div class="logo">J</div>
      <div>
        <h1>Jarvis</h1>
        <div class="sub">La tua segretaria personale</div>
        <div class="statusline"><span class="dot"></span> Online · Lezioni e serate</div>
      </div>
    </div>
    <div class="row"><button id="voice" class="secondary" onclick="toggleVoice()">🔊 Voce</button><button class="secondary" onclick="logout()">🔒</button></div>
  </div>

  <div id="storageNotice"></div>

  <div class="tabs">
    <button class="tab active" onclick="show('dashboard',this)">🏠 Oggi</button>
    <button class="tab" onclick="show('calendar',this)">📅 Calendario</button>
    <button class="tab" onclick="show('students',this)">👥 Allievi</button>
    <button class="tab" onclick="show('events',this)">💃 Serate</button>
    <button class="tab" onclick="show('tasks',this)">✅ Attività</button>
    <button class="tab" onclick="show('publish',this)">📣 Pubblicazioni</button>
    <button class="tab" onclick="show('assistant',this)">✨ Jarvis</button>
  </div>

  <section id="dashboard" class="view active">
    <div class="hero">
      <h2>La tua giornata, in un colpo d’occhio</h2>
      <p>Lezioni, allievi, incassi, serate e promozione: Jarvis tiene tutto ordinato e ti chiede conferma prima di modificare qualcosa.</p>
      <div class="quick">
        <button onclick="show('calendar',document.querySelectorAll('.tab')[1])"><span class="qi">＋</span>Lezione</button>
        <button onclick="show('students',document.querySelectorAll('.tab')[2]);toggleStudentForm()"><span class="qi">👤</span>Allievo</button>
        <button onclick="show('events',document.querySelectorAll('.tab')[3])"><span class="qi">💃</span>Serata</button>
        <button onclick="openJarvis()"><span class="qi">✨</span>Chiedi a Jarvis</button>
      </div>
    </div>
    <div id="stats" class="grid"></div>
    <div class="card"><div class="softTitle"><b>Agenda prossime 48 ore</b><span>prossimi impegni</span></div><div id="agenda48"></div></div>
    <div class="card"><div class="softTitle"><b>Da controllare</b><span>priorità</span></div><div id="alerts"></div></div>
    <div class="card"><div class="softTitle"><b>Ultime attività</b><span>registro</span></div><div id="activity"></div></div>
  </section>

  <section id="calendar" class="view">
    <div class="card">
      <div class="row"><b class="grow">Nuova lezione</b><button class="secondary" onclick="loadCalendar()">Aggiorna</button></div>
      <div class="two">
        <div><label>Allievo</label><select id="lessonStudent"></select></div>
        <div><label>Data e ora</label><input id="lessonStart" type="datetime-local"></div>
      </div>
      <div class="three">
        <div><label>Durata (min)</label><input id="lessonDuration" type="number" value="60" min="15" step="15"></div>
        <div><label>Luogo</label><input id="lessonLocation" placeholder="Sala / studio / domicilio"></div>
        <div><label>Tipo</label><select id="lessonKind"><option value="standard">Normale</option><option value="recovery">Recupero</option><option value="trial">Prova</option><option value="free">Omaggio</option></select></div>
      </div>
      <label>Note</label><input id="lessonNotes" placeholder="Note lezione">
      <button onclick="prepareLesson()">Prepara lezione</button>
    </div>
    <div id="lessonConfirm"></div>
    <div class="card"><b>Prossimi appuntamenti</b><div id="calendarList"></div></div>
  </section>

  <section id="students" class="view">
    <div class="card">
      <div class="row"><input class="grow" id="studentSearch" placeholder="Cerca allievo..." oninput="renderStudents()"><button onclick="toggleStudentForm()">+ Allievo</button></div>
    </div>
    <div id="studentForm" class="card" style="display:none">
      <b>Nuovo allievo e pacchetto</b>
      <div class="two"><input id="sName" placeholder="Nome e cognome"><input id="sPhone" placeholder="Telefono"></div>
      <div class="two"><input id="sEmail" placeholder="Email"><input id="sLevel" placeholder="Livello"></div>
      <div class="two"><input id="sType" placeholder="Tipo lezione (es. salsa privata)"><input id="sDays" placeholder="Giorni/orari preferiti"></div>
      <textarea id="sGoals" placeholder="Obiettivi"></textarea>
      <textarea id="sNotes" placeholder="Note"></textarea>
      <hr style="border-color:#263c58">
      <div class="three"><input id="pTotal" type="number" placeholder="Lezioni pacchetto"><input id="pDuration" type="number" value="60" placeholder="Minuti"><input id="pPrice" type="number" step=".01" placeholder="Prezzo totale €"></div>
      <div class="two"><input id="pStart" type="date"><input id="pExpiry" type="date"></div>
      <div class="two"><input id="pPaid" type="number" step=".01" placeholder="Acconto / già pagato €"><input id="pMethod" placeholder="Metodo pagamento"></div>
      <button onclick="prepareStudent()">Prepara inserimento</button>
    </div>
    <div id="studentConfirm"></div>
    <div class="card"><div id="studentList"></div></div>
  </section>

  <section id="events" class="view">
    <div class="card">
      <b>Nuova serata di ballo</b>
      <input id="eTitle" placeholder="Titolo serata">
      <div class="two"><input id="eStart" type="datetime-local"><input id="eEnd" type="datetime-local"></div>
      <div class="two"><input id="eVenue" placeholder="Locale / venue"><input id="eCity" placeholder="Città"></div>
      <input id="eAddress" placeholder="Indirizzo">
      <div class="two"><input id="ePrice" placeholder="Ingresso / prezzo"><input id="eMusic" placeholder="Musica / DJ / orchestra"></div>
      <div class="two"><input id="eDress" placeholder="Dress code"><input id="eContact" placeholder="Contatto / prenotazioni"></div>
      <textarea id="eDescription" placeholder="Descrizione della serata"></textarea>
      <input id="eImage" placeholder="URL immagine/locandina (opzionale)">
      <button onclick="prepareEvent()">Prepara serata</button>
    </div>
    <div id="eventConfirm"></div>
    <div class="card"><b>Serate programmate</b><div id="eventList"></div></div>
  </section>

  <section id="tasks" class="view">
    <div class="card">
      <b>Nuova attività / promemoria</b>
      <input id="tTitle" placeholder="Cosa devo fare?">
      <div class="three"><input id="tDue" type="datetime-local"><select id="tCategory"><option>generale</option><option>lezioni</option><option>serate</option><option>social</option><option>sito</option><option>amministrazione</option></select><select id="tPriority"><option value="bassa">Bassa</option><option value="media" selected>Media</option><option value="alta">Alta</option></select></div>
      <textarea id="tNotes" placeholder="Note"></textarea>
      <button onclick="prepareTask()">Prepara attività</button>
    </div>
    <div id="taskConfirm"></div>
    <div class="card"><div id="taskList"></div></div>
  </section>

  <section id="publish" class="view">
    <div class="notice">Instagram, Facebook e sito sono già previsti nel flusso. Per ora Jarvis prepara le bozze e le mette in coda; la pubblicazione reale verrà collegata agli account Meta e al sito quando configureremo le credenziali/API.</div>
    <div class="card">
      <b>Crea contenuti da una serata</b>
      <select id="pubEvent"></select>
      <button onclick="generatePublications()">Genera bozze con Jarvis</button>
    </div>
    <div class="card"><b>Coda pubblicazioni</b><div id="publicationList"></div></div>
  </section>

  <section id="assistant" class="view">
    <div class="card">
      <div id="chat" class="chat"><div class="msg ai">Sono pronta. Posso gestire allievi, lezioni, pagamenti, agenda, attività, serate e bozze social. Le modifiche richiedono sempre la tua conferma.</div></div>
      <textarea id="ask" placeholder="Es. Domani alle 18 metti una lezione con Marco; oppure: quanto mi deve Laura?"></textarea>
      <div class="row"><button class="grow" onclick="askJarvis()">Invia</button><button id="mic" onclick="startVoice()">🎙️ Parla</button></div>
    </div>
    <div id="aiConfirm"></div>
  </section>
</div>

<div class="bottom"><div class="bottomin"><button class="grow" onclick="openJarvis()">🎙️ Parla con Jarvis</button><button class="secondary" onclick="backup()">⬇ Backup</button></div></div>

<script>
let DATA={students:[],lessons:[],events:[],tasks:[],publications:[]};
let pending=null, voiceOn=false;
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const euro=n=>new Intl.NumberFormat("it-IT",{style:"currency",currency:"EUR"}).format(Number(n||0));
const dt=s=>s?new Date(s).toLocaleString("it-IT",{dateStyle:"short",timeStyle:"short"}):"";

async function api(url,opt={}){let r=await fetch(url,{headers:{"Content-Type":"application/json",...(opt.headers||{})},...opt});if(r.status===401){location="/login";throw new Error("Login richiesto")}let d=await r.json();if(!r.ok)throw new Error(d.error||"Errore");return d}

function show(id,btn){document.querySelectorAll(".view").forEach(x=>x.classList.remove("active"));document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));$(id).classList.add("active");if(btn)btn.classList.add("active")}
function openJarvis(){show("assistant",document.querySelectorAll(".tab")[6]);$("ask").focus()}
function confirmBox(target,title,html,fn){pending=fn;$(target).innerHTML=`<div class="card confirm"><b>${esc(title)}</b><div style="margin:10px 0">${html}</div><div class="row"><button class="ok" onclick="confirmPending('${target}')">Conferma</button><button class="secondary" onclick="cancelPending('${target}')">Annulla</button></div></div>`}
async function confirmPending(target){if(!pending)return;let fn=pending;pending=null;try{await fn();$(target).innerHTML="";await loadAll()}catch(e){alert(e.message)}}
function cancelPending(target){pending=null;$(target).innerHTML=""}

async function loadAll(){
  let d=await api("/api/bootstrap");DATA=d;
  renderDashboard();renderStudents();renderCalendar();renderEvents();renderTasks();renderPublications();fillSelects();
  $("storageNotice").innerHTML=d.storage_persistent?"":'<div class="notice">⚠️ Archivio server non ancora configurato come permanente. Prima di inserire dati reali configureremo l’archivio persistente.</div>';
}
function fillSelects(){
  let opts=DATA.students.filter(s=>s.active).map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join("");
  $("lessonStudent").innerHTML=opts||'<option value="">Nessun allievo</option>';
  $("pubEvent").innerHTML=DATA.events.map(e=>`<option value="${e.id}">${esc(e.title)} · ${dt(e.starts_at)}</option>`).join("")||'<option value="">Nessuna serata</option>';
}
function renderDashboard(){
  let d=DATA.dashboard;
  $("stats").innerHTML=[
    ["Allievi attivi",d.active_students],["Lezioni oggi",d.lessons_today],["Residue",d.remaining_lessons],["Da incassare",euro(d.total_due)]
  ].map(x=>`<div class="stat"><b>${x[1]}</b><span>${x[0]}</span></div>`).join("");
  $("agenda48").innerHTML=d.agenda48.map(x=>`<div class="item"><b>${esc(x.label)}</b><div>${dt(x.starts_at)} · ${esc(x.where||"")}</div><div class="small">${esc(x.type)}</div></div>`).join("")||'<div class="empty">Nessun appuntamento.</div>';
  $("alerts").innerHTML=d.alerts.map(x=>`<div class="item">${esc(x)}</div>`).join("")||'<div class="empty">Nessun avviso.</div>';
  $("activity").innerHTML=d.activity.map(x=>`<div class="item">${esc(x.text)}<div class="small">${dt(x.created_at)}</div></div>`).join("")||'<div class="empty">Nessuna attività.</div>';
}
function renderStudents(){
  let q=($("studentSearch")?.value||"").toLowerCase();
  let arr=DATA.students.filter(s=>s.name.toLowerCase().includes(q));
  $("studentList").innerHTML=arr.map(s=>`<div class="item">
    <h3>${esc(s.name)}</h3>
    <span class="pill">${esc(s.lesson_type||"Privata")}</span>
    <span class="pill">${s.done_lessons}/${s.package?.total_lessons||0} fatte</span>
    <span class="pill">${s.remaining_lessons} residue</span>
    <span class="pill ${s.due>0?'bad':'good'}">${euro(s.due)} da incassare</span>
    <div class="small">${esc(s.phone||"")} ${s.level?"· "+esc(s.level):""} ${s.preferred_days?"· "+esc(s.preferred_days):""}</div>
    ${s.goals?`<div class="small">Obiettivi: ${esc(s.goals)}</div>`:""}
    ${s.notes?`<div class="small">Note: ${esc(s.notes)}</div>`:""}
    <div class="row" style="margin-top:8px">
      <button onclick="quickComplete(${s.id})">✓ Lezione fatta</button>
      <button class="secondary" onclick="quickPayment(${s.id})">€ Pagamento</button>
    </div></div>`).join("")||'<div class="empty">Nessun allievo.</div>';
}
function renderCalendar(){
  $("calendarList").innerHTML=DATA.lessons.map(l=>`<div class="item"><b>${esc(l.student_name)}</b> · ${dt(l.starts_at)}
    <div>${l.duration_min} min · ${esc(l.location||"")}</div>
    <span class="pill">${esc(l.status)}</span><span class="pill">${esc(l.kind)}</span>
    ${l.status==="scheduled"?`<div class="row" style="margin-top:7px"><button onclick="setLessonStatus(${l.id},'completed')">✓ Fatta</button><button class="secondary" onclick="setLessonStatus(${l.id},'cancelled')">Annullata</button></div>`:""}
  </div>`).join("")||'<div class="empty">Nessuna lezione in agenda.</div>';
}
function renderEvents(){
  $("eventList").innerHTML=DATA.events.map(e=>`<div class="item"><h3>${esc(e.title)}</h3><div>${dt(e.starts_at)} · ${esc(e.venue)} ${e.city?"· "+esc(e.city):""}</div><div class="small">${esc(e.description||"")}</div><span class="pill">${esc(e.status)}</span><button class="secondary" onclick="goPublish(${e.id})">Crea post</button></div>`).join("")||'<div class="empty">Nessuna serata.</div>';
}
function renderTasks(){
  $("taskList").innerHTML=DATA.tasks.map(t=>`<div class="item"><b>${esc(t.title)}</b><div>${t.due_at?dt(t.due_at):"Senza scadenza"} · ${esc(t.category)} · priorità ${esc(t.priority)}</div>${t.notes?`<div class="small">${esc(t.notes)}</div>`:""}${t.status==="open"?`<button onclick="closeTask(${t.id})">✓ Fatto</button>`:"<span class='pill good'>completata</span>"}</div>`).join("")||'<div class="empty">Nessuna attività.</div>';
}
function renderPublications(){
  $("publicationList").innerHTML=DATA.publications.map(p=>`<div class="item"><b>${esc(p.channel)}</b> · <span class="pill">${esc(p.status)}</span>${p.event_title?` · ${esc(p.event_title)}`:""}<div style="white-space:pre-wrap;margin-top:7px">${esc(p.caption)}</div>${p.status==="draft"?`<button onclick="approvePub(${p.id})">Approva bozza</button>`:""}</div>`).join("")||'<div class="empty">Nessuna bozza.</div>';
}
function toggleStudentForm(){$("studentForm").style.display=$("studentForm").style.display==="none"?"block":"none"}

function prepareStudent(){
  let body={name:$("sName").value.trim(),phone:$("sPhone").value.trim(),email:$("sEmail").value.trim(),level:$("sLevel").value.trim(),lesson_type:$("sType").value.trim()||"Privata",preferred_days:$("sDays").value.trim(),goals:$("sGoals").value.trim(),notes:$("sNotes").value.trim(),
    package:{total_lessons:+$("pTotal").value||0,duration_min:+$("pDuration").value||60,price_total:+$("pPrice").value||0,start_date:$("pStart").value,expiry_date:$("pExpiry").value,paid:+$("pPaid").value||0,payment_method:$("pMethod").value.trim()}}
  if(!body.name)return alert("Inserisci il nome.");
  confirmBox("studentConfirm","Conferma nuovo allievo",`<b>${esc(body.name)}</b><br>${body.package.total_lessons} lezioni · ${body.package.duration_min} min · ${euro(body.package.price_total)}<br>Già pagato ${euro(body.package.paid)}`,()=>api("/api/students",{method:"POST",body:JSON.stringify(body)}))
}
function prepareLesson(){
  let body={student_id:+$("lessonStudent").value,starts_at:$("lessonStart").value,duration_min:+$("lessonDuration").value||60,location:$("lessonLocation").value.trim(),kind:$("lessonKind").value,notes:$("lessonNotes").value.trim()};
  if(!body.student_id||!body.starts_at)return alert("Scegli allievo e data/ora.");
  let s=DATA.students.find(x=>x.id===body.student_id);
  confirmBox("lessonConfirm","Conferma lezione",`${esc(s?.name||"")} · ${dt(body.starts_at)} · ${body.duration_min} min`,()=>api("/api/lessons",{method:"POST",body:JSON.stringify(body)}))
}
async function setLessonStatus(id,status){if(!confirm("Confermi?"))return;await api(`/api/lessons/${id}`,{method:"PATCH",body:JSON.stringify({status})});await loadAll()}
function prepareEvent(){
  let body={title:$("eTitle").value.trim(),starts_at:$("eStart").value,ends_at:$("eEnd").value,venue:$("eVenue").value.trim(),city:$("eCity").value.trim(),address:$("eAddress").value.trim(),price_text:$("ePrice").value.trim(),music:$("eMusic").value.trim(),dress_code:$("eDress").value.trim(),contact:$("eContact").value.trim(),description:$("eDescription").value.trim(),image_url:$("eImage").value.trim()};
  if(!body.title||!body.starts_at)return alert("Titolo e data/ora sono obbligatori.");
  confirmBox("eventConfirm","Conferma serata",`<b>${esc(body.title)}</b><br>${dt(body.starts_at)} · ${esc(body.venue)} ${body.city?"· "+esc(body.city):""}`,()=>api("/api/events",{method:"POST",body:JSON.stringify(body)}))
}
function prepareTask(){
  let body={title:$("tTitle").value.trim(),due_at:$("tDue").value,category:$("tCategory").value,priority:$("tPriority").value,notes:$("tNotes").value.trim()};
  if(!body.title)return alert("Inserisci l'attività.");
  confirmBox("taskConfirm","Conferma attività",`${esc(body.title)}${body.due_at?" · "+dt(body.due_at):""}`,()=>api("/api/tasks",{method:"POST",body:JSON.stringify(body)}))
}
async function closeTask(id){await api(`/api/tasks/${id}`,{method:"PATCH",body:JSON.stringify({status:"done"})});await loadAll()}
async function quickComplete(studentId){
  let s=DATA.students.find(x=>x.id===studentId);if(!s)return;
  let scheduled=DATA.lessons.find(l=>l.student_id===studentId&&l.status==="scheduled");
  if(scheduled){if(confirm(`Segno come fatta la lezione in agenda di ${s.name}?`)){await setLessonStatus(scheduled.id,"completed")}return}
  let start=new Date().toISOString().slice(0,16);
  if(!confirm(`Registro adesso una lezione effettuata per ${s.name}?`))return;
  let x=await api("/api/lessons",{method:"POST",body:JSON.stringify({student_id:studentId,starts_at:start,duration_min:s.package?.duration_min||60,status:"completed",kind:"standard",location:"",notes:"Registrata rapidamente"})});await loadAll()
}
async function quickPayment(studentId){
  let s=DATA.students.find(x=>x.id===studentId);let v=prompt(`Importo ricevuto da ${s.name} (€):`);if(v===null)return;let amount=Number(v.replace(",","."));if(!(amount>0))return alert("Importo non valido.");
  if(!confirm(`Confermi ${euro(amount)} ricevuti da ${s.name}?`))return;
  await api("/api/payments",{method:"POST",body:JSON.stringify({student_id:studentId,amount,paid_at:new Date().toISOString().slice(0,10),method:"",notes:""})});await loadAll()
}
function goPublish(id){show("publish",document.querySelectorAll(".tab")[5]);$("pubEvent").value=id}
async function generatePublications(){let id=+$("pubEvent").value;if(!id)return alert("Scegli una serata.");let d=await api(`/api/events/${id}/draft-publications`,{method:"POST"});alert(`Create ${d.created} bozze.`);await loadAll()}
async function approvePub(id){if(!confirm("Approvo questa bozza per la futura pubblicazione?"))return;await api(`/api/publications/${id}`,{method:"PATCH",body:JSON.stringify({status:"approved"})});await loadAll()}

function addMsg(cls,text){let d=document.createElement("div");d.className="msg "+cls;d.textContent=text;$("chat").appendChild(d);$("chat").scrollTop=$("chat").scrollHeight}
async function askJarvis(){
  let message=$("ask").value.trim();if(!message)return;$("ask").value="";addMsg("me",message);
  try{let d=await api("/api/assistant",{method:"POST",body:JSON.stringify({message})});addMsg("ai",d.reply||"");if(voiceOn)speak(d.reply||"");if(d.action)prepareAIAction(d.action)}
  catch(e){addMsg("ai","Errore: "+e.message)}
}
function prepareAIAction(action){
  let summary=esc(action.summary||"Jarvis propone una modifica.");
  confirmBox("aiConfirm","Jarvis propone",summary,()=>api("/api/action",{method:"POST",body:JSON.stringify({action})}))
}
function toggleVoice(){if(!("speechSynthesis" in window))return alert("Sintesi vocale non supportata.");voiceOn=!voiceOn;$("voice").classList.toggle("on",voiceOn);$("voice").textContent=voiceOn?"🔊 Voce attiva":"🔊 Voce";if(voiceOn)speak("Voce attivata")}
function speak(text){speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(text);u.lang="it-IT";speechSynthesis.speak(u)}
function startVoice(){let SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return alert("Riconoscimento vocale non supportato.");let r=new SR();r.lang="it-IT";r.interimResults=false;$("mic").classList.add("listening");$("mic").textContent="🎙️ Ascolto";r.onresult=e=>$("ask").value=e.results[0][0].transcript;r.onend=()=>{$("mic").classList.remove("listening");$("mic").textContent="🎙️ Parla";if($("ask").value.trim())askJarvis()};r.onerror=r.onend;r.start()}
function backup(){location="/api/backup"}
function logout(){location="/logout"}
function loadCalendar(){loadAll()}
loadAll().catch(e=>alert(e.message));
</script>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PIN:
        session["jarvis_auth"] = True
        return redirect(url_for("home"))
    error = ""
    if request.method == "POST":
        if request.form.get("pin", "") == ADMIN_PIN:
            session["jarvis_auth"] = True
            return redirect(url_for("home"))
        error = "PIN non corretto."
    return render_template_string(LOGIN_PAGE, error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@auth_required
def home():
    return render_template_string(PAGE)


@app.route("/api/bootstrap")
@auth_required
def bootstrap():
    con = get_db()

    students_rows = con.execute("SELECT id FROM students ORDER BY active DESC, name").fetchall()
    students = [student_summary(con, r["id"]) for r in students_rows]

    lessons = [dict(r) for r in con.execute("""
        SELECT l.*, s.name AS student_name
        FROM lessons l JOIN students s ON s.id=l.student_id
        WHERE l.starts_at >= datetime('now','-2 days')
        ORDER BY l.starts_at
        LIMIT 200
    """).fetchall()]

    events = [dict(r) for r in con.execute("""
        SELECT * FROM events
        WHERE starts_at >= datetime('now','-30 days')
        ORDER BY starts_at
        LIMIT 200
    """).fetchall()]

    tasks = [dict(r) for r in con.execute("""
        SELECT * FROM tasks
        ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END,
                 CASE priority WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END,
                 due_at
        LIMIT 200
    """).fetchall()]

    publications = [dict(r) for r in con.execute("""
        SELECT p.*, e.title AS event_title
        FROM publications p LEFT JOIN events e ON e.id=p.event_id
        ORDER BY p.id DESC LIMIT 200
    """).fetchall()]

    active_students = sum(1 for s in students if s["active"])
    remaining = sum(int(s["remaining_lessons"]) for s in students if s["active"])
    total_due = sum(float(s["due"]) for s in students if s["active"])
    lessons_today = con.execute("""
        SELECT COUNT(*) AS n FROM lessons
        WHERE substr(starts_at,1,10)=? AND status='scheduled'
    """, (today_iso(),)).fetchone()["n"]

    horizon = (datetime.now() + timedelta(hours=48)).replace(microsecond=0).isoformat()
    now = now_iso()
    agenda = []
    for r in con.execute("""
        SELECT l.starts_at, l.location, s.name
        FROM lessons l JOIN students s ON s.id=l.student_id
        WHERE l.starts_at BETWEEN ? AND ? AND l.status='scheduled'
        ORDER BY l.starts_at
    """, (now, horizon)).fetchall():
        agenda.append({"type": "Lezione", "label": r["name"], "starts_at": r["starts_at"], "where": r["location"]})
    for r in con.execute("""
        SELECT starts_at, venue, title FROM events
        WHERE starts_at BETWEEN ? AND ? AND status!='cancelled'
        ORDER BY starts_at
    """, (now, horizon)).fetchall():
        agenda.append({"type": "Serata", "label": r["title"], "starts_at": r["starts_at"], "where": r["venue"]})
    agenda.sort(key=lambda x: x["starts_at"])

    alerts = []
    for s in students:
        if not s["active"]:
            continue
        if s["package"]:
            if s["remaining_lessons"] <= 1:
                alerts.append(f"{s['name']}: {s['remaining_lessons']} lezioni residue.")
            if s["due"] > 0:
                alerts.append(f"{s['name']}: {s['due']:.2f} € da incassare.")
            exp = s["package"].get("expiry_date") or ""
            if exp:
                try:
                    days = (datetime.fromisoformat(exp).date() - datetime.now().date()).days
                    if days <= 14:
                        alerts.append(f"{s['name']}: pacchetto in scadenza tra {days} giorni.")
                except Exception:
                    pass

    overdue_tasks = con.execute("""
        SELECT title FROM tasks
        WHERE status='open' AND due_at!='' AND due_at < ?
        ORDER BY due_at
    """, (now,)).fetchall()
    for t in overdue_tasks:
        alerts.append(f"Attività scaduta: {t['title']}.")

    activity = [dict(r) for r in con.execute("""
        SELECT * FROM activity ORDER BY id DESC LIMIT 12
    """).fetchall()]

    con.close()

    storage_persistent = bool(os.environ.get("JARVIS_DB_PATH"))
    return jsonify({
        "students": students,
        "lessons": lessons,
        "events": events,
        "tasks": tasks,
        "publications": publications,
        "dashboard": {
            "active_students": active_students,
            "lessons_today": lessons_today,
            "remaining_lessons": remaining,
            "total_due": total_due,
            "agenda48": agenda,
            "alerts": alerts[:30],
            "activity": activity,
        },
        "storage_persistent": storage_persistent,
    })


@app.route("/api/students", methods=["POST"])
@auth_required
def create_student():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Nome obbligatorio"}), 400

    pkg = data.get("package") or {}
    con = get_db()
    cur = con.execute("""
        INSERT INTO students(name, phone, email, level, lesson_type, preferred_days, goals, notes, active, created_at)
        VALUES(?,?,?,?,?,?,?,?,1,?)
    """, (
        name, data.get("phone",""), data.get("email",""), data.get("level",""),
        data.get("lesson_type","Privata"), data.get("preferred_days",""),
        data.get("goals",""), data.get("notes",""), now_iso()
    ))
    sid = cur.lastrowid

    pid = None
    if int(pkg.get("total_lessons") or 0) > 0 or float(pkg.get("price_total") or 0) > 0:
        cur = con.execute("""
            INSERT INTO packages(student_id,total_lessons,duration_min,price_total,start_date,expiry_date,notes,active,created_at)
            VALUES(?,?,?,?,?,?,?,1,?)
        """, (
            sid, int(pkg.get("total_lessons") or 0), int(pkg.get("duration_min") or 60),
            float(pkg.get("price_total") or 0), pkg.get("start_date",""), pkg.get("expiry_date",""),
            pkg.get("notes",""), now_iso()
        ))
        pid = cur.lastrowid

        paid = float(pkg.get("paid") or 0)
        if paid > 0:
            con.execute("""
                INSERT INTO payments(student_id,package_id,amount,paid_at,method,notes,created_at)
                VALUES(?,?,?,?,?,?,?)
            """, (sid, pid, paid, today_iso(), pkg.get("payment_method",""), "Pagamento iniziale", now_iso()))

    con.commit()
    con.close()
    log_activity(f"Inserito allievo {name}.")
    return jsonify({"ok": True, "student_id": sid})


@app.route("/api/lessons", methods=["POST"])
@auth_required
def create_lesson():
    data = request.get_json(silent=True) or {}
    sid = int(data.get("student_id") or 0)
    starts_at = str(data.get("starts_at", "")).strip()
    if not sid or not starts_at:
        return jsonify({"error": "Allievo e data/ora obbligatori"}), 400

    con = get_db()
    student = con.execute("SELECT name FROM students WHERE id=?", (sid,)).fetchone()
    if not student:
        con.close()
        return jsonify({"error": "Allievo non trovato"}), 404

    pkg = con.execute("""
        SELECT id FROM packages WHERE student_id=? AND active=1 ORDER BY id DESC LIMIT 1
    """, (sid,)).fetchone()

    duration = int(data.get("duration_min") or 60)
    status = data.get("status", "scheduled")
    kind = data.get("kind", "standard")
    counts_package = 0 if kind in ("trial", "free") else 1

    # Basic overlap warning is returned but does not silently block after user confirmation.
    start_dt = datetime.fromisoformat(starts_at)
    end_dt = start_dt + timedelta(minutes=duration)
    conflicts = con.execute("""
        SELECT l.id, l.starts_at, l.duration_min, s.name
        FROM lessons l JOIN students s ON s.id=l.student_id
        WHERE l.status='scheduled'
    """).fetchall()
    conflict_names = []
    for c in conflicts:
        try:
            cstart = datetime.fromisoformat(c["starts_at"])
            cend = cstart + timedelta(minutes=int(c["duration_min"]))
            if start_dt < cend and end_dt > cstart:
                conflict_names.append(c["name"])
        except Exception:
            pass

    cur = con.execute("""
        INSERT INTO lessons(student_id,package_id,starts_at,duration_min,location,status,kind,counts_package,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        sid, pkg["id"] if pkg else None, starts_at, duration, data.get("location",""),
        status, kind, counts_package, data.get("notes",""), now_iso()
    ))
    con.commit()
    con.close()
    log_activity(f"Lezione {status}: {student['name']} · {starts_at}.")
    return jsonify({"ok": True, "lesson_id": cur.lastrowid, "conflicts": conflict_names})


@app.route("/api/lessons/<int:lesson_id>", methods=["PATCH"])
@auth_required
def update_lesson(lesson_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    allowed = {"scheduled","completed","cancelled","no_show"}
    if status not in allowed:
        return jsonify({"error": "Stato non valido"}), 400
    con = get_db()
    row = con.execute("""
        SELECT l.id, s.name FROM lessons l JOIN students s ON s.id=l.student_id WHERE l.id=?
    """, (lesson_id,)).fetchone()
    if not row:
        con.close()
        return jsonify({"error": "Lezione non trovata"}), 404
    con.execute("UPDATE lessons SET status=? WHERE id=?", (status, lesson_id))
    con.commit()
    con.close()
    log_activity(f"{row['name']}: lezione impostata come {status}.")
    return jsonify({"ok": True})


@app.route("/api/payments", methods=["POST"])
@auth_required
def create_payment():
    data = request.get_json(silent=True) or {}
    sid = int(data.get("student_id") or 0)
    amount = float(data.get("amount") or 0)
    if not sid or amount <= 0:
        return jsonify({"error": "Allievo e importo validi sono obbligatori"}), 400
    con = get_db()
    student = con.execute("SELECT name FROM students WHERE id=?", (sid,)).fetchone()
    if not student:
        con.close()
        return jsonify({"error": "Allievo non trovato"}), 404
    pkg = con.execute("SELECT id FROM packages WHERE student_id=? AND active=1 ORDER BY id DESC LIMIT 1", (sid,)).fetchone()
    con.execute("""
        INSERT INTO payments(student_id,package_id,amount,paid_at,method,notes,created_at)
        VALUES(?,?,?,?,?,?,?)
    """, (sid, pkg["id"] if pkg else None, amount, data.get("paid_at") or today_iso(), data.get("method",""), data.get("notes",""), now_iso()))
    con.commit()
    con.close()
    log_activity(f"{student['name']}: registrato pagamento di {amount:.2f} €.")
    return jsonify({"ok": True})


@app.route("/api/events", methods=["POST"])
@auth_required
def create_event():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    starts_at = str(data.get("starts_at", "")).strip()
    if not title or not starts_at:
        return jsonify({"error": "Titolo e data/ora obbligatori"}), 400
    con = get_db()
    cur = con.execute("""
        INSERT INTO events(title,starts_at,ends_at,venue,city,address,price_text,description,music,dress_code,contact,image_url,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        title, starts_at, data.get("ends_at",""), data.get("venue",""), data.get("city",""),
        data.get("address",""), data.get("price_text",""), data.get("description",""),
        data.get("music",""), data.get("dress_code",""), data.get("contact",""),
        data.get("image_url",""), "planned", now_iso()
    ))
    con.commit()
    con.close()
    log_activity(f"Creata serata: {title} · {starts_at}.")
    return jsonify({"ok": True, "event_id": cur.lastrowid})


@app.route("/api/tasks", methods=["POST"])
@auth_required
def create_task():
    data = request.get_json(silent=True) or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify({"error": "Titolo obbligatorio"}), 400
    con = get_db()
    cur = con.execute("""
        INSERT INTO tasks(title,due_at,category,priority,status,notes,related_type,related_id,created_at)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, (title, data.get("due_at",""), data.get("category","generale"), data.get("priority","media"), "open",
          data.get("notes",""), data.get("related_type",""), data.get("related_id"), now_iso()))
    con.commit()
    con.close()
    log_activity(f"Creata attività: {title}.")
    return jsonify({"ok": True, "task_id": cur.lastrowid})


@app.route("/api/tasks/<int:task_id>", methods=["PATCH"])
@auth_required
def update_task(task_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"open","done"}:
        return jsonify({"error": "Stato non valido"}), 400
    con = get_db()
    row = con.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        con.close()
        return jsonify({"error": "Attività non trovata"}), 404
    con.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
    con.commit()
    con.close()
    log_activity(f"Attività '{row['title']}' impostata come {status}.")
    return jsonify({"ok": True})


@app.route("/api/events/<int:event_id>/draft-publications", methods=["POST"])
@auth_required
def draft_publications(event_id):
    con = get_db()
    event = con.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not event:
        con.close()
        return jsonify({"error": "Serata non trovata"}), 404

    api_key = os.environ.get("OPENAI_API_KEY")
    captions = None
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            prompt = {
                "event": dict(event),
                "task": "Crea tre testi promozionali distinti per Instagram, Facebook e sito web. Italiano naturale, niente informazioni inventate."
            }
            resp = client.responses.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-5"),
                instructions=(
                    'Rispondi solo JSON valido: {"instagram":"...","facebook":"...","website":"..."}. '
                    "Per Instagram usa tono coinvolgente e hashtag sobri; Facebook più informativo; sito chiaro e completo."
                ),
                input=json.dumps(prompt, ensure_ascii=False)
            )
            raw = resp.output_text.strip().replace("```json","").replace("```","").strip()
            captions = json.loads(raw)
        except Exception:
            captions = None

    if not captions:
        base = f"{event['title']} · {event['starts_at']} · {event['venue']} {event['city']}. {event['description']}".strip()
        captions = {"instagram": base, "facebook": base, "website": base}

    created = 0
    for channel in ("instagram","facebook","website"):
        con.execute("""
            INSERT INTO publications(event_id,channel,caption,status,scheduled_at,published_at,created_at)
            VALUES(?,?,?,?,?,?,?)
        """, (event_id, channel, captions.get(channel,""), "draft", "", "", now_iso()))
        created += 1

    con.commit()
    con.close()
    log_activity(f"Create bozze pubblicazione per '{event['title']}'.")
    return jsonify({"ok": True, "created": created})


@app.route("/api/publications/<int:pub_id>", methods=["PATCH"])
@auth_required
def update_publication(pub_id):
    data = request.get_json(silent=True) or {}
    status = data.get("status")
    if status not in {"draft","approved","published"}:
        return jsonify({"error": "Stato non valido"}), 400
    con = get_db()
    con.execute("UPDATE publications SET status=?, published_at=CASE WHEN ?='published' THEN ? ELSE published_at END WHERE id=?",
                (status, status, now_iso(), pub_id))
    con.commit()
    con.close()
    log_activity(f"Pubblicazione #{pub_id}: {status}.")
    return jsonify({"ok": True})


def assistant_context():
    con = get_db()
    students = [student_summary(con, r["id"]) for r in con.execute("SELECT id FROM students WHERE active=1 ORDER BY name").fetchall()]
    lessons = [dict(r) for r in con.execute("""
        SELECT l.id,l.student_id,s.name AS student_name,l.starts_at,l.duration_min,l.location,l.status,l.kind
        FROM lessons l JOIN students s ON s.id=l.student_id
        WHERE l.starts_at >= datetime('now','-7 days')
        ORDER BY l.starts_at LIMIT 120
    """).fetchall()]
    events = [dict(r) for r in con.execute("SELECT * FROM events ORDER BY starts_at LIMIT 100").fetchall()]
    tasks = [dict(r) for r in con.execute("SELECT * FROM tasks WHERE status='open' ORDER BY due_at LIMIT 100").fetchall()]
    con.close()
    return {"now": now_iso(), "students": students, "lessons": lessons, "events": events, "tasks": tasks}


@app.route("/api/assistant", methods=["POST"])
@auth_required
def assistant():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Messaggio vuoto"}), 400
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY non configurata"}), 500

    context = assistant_context()
    instructions = """
Sei Jarvis, segretaria AI personale per un insegnante di ballo.
Gestisci: allievi, pacchetti, lezioni, pagamenti, calendario, recuperi, attività, serate di ballo e bozze di pubblicazione.
Usa SOLO i dati nel contesto. Non inventare nomi, importi, date, contatti o impegni.
Per domande informative rispondi direttamente e action=null.
Per QUALSIASI modifica proponi UNA azione e non dire mai che è stata eseguita: l'utente deve confermarla.
Se mancano dati essenziali, chiedili e action=null.

Azioni ammesse:
- add_student: payload come /api/students
- schedule_lesson: student_id, starts_at, duration_min, location, kind, notes
- complete_lesson: lesson_id
- cancel_lesson: lesson_id
- record_payment: student_id, amount, paid_at, method, notes
- create_event: title, starts_at, ends_at, venue, city, address, price_text, description, music, dress_code, contact, image_url
- create_task: title, due_at, category, priority, notes
- draft_publications: event_id

Restituisci ESCLUSIVAMENTE JSON valido:
{"reply":"testo per l'utente","action":null}
oppure
{"reply":"testo","action":{"type":"schedule_lesson","summary":"Testo preciso di ciò che verrà fatto","payload":{...}}}
"""
    client = OpenAI(api_key=api_key)
    try:
        resp = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-5"),
            instructions=instructions,
            input=json.dumps({"message": message, "context": context}, ensure_ascii=False)
        )
        raw = resp.output_text.strip().replace("```json","").replace("```","").strip()
        parsed = json.loads(raw)
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/action", methods=["POST"])
@auth_required
def execute_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action") or {}
    kind = action.get("type")
    payload = action.get("payload") or {}

    # Execute only after explicit client confirmation.
    if kind == "add_student":
        with app.test_request_context("/api/students", method="POST", json=payload):
            session["jarvis_auth"] = True
            return create_student()

    if kind == "schedule_lesson":
        with app.test_request_context("/api/lessons", method="POST", json=payload):
            session["jarvis_auth"] = True
            return create_lesson()

    if kind in {"complete_lesson","cancel_lesson"}:
        lesson_id = int(payload.get("lesson_id") or action.get("lesson_id") or 0)
        if not lesson_id:
            return jsonify({"error": "lesson_id mancante"}), 400
        status = "completed" if kind == "complete_lesson" else "cancelled"
        con = get_db()
        row = con.execute("""
            SELECT l.id,s.name FROM lessons l JOIN students s ON s.id=l.student_id WHERE l.id=?
        """, (lesson_id,)).fetchone()
        if not row:
            con.close()
            return jsonify({"error": "Lezione non trovata"}), 404
        con.execute("UPDATE lessons SET status=? WHERE id=?", (status, lesson_id))
        con.commit()
        con.close()
        log_activity(f"{row['name']}: lezione {status}.")
        return jsonify({"ok": True})

    if kind == "record_payment":
        with app.test_request_context("/api/payments", method="POST", json=payload):
            session["jarvis_auth"] = True
            return create_payment()

    if kind == "create_event":
        with app.test_request_context("/api/events", method="POST", json=payload):
            session["jarvis_auth"] = True
            return create_event()

    if kind == "create_task":
        with app.test_request_context("/api/tasks", method="POST", json=payload):
            session["jarvis_auth"] = True
            return create_task()

    if kind == "draft_publications":
        event_id = int(payload.get("event_id") or 0)
        if not event_id:
            return jsonify({"error": "event_id mancante"}), 400
        with app.test_request_context(f"/api/events/{event_id}/draft-publications", method="POST"):
            session["jarvis_auth"] = True
            return draft_publications(event_id)

    return jsonify({"error": "Azione non supportata"}), 400


@app.route("/api/backup")
@auth_required
def backup():
    con = get_db()
    data = {}
    for table in ("students","packages","lessons","payments","events","tasks","publications","activity"):
        data[table] = [dict(r) for r in con.execute(f"SELECT * FROM {table}").fetchall()]
    con.close()
    path = os.path.join("/tmp", f"jarvis_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
