import os
from flask import Flask, jsonify, request, render_template_string
from openai import OpenAI

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jarvis</title>
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: #0b1020;
      color: white;
      padding: 20px;
    }

    .box {
      max-width: 700px;
      margin: auto;
    }

    #chat {
      background: #111827;
      border-radius: 15px;
      padding: 15px;
      min-height: 300px;
      margin-bottom: 15px;
    }

    .msg {
      padding: 10px;
      margin: 8px 0;
      border-radius: 10px;
    }

    .user {
      background: #1f2937;
    }

    .jarvis {
      background: #172554;
    }

    textarea {
      width: 100%;
      min-height: 60px;
      border-radius: 10px;
      padding: 10px;
      box-sizing: border-box;
    }

    button {
      margin-top: 10px;
      padding: 14px 18px;
      border: none;
      border-radius: 10px;
      background: #2563eb;
      color: white;
      font-size: 16px;
    }

    #mic {
      margin-left: 8px;
    }
  </style>
</head>

<body>
  <div class="box">
    <h1>Jarvis</h1>

    <div id="chat">
      <div class="msg jarvis">
        Sono online. Scrivimi oppure premi il microfono.
      </div>
    </div>

    <textarea id="text" placeholder="Scrivi a Jarvis..."></textarea>

    <button onclick="sendMessage()">Invia</button>
    <button id="mic" onclick="startVoice()">🎙️ Parla</button>
  </div>

<script>
async function sendMessage() {
  const input = document.getElementById("text");
  const message = input.value.trim();

  if (!message) return;

  addMessage("user", message);
  input.value = "";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: message
      })
    });

    const data = await response.json();

    if (data.reply) {
      addMessage("jarvis", data.reply);
      speak(data.reply);
    } else {
      addMessage("jarvis", data.error || "Errore sconosciuto");
    }

  } catch (error) {
    addMessage("jarvis", "Errore di connessione.");
  }
}

function addMessage(type, text) {
  const chat = document.getElementById("chat");
  const div = document.createElement("div");

  div.className = "msg " + type;
  div.textContent = text;

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function speak(text) {
  if (!("speechSynthesis" in window)) return;

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "it-IT";

  speechSynthesis.cancel();
  speechSynthesis.speak(utterance);
}

function startVoice() {
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    alert("Il riconoscimento vocale non è supportato da questo browser.");
    return;
  }

  const recognition = new SpeechRecognition();

  recognition.lang = "it-IT";
  recognition.interimResults = false;

  recognition.onresult = function(event) {
    const text = event.results[0][0].transcript;

    document.getElementById("text").value = text;
    sendMessage();
  };

  recognition.start();
}
</script>

</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(PAGE)

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json() or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Messaggio vuoto"}), 400

    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        return jsonify({
            "error": "OPENAI_API_KEY non configurata"
        }), 500

    try:
        client = OpenAI(api_key=api_key)

        response = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-5"),
            input=message,
            instructions=(
                "Sei Jarvis, un assistente personale italiano. "
                "Rispondi in italiano, in modo pratico, chiaro e conciso."
            )
        )

        return jsonify({
            "reply": response.output_text
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
