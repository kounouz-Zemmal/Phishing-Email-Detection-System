function extractEmailData() {
  const subjectEl = document.querySelector('h2.hP');
  const subject = subjectEl ? subjectEl.innerText : '';

  const bodyEl = document.querySelector('div.a3s.aiL');
  const body = bodyEl ? bodyEl.innerText : '';

  const senderEl = document.querySelector('span.gD');
  const from_email = senderEl ? (senderEl.getAttribute('email') || '') : '';

  const links = bodyEl ? bodyEl.querySelectorAll('a') : [];
  const url_count = links.length;

  const ipPattern = /https?:\/\/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/;
  const urlTexts = Array.from(links).map(a => a.href).join(' ');
  const has_ip_url = ipPattern.test(urlTexts) ? 1 : 0;

  const html_flag = bodyEl && bodyEl.innerHTML !== bodyEl.innerText ? 1 : 0;

  const char_count = body.length;
  const word_count = body.split(/\s+/).filter(Boolean).length;

  return {
    subject,
    body_clean: body,
    from_email,
    url_count,
    has_ip_url,
    html_flag,
    char_count,
    word_count
  };
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'extractEmail') {
    sendResponse(extractEmailData());
  }
});
