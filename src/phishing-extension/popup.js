const btn = document.getElementById('analyze');
const resultDiv = document.getElementById('result');

btn.addEventListener('click', async () => {
  btn.disabled = true;
  btn.textContent = 'Analyzing…';
  resultDiv.style.display = 'none';

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

  chrome.tabs.sendMessage(tab.id, { action: 'extractEmail' }, async (emailData) => {
    if (chrome.runtime.lastError || !emailData) {
      showResult('error', '⚠️ Please open an email in Gmail first.');
      reset();
      return;
    }

    if (!emailData.body_clean && !emailData.subject) {
      showResult('error', '⚠️ No email content found. Click into an email first.');
      reset();
      return;
    }

    try {
      const response = await fetch('https://phishing-email-detection-system.onrender.com/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(emailData)
      });

      if (!response.ok) throw new Error('API error');

      const result = await response.json();
      const pred = result.prediction;                    // ← unwrap nested object

      const riskPct = (pred.phishing_probability * 100).toFixed(1);
      const safePct = ((1 - pred.phishing_probability) * 100).toFixed(1);

      if (pred.label === 'phishing') {
        showResult('phishing', `⚠️ <b>Phishing Detected!</b><div class="confidence">Risk: ${riskPct}% · Level: ${pred.risk_level}</div>`);
      } else {
        showResult('safe', `✅ <b>Email looks safe</b><div class="confidence">Safe score: ${safePct}%</div>`);
      }
    } catch (e) {
      showResult('error', '🔌 Cannot reach API.<br><small>Make sure <code>python app.py</code> is running.</small>');
    }

    reset();
  });
});

function showResult(cls, html) {
  resultDiv.className = cls;
  resultDiv.innerHTML = html;
  resultDiv.style.display = 'block';
}

function reset() {
  btn.disabled = false;
  btn.textContent = 'Analyze Current Email';
}
