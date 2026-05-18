/**
 * Newsletter cines — Google Apps Script.
 *
 * Hace dos cosas:
 *   1) Endpoint POST público (doPost) que recibe {email} del form de sitedigo
 *      y lo agrega a la primera hoja del Spreadsheet activo.
 *   2) Función sendNewsletter() que se dispara con un time-trigger todos los
 *      jueves a las 9 AM (configurás abajo). Lee la cartelera de GitHub,
 *      arma el HTML día por día y manda un mail a cada suscriptor.
 *
 * ──────────────────────────────────────────────────────────────────────
 * SETUP (one-time):
 *   1. Crear un Google Sheet nuevo. La primera hoja debe tener en A1:
 *        email
 *      (después se llena con cada suscripción)
 *   2. Extensions → Apps Script → pegar TODO este archivo
 *   3. Configurar abajo CARTELERA_URL y FROM_NAME
 *   4. Deploy → New deployment:
 *        - Type: Web app
 *        - Execute as: Me
 *        - Who has access: Anyone
 *      Copiar el "Web app URL" → pegarlo en index.html como APPS_SCRIPT_URL
 *   5. Triggers (reloj a la izquierda) → Add trigger:
 *        - Function: sendNewsletter
 *        - Source: Time-driven → Week timer → Thursday → 9 AM-10 AM
 *
 * Eso es todo. El form de sitedigo va a appendear a la sheet, y todos los
 * jueves a las 9 AM-10 AM Apps Script va a mandar el newsletter automático.
 * ──────────────────────────────────────────────────────────────────────
 */

// ⚙️ Config — cambiá esto antes de deployar
const CARTELERA_URL = "https://raw.githubusercontent.com/allerand/cines/main/data/cartelera.json";
const FROM_NAME = "Cartelera de cines"; // aparece como "Cartelera de cines <tu@gmail.com>"
const SUBJECT_PREFIX = "Cartelera de cine — semana";

// Localización
const DAYS_ES = ["lunes","martes","miércoles","jueves","viernes","sábado","domingo"];
const MONTHS_ES = ["enero","febrero","marzo","abril","mayo","junio",
                   "julio","agosto","septiembre","octubre","noviembre","diciembre"];


// ───── 1. Endpoint del form ────────────────────────────────────────────
function doPost(e) {
  try {
    let email = "";
    if (e.parameter && e.parameter.email) {
      email = e.parameter.email;
    } else if (e.postData && e.postData.contents) {
      try { email = JSON.parse(e.postData.contents).email || ""; } catch (_) {}
    }
    email = String(email).trim().toLowerCase();
    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return _json({ ok: false, error: "invalid_email" });
    }
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    const data = sheet.getDataRange().getValues();
    const emails = new Set(data.slice(1).map(r => String(r[0] || "").trim().toLowerCase()));
    if (!emails.has(email)) {
      sheet.appendRow([email, new Date()]);
    }
    return _json({ ok: true });
  } catch (err) {
    return _json({ ok: false, error: String(err) });
  }
}

function doOptions(e) {
  return ContentService.createTextOutput("");
}

function _json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}


// ───── 2. Envío semanal ─────────────────────────────────────────────────
function sendNewsletter() {
  const weekStart = _nextOrSameMonday(new Date());
  const weekEnd = new Date(weekStart);
  weekEnd.setDate(weekEnd.getDate() + 6);

  // Bajar cartelera
  const res = UrlFetchApp.fetch(CARTELERA_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    Logger.log("Cartelera fetch fail: " + res.getResponseCode());
    return;
  }
  const data = JSON.parse(res.getContentText());
  const screenings = data.screenings || [];

  const html = _buildEmailHtml(weekStart, weekEnd, screenings);
  const subject = SUBJECT_PREFIX + " " + _captionDates(weekStart, weekEnd);

  // Cargar suscriptores
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  const rows = sheet.getDataRange().getValues();
  const emails = rows.slice(1)
    .map(r => String(r[0] || "").trim())
    .filter(e => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e));

  Logger.log("Sending '" + subject + "' to " + emails.length + " subscribers");
  for (const email of emails) {
    try {
      MailApp.sendEmail({
        to: email,
        subject: subject,
        htmlBody: html,
        name: FROM_NAME,
      });
    } catch (err) {
      Logger.log("Fail " + email + ": " + err);
    }
  }
}

function _nextOrSameMonday(d) {
  const r = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  // getDay: 0=Sun, 1=Mon...
  const dow = r.getDay();
  const diff = dow === 0 ? 1 : (dow === 1 ? 0 : 8 - dow);
  r.setDate(r.getDate() + diff);
  return r;
}

function _captionDates(start, end) {
  const mS = MONTHS_ES[start.getMonth()];
  const mE = MONTHS_ES[end.getMonth()];
  if (start.getMonth() === end.getMonth()) {
    return "del " + start.getDate() + " al " + end.getDate() + " de " + mS;
  }
  return "del " + start.getDate() + " de " + mS + " al " + end.getDate() + " de " + mE;
}

function _isoDate(d) {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return d.getFullYear() + "-" + m + "-" + day;
}

function _escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function _buildEmailHtml(weekStart, weekEnd, screenings) {
  const when = _captionDates(weekStart, weekEnd);
  const weekSet = new Set();
  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart); d.setDate(d.getDate() + i);
    weekSet.add(_isoDate(d));
  }
  const byDay = {};
  for (const s of screenings) {
    if (weekSet.has(s.fecha)) {
      (byDay[s.fecha] = byDay[s.fecha] || []).push(s);
    }
  }
  for (const k of Object.keys(byDay)) {
    byDay[k].sort((a, b) => (a.hora || "99").localeCompare(b.hora || "99"));
  }

  const parts = [
    '<div style="font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',system-ui,sans-serif;'
    + ' max-width:640px;margin:0 auto;color:#1a1a1a;line-height:1.5;">',
    '<h1 style="font-size:20px;font-weight:700;margin:0 0 6px;">Cartelera de cine</h1>',
    '<p style="margin:0 0 24px;color:#666;font-size:14px;">'
    + 'Programación de las salas de cine de la ciudad, semana ' + _escapeHtml(when) + '.</p>',
  ];

  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart); d.setDate(d.getDate() + i);
    const iso = _isoDate(d);
    const films = byDay[iso] || [];
    const dayName = DAYS_ES[(d.getDay() + 6) % 7];
    parts.push(
      '<h2 style="font-size:14px;font-weight:700;letter-spacing:0.06em;'
      + 'text-transform:uppercase;margin:24px 0 8px;color:#1a1a1a;'
      + 'border-bottom:1px solid #e0e0e0;padding-bottom:4px;">'
      + _escapeHtml(dayName + " " + d.getDate() + " de " + MONTHS_ES[d.getMonth()])
      + '<span style="float:right;font-weight:400;color:#999;">' + films.length + ' func.</span>'
      + '</h2>'
    );
    if (!films.length) {
      parts.push('<p style="margin:6px 0;color:#999;font-size:14px;">— sin funciones —</p>');
      continue;
    }
    parts.push('<ul style="list-style:none;padding:0;margin:0;font-size:14px;">');
    for (const s of films) {
      const title = s.title_es || s.title_en || "(sin título)";
      const metaExtras = [];
      if (s.director) metaExtras.push(s.director);
      if (s.year) metaExtras.push(s.year);
      if (s.duration) metaExtras.push(s.duration + " min");
      const metaStr = metaExtras.join(" · ");
      const lb = s.letterboxd || "";
      const titleHtml = lb
        ? '<a href="' + _escapeHtml(lb) + '" style="color:#1a1a1a;text-decoration:none;border-bottom:1px solid #999;">' + _escapeHtml(title) + '</a>'
        : _escapeHtml(title);
      parts.push(
        '<li style="padding:6px 0;border-bottom:1px solid #f0f0f0;">'
        + '<strong style="display:inline-block;width:54px;color:#333;">' + _escapeHtml(s.hora || "??") + '</strong>'
        + ' <span style="font-size:11px;color:#777;text-transform:uppercase;letter-spacing:0.04em;'
        + 'border:1px solid #ddd;padding:1px 6px;border-radius:3px;margin-right:6px;">'
        + _escapeHtml(s.cine || "") + '</span> '
        + titleHtml
        + (metaStr ? '<div style="margin-left:54px;color:#777;font-size:13px;">' + _escapeHtml(metaStr) + '</div>' : '')
        + '</li>'
      );
    }
    parts.push('</ul>');
  }

  parts.push(
    '<hr style="border:none;border-top:1px solid #e0e0e0;margin:32px 0 12px;">'
    + '<p style="margin:0;font-size:12px;color:#999;">'
    + 'Todas las funciones también en '
    + '<a href="https://sitedigo.com" style="color:#1a1a1a;">sitedigo.com</a> · '
    + '<a href="https://instagram.com/sitedigocine" style="color:#1a1a1a;">@sitedigocine</a> en Instagram.'
    + '</p></div>'
  );
  return parts.join("");
}


// ───── 3. Tests útiles ────────────────────────────────────────────────
// Correr a mano desde Apps Script editor para verificar antes del trigger.
function previewNewsletter() {
  const weekStart = _nextOrSameMonday(new Date());
  const weekEnd = new Date(weekStart); weekEnd.setDate(weekEnd.getDate() + 6);
  const res = UrlFetchApp.fetch(CARTELERA_URL + "?t=" + Date.now());
  const data = JSON.parse(res.getContentText());
  const html = _buildEmailHtml(weekStart, weekEnd, data.screenings || []);
  Logger.log("subject: " + SUBJECT_PREFIX + " " + _captionDates(weekStart, weekEnd));
  Logger.log("body len: " + html.length);
  // Mandate a vos mismo para probar visualmente
  MailApp.sendEmail({
    to: Session.getActiveUser().getEmail(),
    subject: "[PREVIEW] " + SUBJECT_PREFIX + " " + _captionDates(weekStart, weekEnd),
    htmlBody: html,
    name: FROM_NAME,
  });
  Logger.log("Preview enviado a " + Session.getActiveUser().getEmail());
}
