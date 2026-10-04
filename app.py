import os
import json

from flask import Flask, jsonify, request, render_template_string
from openai import OpenAI

app = Flask(__name__)

PAGE = r"""
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>Jarvis</title>
  <style>
    :root { color-scheme: dark; }
    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0b1020;
      color: white;
      padding: 16px;
    }

    .box {
      max-width: 820px;
      margin: auto;
    }

    h1 {
      margin: 0 0 6px;
    }

    .subtitle {
      color: #aab4c5;
      margin-bottom: 14px;
    }

    #chat {
      background: #111827;
      border-radius: 15px;
      padding: 15px;
      min-height: 280px;
      max-height: 48vh;
      overflow-y: auto;
      margin-bottom: 12px;
    }

    .msg {
      padding: 10px;
      margin: 8px 0;
      border-radius: 10px;
      line-height: 1.4;
      white-space: pre-wrap;
    }

    .user { background: #1f2937; }
    .jarvis { background: #172554; }

    textarea {
      width: 100%;
      min-height: 64px;
      border-radius: 10px;
      border: 1px solid #334155;
      background: #111827;
      color: white;
      padding: 10px;
      font-size: 16px;
    }

    .buttons {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    button {
      margin-top: 10px;
      padding: 13px 16px;
      border: none;
      border-radius: 10px;
      background: #2563eb;
      color: white;
      font-size: 16px;
      font-weight: bold;
      cursor: pointer;
    }

    button.secondary { background: #374151; }
    button.good { background: #15803d; }
    button.danger { background: #b91c1c; }

    #mic.listening { background: #b91c1c; }
    #voiceBtn.enabled { background: #15803d; }

    #status {
      margin-top: 10px;
      color: #aab4c5;
      min-height: 20px;
      font-size: 14px;
    }

    #pendingBox {
      display: none;
      margin-top: 12px;
      background: #3b2f0b;
      border: 1px solid #8a6d1f;
      border-radius: 12px;
      padding: 12px;
    }

    #lessonPanel {
      display: none;
      margin-top: 18px;
      background: #111827;
      border-radius: 15px;
      padding: 14px;
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 12px;
    }

    .stat {
      background: #1f2937;
      border-radius: 10px;
      padding: 10px;
    }

    .stat small {
      display: block;
      color: #94a3b8;
      margin-bottom: 4px;
    }

    .stat strong {
      font-size: 18px;
    }

    .tableWrap {
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 720px;
    }

    th, td {
      border-bottom: 1px solid #334155;
      padding: 9px 7px;
      text-align: left;
      font-size: 14px;
    }

    th { color: #cbd5e1; }

    .muted {
      color: #94a3b8;
      font-size: 13px;
    }

    input[type=file] {
      display: none;
    }

    @media (max-width: 620px) {
      .stats {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      button {
        flex: 1 1 auto;
      }
    }
  </style>
</head>

<body>
<div class="box">

  <h1>Jarvis</h1>
  <div class="subtitle">Assistente personale · modulo Lezioni Private</div>

  <div id="chat">
    <div class="msg jarvis">
      Sono online. Posso gestire allievi, lezioni acquistate, fatte e residue, durata, costi, incassi e insoluti. Prima di modificare i dati ti chiederò conferma.
    </div>
  </div>

  <textarea id="text" placeholder='Esempio: "Aggiungi Marco: 10 lezioni da 1 ora, totale 500 euro, pagati 200"'></textarea>

  <div class="buttons">
    <button onclick="sendMessage()">Invia</button>
    <button id="mic" onclick="startVoice()">🎙️ Parla</button>
    <button id="voiceBtn" onclick="toggleVoice()">🔊 Attiva voce</button>
    <button class="secondary" onclick="toggleLessons()">📚 Lezioni private</button>
  </div>

  <div id="status"></div>

  <div id="pendingBox">
    <div id="pendingText"></div>
    <div class="buttons">
      <button class="good" onclick="confirmPending()">✓ Conferma</button>
      <button class="danger" onclick="cancelPending()">✕ Annulla</button>
    </div>
  </div>

  <div id="lessonPanel">
    <h2>Lezioni private</h2>

    <div class="stats">
      <div class="stat">
        <small>Allievi</small>
        <strong id="statStudents">0</strong>
      </div>
      <div class="stat">
        <small>Lezioni residue</small>
        <strong id="statRemaining">0</strong>
      </div>
      <div class="stat">
        <small>Incassato</small>
        <strong id="statPaid">€0</strong>
      </div>
      <div class="stat">
        <small>Da incassare</small>
        <strong id="statDue">€0</strong>
      </div>
    </div>

    <div class="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Allievo</th>
            <th>Acquistate</th>
            <th>Fatte</th>
            <th>Residue</th>
            <th>Durata</th>
            <th>Costo</th>
            <th>Incassato</th>
            <th>Insoluto</th>
          </tr>
        </thead>
        <tbody id="studentRows"></tbody>
      </table>
    </div>

    <p class="muted">
      I dati di questa prima versione restano salvati nel browser di questo dispositivo.
    </p>

    <div class="buttons">
      <button class="secondary" onclick="exportBackup()">Esporta backup</button>
      <button class="secondary" onclick="document.getElementById('importFile').click()">Importa backup</button>
      <input id="importFile" type="file" accept=".json,application/json" onchange="importBackup(event)">
    </div>
  </div>
</div>

<script>
const STORAGE_KEY = "jarvis_private_lessons_v1";

const chat = document.getElementById("chat");
const input = document.getElementById("text");
const micButton = document.getElementById("mic");
const voiceButton = document.getElementById("voiceBtn");
const statusBox = document.getElementById("status");
const pendingBox = document.getElementById("pendingBox");
const pendingText = document.getElementById("pendingText");

let voiceEnabled = false;
let italianVoice = null;
let recognition = null;
let pendingVoiceMessage = null;
let pendingAction = null;


function loadStudents() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const data = raw ? JSON.parse(raw) : [];
    return Array.isArray(data) ? data : [];
  } catch (_) {
    return [];
  }
}


function saveStudents(students) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(students));
  renderLessons();
}


function cleanName(name) {
  return String(name || "").trim();
}


function findStudentIndex(students, name) {
  const wanted = cleanName(name).toLowerCase();
  return students.findIndex(s => cleanName(s.name).toLowerCase() === wanted);
}


function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}


function money(value) {
  return "€" + num(value).toFixed(2);
}


function normalizeStudent(s) {
  return {
    id: s.id || (Date.now().toString(36) + Math.random().toString(36).slice(2)),
    name: cleanName(s.name),
    purchased: Math.max(0, num(s.purchased)),
    done: Math.max(0, num(s.done)),
    duration_hours: Math.max(0, num(s.duration_hours, 1)),
    total_cost: Math.max(0, num(s.total_cost)),
    paid: Math.max(0, num(s.paid)),
    notes: String(s.notes || "")
  };
}


function renderLessons() {
  const students = loadStudents().map(normalizeStudent);
  const rows = document.getElementById("studentRows");
  rows.innerHTML = "";

  let totalRemaining = 0;
  let totalPaid = 0;
  let totalDue = 0;

  students.forEach(s => {
    const remaining = Math.max(0, s.purchased - s.done);
    const due = Math.max(0, s.total_cost - s.paid);

    totalRemaining += remaining;
    totalPaid += s.paid;
    totalDue += due;

    const tr = document.createElement("tr");

    const values = [
      s.name,
      s.purchased,
      s.done,
      remaining,
      s.duration_hours + " h",
      money(s.total_cost),
      money(s.paid),
      money(due)
    ];

    values.forEach(v => {
      const td = document.createElement("td");
      td.textContent = v;
      tr.appendChild(td);
    });

    rows.appendChild(tr);
  });

  document.getElementById("statStudents").textContent = students.length;
  document.getElementById("statRemaining").textContent = totalRemaining;
  document.getElementById("statPaid").textContent = money(totalPaid);
  document.getElementById("statDue").textContent = money(totalDue);
}


function toggleLessons() {
  const panel = document.getElementById("lessonPanel");
  panel.style.display = panel.style.display === "block" ? "none" : "block";
  renderLessons();
}


function addMessage(type, text) {
  const div = document.createElement("div");
  div.className = "msg " + type;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}


function loadVoices() {
  if (!("speechSynthesis" in window)) return;

  const voices = window.speechSynthesis.getVoices();

  italianVoice =
    voices.find(v => v.lang === "it-IT") ||
    voices.find(v => v.lang && v.lang.toLowerCase().startsWith("it")) ||
    null;
}


if ("speechSynthesis" in window) {
  loadVoices();
  window.speechSynthesis.onvoiceschanged = loadVoices;
}


function toggleVoice() {
  if (!("speechSynthesis" in window)) {
    alert("La sintesi vocale non è supportata da questo browser.");
    return;
  }

  if (voiceEnabled) {
    voiceEnabled = false;
    window.speechSynthesis.cancel();
    voiceButton.textContent = "🔊 Attiva voce";
    voiceButton.classList.remove("enabled");
    statusBox.textContent = "Voce disattivata.";
    return;
  }

  voiceEnabled = true;
  voiceButton.textContent = "🔊 Voce attiva";
  voiceButton.classList.add("enabled");

  window.speechSynthesis.cancel();
  window.speechSynthesis.resume();

  const test = new SpeechSynthesisUtterance("Voce attivata");
  test.lang = "it-IT";
  if (italianVoice) test.voice = italianVoice;

  window.speechSynthesis.speak(test);
  statusBox.textContent = "Voce attivata.";
}


function speak(text) {
  if (!voiceEnabled || !("speechSynthesis" in window) || !text) return;

  window.speechSynthesis.cancel();
  window.speechSynthesis.resume();

  const u = new SpeechSynthesisUtterance(text);
  u.lang = "it-IT";
  u.volume = 1;
  u.rate = 1;
  u.pitch = 1;

  if (italianVoice) u.voice = italianVoice;

  u.onstart = () => statusBox.textContent = "Jarvis sta parlando...";
  u.onend = () => statusBox.textContent = "";
  u.onerror = e => statusBox.textContent = "Errore voce: " + e.error;

  setTimeout(() => {
    window.speechSynthesis.resume();
    window.speechSynthesis.speak(u);
  }, 250);
}


function describeAction(action) {
  if (!action || action.type === "none") return "";

  if (action.type === "add_student") {
    return `Aggiungere ${action.name} · acquistate ${action.purchased ?? 0} · fatte ${action.done ?? 0} · durata ${action.duration_hours ?? 1} h · costo ${money(action.total_cost ?? 0)} · pagato ${money(action.paid ?? 0)}.`;
  }

  if (action.type === "set_student") {
    return `Aggiornare i dati di ${action.name}.`;
  }

  if (action.type === "add_lesson_done") {
    return `Registrare ${action.amount ?? 1} lezione/i effettuata/e per ${action.name}.`;
  }

  if (action.type === "add_payment") {
    return `Registrare un pagamento di ${money(action.amount ?? 0)} per ${action.name}.`;
  }

  if (action.type === "delete_student") {
    return `Eliminare ${action.name} dall'archivio lezioni private.`;
  }

  return "Applicare la modifica proposta.";
}


function showPending(action) {
  pendingAction = action;
  pendingText.textContent = "Jarvis propone: " + describeAction(action);
  pendingBox.style.display = "block";
}


function cancelPending() {
  pendingAction = null;
  pendingBox.style.display = "none";
  addMessage("jarvis", "Modifica annullata.");
  speak("Modifica annullata.");
}


function confirmPending() {
  if (!pendingAction) return;

  const result = applyAction(pendingAction);

  pendingAction = null;
  pendingBox.style.display = "none";

  addMessage("jarvis", result);
  speak(result);
}


function applyAction(action) {
  let students = loadStudents().map(normalizeStudent);
  const type = action.type;
  const name = cleanName(action.name);

  if (type === "add_student") {
    if (!name) return "Nome dell'allievo mancante.";

    if (findStudentIndex(students, name) >= 0) {
      return `${name} esiste già. Dimmi cosa vuoi aggiornare.`;
    }

    students.push(normalizeStudent({
      name: name,
      purchased: action.purchased ?? 0,
      done: action.done ?? 0,
      duration_hours: action.duration_hours ?? 1,
      total_cost: action.total_cost ?? 0,
      paid: action.paid ?? 0,
      notes: action.notes ?? ""
    }));

    saveStudents(students);
    return `${name} aggiunto alle lezioni private.`;
  }

  const i = findStudentIndex(students, name);

  if (i < 0) {
    return `Non trovo un allievo chiamato ${name}.`;
  }

  if (type === "set_student") {
    const s = students[i];

    if (action.purchased !== null && action.purchased !== undefined) s.purchased = Math.max(0, num(action.purchased));
    if (action.done !== null && action.done !== undefined) s.done = Math.max(0, num(action.done));
    if (action.duration_hours !== null && action.duration_hours !== undefined) s.duration_hours = Math.max(0, num(action.duration_hours));
    if (action.total_cost !== null && action.total_cost !== undefined) s.total_cost = Math.max(0, num(action.total_cost));
    if (action.paid !== null && action.paid !== undefined) s.paid = Math.max(0, num(action.paid));
    if (action.notes !== null && action.notes !== undefined) s.notes = String(action.notes);

    students[i] = normalizeStudent(s);
    saveStudents(students);
    return `Dati di ${name} aggiornati.`;
  }

  if (type === "add_lesson_done") {
    students[i].done = Math.max(0, num(students[i].done) + Math.max(0, num(action.amount, 1)));
    saveStudents(students);
    return `Lezione registrata per ${name}. Restano ${Math.max(0, students[i].purchased - students[i].done)} lezioni.`;
  }

  if (type === "add_payment") {
    students[i].paid = Math.max(0, num(students[i].paid) + Math.max(0, num(action.amount)));
    saveStudents(students);
    const due = Math.max(0, students[i].total_cost - students[i].paid);
    return `Pagamento registrato per ${name}. Rimangono da incassare ${money(due)}.`;
  }

  if (type === "delete_student") {
    students.splice(i, 1);
    saveStudents(students);
    return `${name} eliminato dall'archivio.`;
  }

  return "Nessuna modifica applicata.";
}


async function sendMessage(forcedMessage = null) {
  const message = forcedMessage !== null ? forcedMessage.trim() : input.value.trim();

  if (!message) return;

  addMessage("user", message);
  input.value = "";
  statusBox.textContent = "Jarvis sta pensando...";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        message: message,
        students: loadStudents()
      })
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Errore del servizio.");
    }

    addMessage("jarvis", data.reply || "Va bene.");
    statusBox.textContent = "";

    if (data.action && data.action.type && data.action.type !== "none") {
      showPending(data.action);
    }

    speak(data.reply || "Va bene.");

  } catch (error) {
    addMessage("jarvis", "Errore: " + error.message);
    statusBox.textContent = "";
  }
}


input.addEventListener("keydown", function(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
});


function startVoice() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    alert("Il riconoscimento vocale non è supportato da questo browser.");
    return;
  }

  if (!voiceEnabled) {
    statusBox.textContent = "Prima premi 🔊 Attiva voce.";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "it-IT";
  recognition.interimResults = false;
  recognition.continuous = false;

  recognition.onstart = function() {
    pendingVoiceMessage = null;
    micButton.textContent = "🎙️ Ti ascolto...";
    micButton.classList.add("listening");
    statusBox.textContent = "Sto ascoltando...";
  };

  recognition.onresult = function(event) {
    const spokenText = event.results[0][0].transcript;
    pendingVoiceMessage = spokenText;
    input.value = spokenText;
    statusBox.textContent = "Ho sentito: " + spokenText;
  };

  recognition.onend = function() {
    micButton.textContent = "🎙️ Parla";
    micButton.classList.remove("listening");

    if (pendingVoiceMessage) {
      const message = pendingVoiceMessage;
      pendingVoiceMessage = null;
      sendMessage(message);
    }
  };

  recognition.onerror = function(event) {
    micButton.textContent = "🎙️ Parla";
    micButton.classList.remove("listening");
    statusBox.textContent = "Errore microfono: " + event.error;
  };

  recognition.start();
}


function exportBackup() {
  const data = JSON.stringify(loadStudents(), null, 2);
  const blob = new Blob([data], {type: "application/json"});
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = "jarvis_lezioni_private_backup.json";
  a.click();

  URL.revokeObjectURL(url);
}


function importBackup(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();

  reader.onload = function() {
    try {
      const data = JSON.parse(reader.result);
      if (!Array.isArray(data)) throw new Error("Formato non valido");

      const clean = data.map(normalizeStudent);
      saveStudents(clean);
      addMessage("jarvis", "Backup lezioni private importato.");
    } catch (_) {
      alert("Il file di backup non è valido.");
    }

    event.target.value = "";
  };

  reader.readAsText(file);
}


renderLessons();
</script>
</body>
</html>
"""

ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string"},
        "action": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": [
                        "none",
                        "add_student",
                        "set_student",
                        "add_lesson_done",
                        "add_payment",
                        "delete_student"
                    ]
                },
                "name": {"type": ["string", "null"]},
                "purchased": {"type": ["number", "null"]},
                "done": {"type": ["number", "null"]},
                "duration_hours": {"type": ["number", "null"]},
                "total_cost": {"type": ["number", "null"]},
                "paid": {"type": ["number", "null"]},
                "amount": {"type": ["number", "null"]},
                "notes": {"type": ["string", "null"]}
            },
            "required": [
                "type",
                "name",
                "purchased",
                "done",
                "duration_hours",
                "total_cost",
                "paid",
                "amount",
                "notes"
            ],
            "additionalProperties": False
        }
    },
    "required": ["reply", "action"],
    "additionalProperties": False
}


SYSTEM_INSTRUCTIONS = """
Sei Jarvis, assistente personale italiano di Alessandro per la gestione delle lezioni private.

Hai davanti l'archivio corrente degli allievi, che viene inviato dal browser.
Per ogni allievo possono esserci:
- name: nome
- purchased: lezioni acquistate
- done: lezioni effettuate
- duration_hours: durata di una lezione in ore
- total_cost: costo totale concordato in euro
- paid: importo già incassato in euro
- notes: note

Regole:
1. Rispondi sempre in italiano, in modo pratico, naturale e conciso.
2. Puoi calcolare lezioni residue come purchased - done e insoluto come total_cost - paid.
3. Se l'utente fa una domanda sui dati, rispondi e usa action.type="none".
4. Se l'utente chiede di MODIFICARE i dati, prepara UNA sola azione strutturata.
5. Le modifiche NON sono applicate automaticamente: il browser chiederà conferma all'utente.
6. Se mancano dati indispensabili o il nome è ambiguo, non inventare: action.type="none" e chiedi il dato mancante.
7. "Marco ha fatto una lezione" => add_lesson_done con amount=1.
8. "Marco mi ha pagato 100 euro" => add_payment con amount=100.
9. Per add_student, estrai tutti i dati esplicitamente forniti; ciò che manca può essere 0, durata_hours può essere 1.
10. Non cancellare mai un allievo se l'utente non lo chiede esplicitamente.
"""


@app.get("/")
def home():
    return render_template_string(PAGE)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/chat")
def chat_api():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    students = data.get("students", [])

    if not message:
        return jsonify({"error": "Messaggio vuoto"}), 400

    if not isinstance(students, list):
        students = []

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY non configurata"}), 500

    try:
        client = OpenAI(api_key=api_key)

        model_input = (
            "ARCHIVIO LEZIONI PRIVATE ATTUALE:\n"
            + json.dumps(students, ensure_ascii=False)
            + "\n\nRICHIESTA UTENTE:\n"
            + message
        )

        response = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-5"),
            instructions=SYSTEM_INSTRUCTIONS,
            input=model_input,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "jarvis_private_lessons",
                    "schema": ACTION_SCHEMA,
                    "strict": True
                }
            }
        )

        parsed = json.loads(response.output_text)

        return jsonify({
            "reply": parsed.get("reply", ""),
            "action": parsed.get("action", {"type": "none"})
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
