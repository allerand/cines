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
const LOGO_URL = "https://raw.githubusercontent.com/allerand/cines/main/logo.png";
const SITE_URL = "https://sitedigo.com";
const BRAND_NAME = "Si te digo producciones";
const FROM_NAME = "Si te digo producciones";
const SUBJECT_PREFIX = "Cartelera de cine — semana";

// Paleta — igual a la web (index.html)
const T_BG       = "#0a0a0a";
const T_BG2      = "#111";
const T_BG3      = "#1a1a1a";
const T_BORDER   = "#2a2a2a";
const T_TEXT     = "#e0e0e0";
const T_MUTED    = "#666";
const T_ACCENT   = "#00d060";
const T_FONT     = "-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif";

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
    // Wrapper full-bleed dark background. Algunos clientes ignoran el body
    // background, así que envolvemos en un <table> con bgcolor.
    '<div style="background:' + T_BG + ';margin:0;padding:0;">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
    + 'width="100%" bgcolor="' + T_BG + '" '
    + 'style="background:' + T_BG + ';border-collapse:collapse;"><tr><td align="center" style="padding:32px 12px;">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="760" '
    + 'style="max-width:760px;width:100%;background:' + T_BG + ';color:' + T_TEXT + ';'
    + 'font-family:' + T_FONT + ';line-height:1.45;text-align:left;">',

    // Header — logo + brand
    '<tr><td style="padding:0 0 22px;border-bottom:1px solid ' + T_BORDER + ';">',
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>',
    '<td valign="middle" style="padding-right:12px;">',
    '<img src="' + LOGO_URL + '" alt="Si te digo" width="48" height="48" '
    + 'style="display:block;width:48px;height:auto;border:0;outline:none;">',
    '</td>',
    '<td valign="middle">',
    '<div style="font-size:18px;font-weight:700;letter-spacing:-0.01em;color:' + T_TEXT + ';">'
    + _escapeHtml(BRAND_NAME) + '</div>',
    '<div style="font-size:12px;color:' + T_MUTED + ';margin-top:2px;">Cartelera semanal — cines · Buenos Aires</div>',
    '</td>',
    '</tr></table>',
    '</td></tr>',

    // Intro
    '<tr><td style="padding:18px 0 4px;">',
    '<div style="font-size:14px;color:' + T_TEXT + ';">'
    + 'Programación de las salas de cine de la ciudad, semana ' + _escapeHtml(when) + '.</div>',
    '</td></tr>',

    // Body container
    '<tr><td style="padding:0 0 24px;">',
  ];

  for (let i = 0; i < 7; i++) {
    const d = new Date(weekStart); d.setDate(d.getDate() + i);
    const iso = _isoDate(d);
    const films = byDay[iso] || [];
    const dayName = DAYS_ES[(d.getDay() + 6) % 7];
    // Header del día — tabla con título a la izq + contador a la der
    parts.push(
      '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
      + 'style="border-collapse:collapse;margin:26px 0 10px;border-bottom:1px solid ' + T_BORDER + ';">'
      + '<tr>'
      + '<td style="font-size:13px;font-weight:700;letter-spacing:0.08em;'
      + 'text-transform:uppercase;color:' + T_ACCENT + ';padding-bottom:6px;">'
      + _escapeHtml(dayName + " " + d.getDate() + " de " + MONTHS_ES[d.getMonth()])
      + '</td>'
      + '<td align="right" style="font-size:11px;color:' + T_MUTED + ';padding-bottom:6px;">'
      + films.length + ' funciones</td>'
      + '</tr></table>'
    );
    if (!films.length) {
      parts.push('<p style="margin:6px 0 0;color:' + T_MUTED + ';font-size:13px;">— sin funciones —</p>');
      continue;
    }
    if (films.length >= 6) {
      const half = Math.ceil(films.length / 2);
      parts.push(_twoColumnFilms(films.slice(0, half), films.slice(half)));
    } else {
      parts.push('<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;">');
      for (const s of films) parts.push(_renderFilmRow(s));
      parts.push('</table>');
    }
  }

  parts.push(
    '</td></tr>',

    // Footer
    '<tr><td style="padding-top:16px;border-top:1px solid ' + T_BORDER + ';">',
    '<div style="font-size:12px;color:' + T_MUTED + ';">'
    + 'Todas las funciones también en '
    + '<a href="' + SITE_URL + '" style="color:' + T_ACCENT + ';text-decoration:none;">sitedigo.com</a> · '
    + '<a href="https://instagram.com/sitedigocine" style="color:' + T_ACCENT + ';text-decoration:none;">@sitedigocine</a> en Instagram.'
    + '</div>',
    '</td></tr>',

    '</table>',          // inner table
    '</td></tr></table>', // outer table
    '</div>',
  );
  return parts.join("");
}


function _twoColumnFilms(left, right) {
  const renderCol = (arr) => {
    const rows = arr.map(_renderFilmRow).join("");
    return '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
      + 'style="border-collapse:collapse;">' + rows + '</table>';
  };
  return (
    '<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" '
    + 'style="border-collapse:collapse;">'
    + '<tr>'
    + '<td valign="top" width="50%" style="padding-right:14px;">' + renderCol(left) + '</td>'
    + '<td valign="top" width="50%" style="padding-left:14px;">' + renderCol(right) + '</td>'
    + '</tr></table>'
  );
}


function _renderFilmRow(s) {
  const title = s.title_es || s.title_en || "(sin título)";
  const meta = [];
  if (s.director) meta.push(s.director);
  if (s.year) meta.push(s.year);
  if (s.duration) meta.push(s.duration + " min");
  const metaStr = meta.join(" · ");
  const lb = s.letterboxd || "";
  const titleHtml = lb
    ? '<a href="' + _escapeHtml(lb) + '" style="color:' + T_TEXT + ';text-decoration:none;border-bottom:1px solid ' + T_BORDER + ';">' + _escapeHtml(title) + '</a>'
    : _escapeHtml(title);
  return (
    '<tr>'
    + '<td valign="top" width="50" style="padding:8px 10px 8px 0;'
    + 'border-bottom:1px solid ' + T_BORDER + ';font-size:13px;font-weight:700;'
    + 'color:' + T_TEXT + ';font-variant-numeric:tabular-nums;white-space:nowrap;">'
    + _escapeHtml(s.hora || "??") + '</td>'
    + '<td valign="top" style="padding:8px 0;border-bottom:1px solid ' + T_BORDER + ';font-size:13px;color:' + T_TEXT + ';">'
    + '<span style="display:inline-block;font-size:10px;color:' + T_MUTED + ';text-transform:uppercase;'
    + 'letter-spacing:0.05em;border:1px solid ' + T_BORDER + ';padding:1px 6px;border-radius:3px;'
    + 'margin-right:6px;vertical-align:1px;">' + _escapeHtml(s.cine || "") + '</span>'
    + '<span style="font-weight:500;">' + titleHtml + '</span>'
    + (metaStr ? '<div style="color:' + T_MUTED + ';font-size:11.5px;margin-top:2px;">' + _escapeHtml(metaStr) + '</div>' : '')
    + '</td>'
    + '</tr>'
  );
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
