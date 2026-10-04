import os
import json
from flask import Flask, jsonify, request, render_template_string
from openai import OpenAI

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Jarvis - Lezioni Private</title>
<style>
body{margin:0;background:#08111f;color:#fff;font-family:Arial,sans-serif;padding:18px}
.wrap{max-width:760px;margin:auto}.card{background:#101b2d;border:1px solid #263750;border-radius:16px;padding:14px;margin:12px 0}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}.stat{background:#16243a;padding:12px;border-radius:12px}.stat b{display:block;font-size:21px}
button{background:#2f6fed;color:#fff;border:0;border-radius:10px;padding:12px;font-size:15px;font-weight:bold;margin:4px}
input,textarea{width:100%;box-sizing:border-box;background:#0c1627;color:#fff;border:1px solid #263750;border-radius:10px;padding:12px;margin:5px 0;font-size:16px}
.tabs{display:flex;gap:5px;overflow:auto}.tab{background:#16243a}.active{background:#2f6fed}.view{display:none}.view.on{display:block}
.item{border-bottom:1px solid #263750;padding:12px 0}.small{color:#9baac0;font-size:13px}.chat{height:280px;overflow:auto;background:#0c1627;border-radius:12px;padding:10px}
.msg{padding:9px;border-radius:10px;margin:7px 0}.me{background:#1d2b40}.ai{background:#162a55}.confirm{border:1px solid #b78b35;background:#2b2415}
@media(min-width:650px){.grid{grid-template-columns:repeat(4,1fr)}}
</style></head>
<body><div class="wrap">
<h1>Jarvis</h1><div class="small">Agente - Lezioni Private</div>
<div class="tabs">
<button class="tab active" onclick="tab('oggi',this)">Oggi</button>
<button class="tab" onclick="tab('allievi',this)">Allievi</button>
<button class="tab" onclick="tab('nuovo',this)">Nuovo</button>
<button class="tab" onclick="tab('jarvis',this)">Jarvis</button>
</div>
<div id="oggi" class="view on"><div id="stats" class="grid card"></div><div class="card"><b>Da controllare</b><div id="alerts"></div></div><div class="card"><b>Storico</b><div id="history"></div></div></div>
<div id="allievi" class="view"><div class="card"><input id="search" placeholder="Cerca allievo" oninput="renderStudents()"><div id="students"></div></div></div>
<div id="nuovo" class="view"><div class="card"><b>Nuovo allievo</b><input id="name" placeholder="Nome"><input id="total" type="number" placeholder="Lezioni acquistate"><input id="duration" type="number" step=".25" placeholder="Ore per lezione"><input id="price" type="number" step=".01" placeholder="Costo totale euro"><input id="paid" type="number" step=".01" placeholder="Gia incassato euro"><textarea id="notes" placeholder="Note / recuperi / accordi"></textarea><button onclick="prepareNew()">Prepara inserimento</button></div><div id="newConfirm"></div></div>
<div id="jarvis" class="view"><div class="card"><button id="voice" onclick="voiceToggle()">🔊 Attiva voce</button><div id="chat" class="chat"><div class="msg ai">Dimmi cosa vuoi sapere o registrare.</div></div><textarea id="ask" placeholder="Es. Marco ha fatto una lezione"></textarea><button onclick="askAI()">Invia</button><button id="mic" onclick="listen()">🎙️ Parla</button></div><div id="aiConfirm"></div></div>
</div>
<script>
const KEY="jarvis_lessons_v1";let db=JSON.parse(localStorage.getItem(KEY)||'{"students":[],"events":[]}'),pending=null,voiceOn=false;
const E=id=>document.getElementById(id), euro=n=>new Intl.NumberFormat("it-IT",{style:"currency",currency:"EUR"}).format(+n||0);
function tab(id,b){document.querySelectorAll(".view").forEach(x=>x.classList.remove("on"));document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));E(id).classList.add("on");b.classList.add("active")}
function save(){localStorage.setItem(KEY,JSON.stringify(db));render()}
function log(t){db.events.push({text:t,when:new Date().toLocaleString("it-IT")})}
function render(){let left=0,due=0,inc=0;db.students.forEach(s=>{left+=Math.max(0,s.total-s.done);due+=Math.max(0,s.price-s.paid);inc+=s.paid});E("stats").innerHTML=[["Allievi",db.students.length],["Lezioni residue",left],["Incassato",euro(inc)],["Da incassare",euro(due)]].map(x=>`<div class="stat"><b>${x[1]}</b><span>${x[0]}</span></div>`).join("");let a=[];db.students.forEach(s=>{let l=Math.max(0,s.total-s.done),d=Math.max(0,s.price-s.paid);if(l<=1&&s.total)a.push(`<div class="item">⚠️ ${s.name}: ${l} lezioni residue</div>`);if(d>0)a.push(`<div class="item">💶 ${s.name}: ${euro(d)} da incassare</div>`)});E("alerts").innerHTML=a.join("")||'<div class="small">Nessun avviso.</div>';E("history").innerHTML=db.events.slice(-10).reverse().map(e=>`<div class="item">${e.text}<div class="small">${e.when}</div></div>`).join("")||'<div class="small">Nessuna attivita.</div>';renderStudents()}
function renderStudents(){let q=E("search").value.toLowerCase();E("students").innerHTML=db.students.filter(s=>s.name.toLowerCase().includes(q)).map(s=>`<div class="item"><b>${s.name}</b><div>${s.done}/${s.total} fatte - ${Math.max(0,s.total-s.done)} residue</div><div>${euro(s.paid)} incassati - ${euro(Math.max(0,s.price-s.paid))} da incassare</div><div class="small">${s.notes||""}</div><button onclick="lesson('${s.id}')">+ Lezione</button><button onclick="payment('${s.id}')">+ Pagamento</button></div>`).join("")||'<div class="small">Nessun allievo.</div>'}
function box(target,title,html,fn){pending=fn;E(target).innerHTML=`<div class="card confirm"><b>${title}</b><p>${html}</p><button onclick="confirmIt('${target}')">Conferma</button><button onclick="cancelIt('${target}')">Annulla</button></div>`}
function confirmIt(t){if(pending)pending();pending=null;E(t).innerHTML=""}function cancelIt(t){pending=null;E(t).innerHTML=""}
function prepareNew(){let s={id:String(Date.now()),name:E("name").value.trim(),total:+E("total").value||0,done:0,duration:+E("duration").value||1,price:+E("price").value||0,paid:+E("paid").value||0,notes:E("notes").value.trim()};if(!s.name)return alert("Inserisci il nome");box("newConfirm","Conferma",`${s.name}: ${s.total} lezioni, totale ${euro(s.price)}, incassato ${euro(s.paid)}`,()=>{db.students.push(s);log("Inserito "+s.name);save()})}
function find(id){return db.students.find(s=>s.id===id)}
function lesson(id){let s=find(id);box("aiConfirm","Conferma lezione",`Registrare una lezione per ${s.name}?`,()=>{s.done=Math.min(s.total,s.done+1);log(s.name+": 1 lezione");save()});E("jarvis").classList.add("on")}
function payment(id){let s=find(id),v=prompt("Importo incassato");if(v===null)return;let n=Number(v.replace(",","."));if(!(n>0))return;box("aiConfirm","Conferma pagamento",`Registrare ${euro(n)} da ${s.name}?`,()=>{s.paid+=n;log(s.name+": incassati "+euro(n));save()})}
function msg(c,t){let d=document.createElement("div");d.className="msg "+c;d.textContent=t;E("chat").appendChild(d);E("chat").scrollTop=E("chat").scrollHeight}
function snap(){return db.students.map(s=>({...s,residue:Math.max(0,s.total-s.done),da_incassare:Math.max(0,s.price-s.paid)}))}
async function askAI(){let m=E("ask").value.trim();if(!m)return;E("ask").value="";msg("me",m);try{let r=await fetch("/api/lessons",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:m,students:snap()})}),d=await r.json();msg("ai",d.reply||d.error||"Errore");if(voiceOn&&d.reply)speak(d.reply);if(d.action)action(d.action)}catch(e){msg("ai","Errore di connessione.")}}
function byName(n){n=(n||"").toLowerCase();return db.students.find(s=>s.name.toLowerCase()===n)||db.students.find(s=>s.name.toLowerCase().includes(n))}
function action(a){let s=byName(a.student);if(a.type==="lesson_done"&&s)box("aiConfirm","Jarvis propone",`Registrare ${a.quantity||1} lezione/i per ${s.name}?`,()=>{s.done=Math.min(s.total,s.done+(+a.quantity||1));log(s.name+": lezione registrata");save()});else if(a.type==="payment"&&s)box("aiConfirm","Jarvis propone",`Registrare ${euro(a.amount)} da ${s.name}?`,()=>{s.paid+=+a.amount;log(s.name+": pagamento "+euro(a.amount));save()});else if(a.type==="add_student"){let s={id:String(Date.now()),name:a.student,total:+a.total||0,done:+a.done||0,duration:+a.duration||1,price:+a.price||0,paid:+a.paid||0,notes:a.notes||""};box("aiConfirm","Jarvis propone",`Aggiungere ${s.name}: ${s.total} lezioni, ${euro(s.price)}, incassato ${euro(s.paid)}?`,()=>{db.students.push(s);log("Inserito "+s.name);save()})}}
function voiceToggle(){voiceOn=!voiceOn;E("voice").textContent=voiceOn?"🔊 Voce attiva":"🔊 Attiva voce";if(voiceOn)speak("Voce attivata")}
function speak(t){if(!("speechSynthesis" in window))return;speechSynthesis.cancel();let u=new SpeechSynthesisUtterance(t);u.lang="it-IT";speechSynthesis.speak(u)}
function listen(){let SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return alert("Riconoscimento vocale non supportato");let r=new SR();r.lang="it-IT";r.onresult=e=>E("ask").value=e.results[0][0].transcript;r.onend=()=>{if(E("ask").value.trim())askAI()};r.start()}
render();
</script></body></html>
"""

@app.route("/")
def home():
    return render_template_string(PAGE)

@app.route("/api/lessons", methods=["POST"])
def lessons():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    students = data.get("students", [])
    if not message:
        return jsonify({"error": "Messaggio vuoto"}), 400
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return jsonify({"error": "OPENAI_API_KEY non configurata"}), 500
    instructions = (
        "Sei Jarvis, agente gestionale per lezioni private. Rispondi in italiano, breve e preciso. "
        "Usa solo i dati forniti e non inventare. Se l'utente chiede informazioni, action=null. "
        "Per modifiche proponi una sola azione senza dichiararla eseguita. "
        "Azioni: lesson_done(student,quantity), payment(student,amount), "
        "add_student(student,total,done,duration,price,paid,notes). "
        "Se mancano dati chiedili e action=null. "
        'Rispondi esclusivamente JSON valido: {"reply":"testo","action":null} oppure '
        '{"reply":"testo","action":{"type":"...","student":"..."}}.'
    )
    payload = json.dumps({"richiesta": message, "allievi": students}, ensure_ascii=False)
    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-5"),
            instructions=instructions,
            input=payload,
        )
        raw = response.output_text.strip().replace("```json", "").replace("```", "").strip()
        return jsonify(json.loads(raw))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
