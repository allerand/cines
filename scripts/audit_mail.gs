/**
 * Auditoría de la cartelera por mail — Google Apps Script.
 *
 * Va en un proyecto de Apps Script APARTE del newsletter, a propósito: acá no
 * hay ninguna función que le mande mail a nadie más que a vos. El proyecto del
 * newsletter tiene la lista de suscriptores y su propio trigger; este archivo
 * no lo toca ni lo importa.
 *
 * Por qué Apps Script y no GitHub Actions: mandar mail desde el runner pediría
 * guardar una contraseña de aplicación como secret del repo. Acá corre con tu
 * cuenta de Google y no hay ninguna credencial dada de alta en ningún lado.
 *
 * ──────────────────────────────────────────────────────────────────────
 * SETUP (una vez):
 *   1. script.google.com → Nuevo proyecto → nombralo "Auditoría cines"
 *      (NUEVO, no el del newsletter)
 *   2. Pegá este archivo entero, reemplazando el Code.gs vacío
 *   3. Ejecutar → sendAuditMail. Te pide permisos y te manda el informe de hoy
 *   4. Triggers (el reloj) → Add trigger:
 *        - Function: sendAuditMail
 *        - Source: Time-driven → Week timer → Monday → 10 AM-11 AM
 *      (el workflow corre 09:30 ART, así que a las 10 ya está el informe)
 * ──────────────────────────────────────────────────────────────────────
 */

const AUDIT_URL = "https://raw.githubusercontent.com/allerand/cines/main/data/audit.html";
// Vacío = tu propia casilla. No pongas acá una lista de nadie más.
const AUDIT_TO = "";

function sendAuditMail() {
  const res = UrlFetchApp.fetch(AUDIT_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    Logger.log("No se pudo leer el informe: HTTP " + res.getResponseCode());
    return;
  }
  const html = res.getContentText();

  // audit.py deja el veredicto en un comentario HTML para no tener que
  // re-parsear el informe sólo para armar el asunto.
  const mRes = html.match(/<!--\s*asunto:\s*(.*?)\s*-->/);
  const asunto = mRes ? mRes[1] : "Auditoría de cartelera";

  // Quién audita al auditor: si el informe no es de esta semana, el workflow
  // dejó de correr. Sin este chequeo llegaría el mismo informe viejo para
  // siempre, dando la falsa impresión de que está todo bien.
  const mFecha = html.match(/<!--\s*fecha:\s*(\d{4}-\d{2}-\d{2})\s*-->/);
  let aviso = "";
  if (mFecha) {
    const dias = Math.floor((Date.now() - new Date(mFecha[1] + "T12:00:00Z")) / 86400000);
    if (dias > 8) {
      aviso = "[informe de hace " + dias + " días] ";
      Logger.log("El informe tiene " + dias + " días: revisá el workflow audit.yml");
    }
  }

  MailApp.sendEmail({
    to: AUDIT_TO || Session.getActiveUser().getEmail(),
    subject: aviso + asunto,
    htmlBody: html,
    name: "Auditoría cartelera",
  });
  Logger.log("Enviado: " + asunto);
}
