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
      max-height: 55vh;
      overflow-y: auto;
      margin-bottom: 15px;
    }

    .msg {
      padding: 10px;
      margin: 8px 0;
      border-radius: 10px;
      line-height: 1.4;
      white-space: pre-wrap;
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
      font-size: 16px;
    }

    .buttons {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    button {
      margin-top: 10px;
      padding: 14px 18px;
      border: none;
      border-radius: 10px;
      background: #2563eb;
      color: white;
      font-size: 16px;
      font-weight: bold;
    }

    #mic.listening {
      background: #b91c1c;
    }

    #voiceBtn.enabled {
      background: #15803d;
    }

    #status {
      margin-top: 12px;
      color: #aab4c5;
      min-height: 20px;
      font-size: 14px;
    }
  </style>
</head>

<body>

<div class="box">

  <h1>Jarvis</h1>

  <div id="chat">
    <div class="msg jarvis">
      Sono online. Prima premi 🔊 Attiva voce, poi puoi parlarmi.
    </div>
  </div>

  <textarea
    id="text"
    placeholder="Scrivi a Jarvis..."
  ></textarea>

  <div class="buttons">

    <button onclick="sendMessage()">
      Invia
    </button>

    <button
      id="mic"
      onclick="startVoice()"
    >
      🎙️ Parla
    </button>

    <button
      id="voiceBtn"
      onclick="toggleVoice()"
    >
      🔊 Attiva voce
    </button>

  </div>

  <div id="status"></div>

</div>


<script>

const chat = document.getElementById("chat");
const input = document.getElementById("text");
const micButton = document.getElementById("mic");
const voiceButton = document.getElementById("voiceBtn");
const statusBox = document.getElementById("status");

let voiceEnabled = false;
let italianVoice = null;
let recognition = null;
let pendingVoiceMessage = null;


/* =========================================
   CARICAMENTO VOCI DEL TELEFONO
   ========================================= */

function loadVoices() {

  if (!("speechSynthesis" in window)) {
    return;
  }

  const voices = window.speechSynthesis.getVoices();

  italianVoice =
    voices.find(v => v.lang === "it-IT") ||
    voices.find(v => v.lang && v.lang.toLowerCase().startsWith("it")) ||
    null;
}


if ("speechSynthesis" in window) {

  loadVoices();

  window.speechSynthesis.onvoiceschanged = function() {
    loadVoices();
  };
}


/* =========================================
   ATTIVAZIONE VOCE
   ========================================= */

function toggleVoice() {

  if (!("speechSynthesis" in window)) {

    alert(
      "La sintesi vocale non è supportata da questo browser."
    );

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

  const test =
    new SpeechSynthesisUtterance("Voce attivata.");

  test.lang = "it-IT";

  if (italianVoice) {
    test.voice = italianVoice;
  }

  test.volume = 1;
  test.rate = 1;
  test.pitch = 1;

  window.speechSynthesis.speak(test);

  statusBox.textContent =
    "Voce attivata.";
}


/* =========================================
   JARVIS PARLA
   ========================================= */

function speak(text) {

  if (!voiceEnabled) {
    return;
  }

  if (!("speechSynthesis" in window)) {
    return;
  }

  if (!text) {
    return;
  }


  window.speechSynthesis.cancel();
  window.speechSynthesis.resume();

  const utterance =
    new SpeechSynthesisUtterance(text);

  utterance.lang = "it-IT";

  if (italianVoice) {
    utterance.voice = italianVoice;
  }

  utterance.volume = 1;
  utterance.rate = 1;
  utterance.pitch = 1;


  utterance.onstart = function() {

    statusBox.textContent =
      "Jarvis sta parlando...";
  };


  utterance.onend = function() {

    statusBox.textContent = "";
  };


  utterance.onerror = function(event) {

    statusBox.textContent =
      "Errore voce: " + event.error;
  };


  /*
  Piccolo ritardo utile soprattutto
  sui browser dei telefoni.
  */

  setTimeout(function() {

    window.speechSynthesis.resume();
    window.speechSynthesis.speak(utterance);

  }, 200);
}


/* =========================================
   MESSAGGI NELLA CHAT
   ========================================= */

function addMessage(type, text) {

  const div =
    document.createElement("div");

  div.className =
    "msg " + type;

  div.textContent =
    text;

  chat.appendChild(div);

  chat.scrollTop =
    chat.scrollHeight;
}


/* =========================================
   INVIO A JARVIS
   ========================================= */

async function sendMessage(forcedMessage = null) {

  const message =
    forcedMessage !== null
      ? forcedMessage.trim()
      : input.value.trim();


  if (!message) {
    return;
  }


  addMessage(
    "user",
    message
  );


  input.value = "";

  statusBox.textContent =
    "Jarvis sta pensando...";


  try {

    const response =
      await fetch("/api/chat", {

        method: "POST",

        headers: {
          "Content-Type":
            "application/json"
        },

        body: JSON.stringify({
          message: message
        })

      });


    const data =
      await response.json();


    if (data.reply) {

      addMessage(
        "jarvis",
        data.reply
      );

      statusBox.textContent = "";

      speak(
        data.reply
      );

    }

    else {

      const errorText =
        data.error ||
        "Errore sconosciuto.";

      addMessage(
        "jarvis",
        errorText
      );

      statusBox.textContent = "";
    }

  }

  catch (error) {

    addMessage(
      "jarvis",
      "Errore di connessione."
    );

    statusBox.textContent = "";
  }
}


/* =========================================
   INVIO CON TASTO ENTER
   ========================================= */

input.addEventListener(
  "keydown",
  function(event) {

    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {

      event.preventDefault();

      sendMessage();
    }
  }
);


/* =========================================
   RICONOSCIMENTO VOCALE
   ========================================= */

function startVoice() {

  const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;


  if (!SpeechRecognition) {

    alert(
      "Il riconoscimento vocale non è supportato da questo browser."
    );

    return;
  }


  /*
  Se la voce non è stata ancora
  attivata, avvisiamo l'utente.
  */

  if (!voiceEnabled) {

    statusBox.textContent =
      "Prima premi 🔊 Attiva voce.";

    return;
  }


  recognition =
    new SpeechRecognition();


  recognition.lang =
    "it-IT";

  recognition.interimResults =
    false;

  recognition.continuous =
    false;


  recognition.onstart =
    function() {

      pendingVoiceMessage =
        null;

      micButton.textContent =
        "🎙️ Ti ascolto...";

      micButton.classList.add(
        "listening"
      );

      statusBox.textContent =
        "Sto ascoltando...";
    };


  recognition.onresult =
    function(event) {

      const spokenText =
        event.results[0][0].transcript;

      pendingVoiceMessage =
        spokenText;

      input.value =
        spokenText;

      statusBox.textContent =
        "Ho sentito: " + spokenText;
    };


  /*
  Aspettiamo che il microfono
  sia realmente chiuso prima
  di chiedere a Jarvis la risposta.

  Questo evita conflitti audio
  su molti telefoni.
  */

  recognition.onend =
    function() {

      micButton.textContent =
        "🎙️ Parla";

      micButton.classList.remove(
        "listening"
      );


      if (pendingVoiceMessage) {

        const message =
          pendingVoiceMessage;

        pendingVoiceMessage =
          null;

        sendMessage(message);
      }
  };


  recognition.onerror =
    function(event) {

      micButton.textContent =
        "🎙️ Parla";

      micButton.classList.remove(
        "listening"
      );

      statusBox.textContent =
        "Errore microfono: " +
        event.error;
    };


  recognition.start();
}

</script>

</body>
</html>
"""


@app.route("/")
def home():

    return render_template_string(
        PAGE
    )


@app.route(
    "/api/chat",
    methods=["POST"]
)
def chat():

    data =
        request.get_json(
            silent=True
        ) or {}

    message =
        str(
            data.get(
                "message",
                ""
            )
        ).strip()


    if not message:

        return jsonify({
            "error":
            "Messaggio vuoto"
        }), 400


    api_key =
        os.environ.get(
            "OPENAI_API_KEY"
        )


    if not api_key:

        return jsonify({
            "error":
            "OPENAI_API_KEY non configurata"
        }), 500


    try:

        client =
            OpenAI(
                api_key=api_key
            )


        response =
            client.responses.create(

                model=
                    os.environ.get(
                        "OPENAI_MODEL",
                        "gpt-5"
                    ),

                input=
                    message,

                instructions=(
                    "Sei Jarvis, un assistente personale italiano. "
                    "Rispondi sempre in italiano. "
                    "Sii pratico, chiaro, naturale e conciso. "
                    "Dato che spesso la risposta verrà letta ad alta voce, "
                    "evita formattazioni inutili e risposte eccessivamente lunghe."
                )
            )


        reply =
            response.output_text


        return jsonify({
            "reply":
            reply
        })


    except Exception as e:

        return jsonify({
            "error":
            str(e)
        }), 500


if __name__ == "__main__":

    port =
        int(
            os.environ.get(
                "PORT",
                10000
            )
        )

    app.run(
        host="0.0.0.0",
        port=port
    )
