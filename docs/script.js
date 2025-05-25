const formEl = document.querySelector("form");
const inputEl = document.querySelector("input");
const chatEl = document.querySelector("#chat");

function appendLine(text) {
  const line = document.createElement("div");
  line.textContent = text;
  chatEl.appendChild(line);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function replaceLastLine(text) {
  const lastLine = chatEl.lastChild;
  if (lastLine) {
    lastLine.textContent = text;
  }
}

formEl.addEventListener("submit", async e => {
  e.preventDefault();
  const userText = inputEl.value.trim();
  if (!userText) return;
  inputEl.value = "";

  appendLine(`You: ${userText}`);

  appendLine("AI: …");
  const aiText = await fetchAI(userText);
  replaceLastLine(`AI: ${aiText}`);
});

async function fetchAI(prompt) {
  const res = await fetch("https://api-inference.huggingface.co/models/google/gemma-2b-it", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${HF_TOKEN}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      inputs: prompt,
      parameters: { max_new_tokens: 128, temperature: 0.7 }
    })
  });
  const data = await res.json();
  let output = "[error]";
  if (Array.isArray(data)) {
    output = (data[0]?.generated_text || output).replace(prompt, "").trim();
  } else if (data?.generated_text) {
    output = data.generated_text.replace(prompt, "").trim();
  }
  return output;
}
