<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>🎬 Smart Movie Advisor</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      background: linear-gradient(to bottom right, #141e30, #243b55);
      height: 100vh;
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .chat-container {
      background: white;
      border-radius: 15px;
      width: 95%;
      max-width: 480px;
      height: 90vh;
      display: flex;
      flex-direction: column;
      padding: 20px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.4);
    }
    #chatbox {
      flex: 1;
      overflow-y: auto;
      margin-bottom: 10px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .message {
      padding: 12px 16px;
      border-radius: 18px;
      max-width: 75%;
      word-wrap: break-word;
      animation: fadeIn 0.3s ease;
    }
    .user { background: #e0f7fa; align-self: flex-start; }
    .bot { background: #dcedc8; align-self: flex-end; }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(5px); }
      to { opacity: 1; transform: translateY(0); }
    }

    #controls {
      display: flex;
      gap: 10px;
    }
    input {
      flex: 1;
      padding: 12px;
      border-radius: 999px;
      border: 1px solid #ccc;
      font-size: 16px;
    }
    button {
      padding: 12px 16px;
      border: none;
      border-radius: 999px;
      background: #4caf50;
      color: white;
      font-weight: bold;
      cursor: pointer;
    }
    .option-buttons {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
    }
    .option-buttons button {
      background: #2196f3;
      color: white;
      border: none;
      padding: 8px 12px;
      border-radius: 20px;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <div class="chat-container">
    <div id="chatbox"></div>
    <div id="controls">
      <input id="message" placeholder="Type a message..." onkeydown="if(event.key==='Enter') sendMessage()" />
      <button onclick="sendMessage()">Send</button>
    </div>
  </div>

  <script>
    let conversation = []
    const chatbox = document.getElementById("chatbox");

    function appendMessage(text, type = "bot") {
      const msg = document.createElement("div");
      msg.className = `message ${type}`;
      msg.textContent = text;
      chatbox.appendChild(msg);
      chatbox.scrollTop = chatbox.scrollHeight;
    }

    function appendOptions(tag) {
      const container = document.createElement("div");
      container.className = "option-buttons";

      let options = [];

      if (tag === "[[ASK_GENRE]]") {
        options = ["Action", "Comedy", "Drama", "Horror", "Romance", "Thriller", "Animation", "Adventure", "Fantasy"];
      } else if (tag === "[[ASK_LENGTH]]") {
        options = ["Short (up to 90 min)", "Medium (91-120 min)", "Long (over 120 min)"];
      } else if (tag === "[[ASK_ADULT]]") {
        options = ["All Audiences", "Adults Only"];
      }

      options.forEach(opt => {
        const btn = document.createElement("button");
        btn.textContent = opt;
        btn.onclick = () => {
          container.remove();
          appendMessage(opt, "user");
          conversation.push({ role: "user", content: opt });
          fetchResponse(opt);
        };
        container.appendChild(btn);
      });

      chatbox.appendChild(container);
      chatbox.scrollTop = chatbox.scrollHeight;
    }

    async function sendMessage() {
      const input = document.getElementById("message");
      const message = input.value.trim();
      if (!message) return;

      appendMessage(message, "user");
      conversation.push({ role: "user", content: message });
      input.value = "";

      await fetchResponse(message);
    }

    async function fetchResponse(message) {
      try {
        const res = await fetch("https://chatbot-proxy-4g5l.onrender.com/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: conversation })
        });

        const data = await res.json();
        const reply = data.response;

        if (["[[ASK_GENRE]]", "[[ASK_LENGTH]]", "[[ASK_ADULT]]"].includes(reply)) {
          appendMessage("Please choose:", "bot");
          appendOptions(reply);
        } else {
          appendMessage(reply, "bot");
          conversation.push({ role: "assistant", content: reply });
        }
      } catch (err) {
        appendMessage("⚠️ Error connecting to server.", "bot");
      }
    }
  </script>
</body>
</html>
