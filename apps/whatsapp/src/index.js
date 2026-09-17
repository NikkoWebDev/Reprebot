// Arranque del puente: config, logger, servidor de salud, keep-alive y el
// socket de Baileys con reconexion.

import http from 'node:http';
import fs from 'node:fs';
import 'dotenv/config';
import pino from 'pino';
import qrcode from 'qrcode-terminal';
import makeWASocket, {
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
} from '@whiskeysockets/baileys';
import { crearHandler } from './bot.js';

const AUTH_DIR = 'auth';
const KEEPALIVE_MS = 10 * 60 * 1000;
const RECONNECT_MAX_MS = 60 * 1000;

function boolEnv(valor) {
  return ['1', 'true', 'yes', 'on'].includes(String(valor ?? '').trim().toLowerCase());
}

function numEnv(valor, porDefecto) {
  const n = Number(valor);
  return Number.isFinite(n) && n > 0 ? n : porDefecto;
}

const config = {
  port: numEnv(process.env.PORT, 3000),
  groupName: (process.env.WA_GROUP_NAME || '').trim(),
  groupJid: (process.env.WA_GROUP_JID || '').trim() || null,
  triggers: (process.env.WA_TRIGGERS ?? '!repre,/repre')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
  cooldownSeconds: numEnv(process.env.WA_COOLDOWN_SECONDS, 20),
  maxPerMinute: numEnv(process.env.WA_MAX_PER_MINUTE, 6),
  maxChars: numEnv(process.env.WA_MAX_CHARS, 1800),
  keepalive: boolEnv(process.env.WA_KEEPALIVE),
  qrToken: (process.env.WA_QR_TOKEN || '').trim(),
};

const log = pino({ level: process.env.LOG_LEVEL || 'warn' });

const grupos = new Map();
const estado = { connected: false, qr: null };

let sock = null;
let reintentoMs = 1000;
let reconexionProgramada = false;

// --- Servidor HTTP: health check de Render y QR para emparejar ---
const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url.split('?')[0] === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(
      JSON.stringify({
        ok: true,
        connected: estado.connected,
        group: config.groupJid,
        groupName: config.groupName || null,
      }),
    );
    return;
  }

  if (req.method === 'GET' && req.url.split('?')[0] === '/qr') {
    // El QR empareja la sesion: quien lo escanee se queda con el WhatsApp del
    // bot. Sin WA_QR_TOKEN no se expone por HTTP; el QR sigue saliendo en los
    // logs del servicio.
    if (!config.qrToken) {
      res.writeHead(403, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('WA_QR_TOKEN sin configurar. Mira el QR en los logs del servicio.');
      return;
    }
    const token = new URL(req.url, 'http://localhost').searchParams.get('token') || '';
    if (token !== config.qrToken) {
      res.writeHead(401, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('token invalido');
      return;
    }
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(estado.qr || 'sin qr');
    return;
  }

  res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
  res.end('not found');
});

server.listen(config.port, () => {
  log.warn(`Escuchando en http://0.0.0.0:${config.port} (/health, /qr)`);
});

// --- Keep-alive: evita que Render duerma el free (consume cuota de horas) ---
if (config.keepalive && process.env.RENDER_EXTERNAL_URL) {
  const url = `${process.env.RENDER_EXTERNAL_URL.replace(/\/+$/, '')}/health`;
  const timer = setInterval(() => {
    fetch(url).catch(() => {});
  }, KEEPALIVE_MS);
  timer.unref?.();
  log.warn(`Keep-alive activo: ${url} cada 10 min.`);
}

// --- Resolucion del grupo objetivo ---
function normalizarNombre(valor) {
  return String(valor || '')
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase();
}

function listarGrupos() {
  return [...grupos]
    .map(([jid, subject]) => `${subject || '(sin nombre)'} <${jid}>`)
    .join(' | ');
}

async function resolverGrupo() {
  if (config.groupJid || !sock) return;

  let todos;
  try {
    todos = await sock.groupFetchAllParticipating();
  } catch (err) {
    log.warn(`No pude listar los grupos: ${err?.message || err}`);
    return;
  }

  const lista = Object.values(todos || {});
  for (const g of lista) {
    if (g?.id) grupos.set(g.id, g.subject || '');
  }

  if (!config.groupName) {
    log.warn(
      `Sin WA_GROUP_NAME ni WA_GROUP_JID: no respondo a nadie. ` +
        `Grupos vistos: ${listarGrupos() || 'ninguno'}`,
    );
    return;
  }

  const objetivo = normalizarNombre(config.groupName);
  const coincidencias = lista.filter((g) => normalizarNombre(g.subject) === objetivo);

  if (coincidencias.length === 1) {
    config.groupJid = coincidencias[0].id;
    config.groupName = coincidencias[0].subject || config.groupName;
    log.warn(`Grupo objetivo: "${config.groupName}" <${config.groupJid}>`);
  } else if (coincidencias.length > 1) {
    log.warn(`Varios grupos coinciden con "${config.groupName}"; no respondo hasta fijar WA_GROUP_JID:`);
    for (const g of coincidencias) log.warn(`  ${g.subject} <${g.id}>`);
  } else {
    log.warn(
      `No encontre ningun grupo llamado "${config.groupName}". ` +
        `Grupos vistos: ${listarGrupos() || 'ninguno'}`,
    );
  }
}

// --- Ciclo de conexion ---
async function conectar() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    logger: log,
    printQRInTerminal: false,
    browser: ['Reprebot', 'Chrome', '1.0.0'],
    syncFullHistory: false,
    markOnlineOnConnect: false,
  });

  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('messages.upsert', crearHandler({ sock, config, log, grupos }));

  sock.ev.on('groups.upsert', async (nuevos) => {
    for (const g of nuevos || []) {
      if (g?.id) grupos.set(g.id, g.subject || grupos.get(g.id) || '');
    }
    if (!config.groupJid) await resolverGrupo();
  });

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      estado.qr = qr;
      qrcode.generate(qr, { small: true });
      log.warn('QR generado. Escanealo desde WhatsApp > Dispositivos vinculados, o abre /qr.');
    }

    if (connection === 'open') {
      estado.connected = true;
      estado.qr = null;
      reintentoMs = 1000;
      log.warn(`Conectado como ${sock.user?.id || '(desconocido)'}`);
      await resolverGrupo();
    }

    if (connection === 'close') {
      estado.connected = false;
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      log.warn(`Conexion cerrada (statusCode=${statusCode}).`);

      if (statusCode === DisconnectReason.loggedOut) {
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        reintentoMs = 1000;
        log.warn('Sesion cerrada; borro auth/ y pido QR nuevo.');
      }

      if (reconexionProgramada) return;
      reconexionProgramada = true;

      const espera = reintentoMs;
      reintentoMs = Math.min(reintentoMs * 2, RECONNECT_MAX_MS);
      setTimeout(() => {
        reconexionProgramada = false;
        conectar().catch((err) => {
          log.error(`Fallo al reconectar: ${err?.message || err}`);
          reconectarTrasFallo();
        });
      }, espera);
    }
  });
}

function reconectarTrasFallo() {
  if (reconexionProgramada) return;
  reconexionProgramada = true;
  setTimeout(() => {
    reconexionProgramada = false;
    conectar().catch((err) => {
      log.error(`Fallo al reconectar: ${err?.message || err}`);
      reconectarTrasFallo();
    });
  }, Math.min(reintentoMs, RECONNECT_MAX_MS));
  reintentoMs = Math.min(reintentoMs * 2, RECONNECT_MAX_MS);
}

process.on('unhandledRejection', (err) => {
  log.error(`unhandledRejection: ${err?.message || err}`);
});

process.on('uncaughtException', (err) => {
  log.error(`uncaughtException: ${err?.message || err}`);
});

conectar().catch((err) => {
  log.error(`Fallo al conectar: ${err?.message || err}`);
  reconectarTrasFallo();
});
