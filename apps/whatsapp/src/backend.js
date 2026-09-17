// Cliente HTTP minimo hacia el backend de Reprebot.
//
// El contrato esta congelado en POST {BACKEND_URL}/api/whatsapp/answer y el
// backend free de Render puede tener cold start de ~1 min, de ahi el timeout.

const TIMEOUT_MS = 90_000;
const BODY_PREVIEW = 300;

function recortar(texto, max = BODY_PREVIEW) {
  const limpio = String(texto || '')
    .replace(/\s+/g, ' ')
    .trim();
  return limpio.length > max ? `${limpio.slice(0, max)}...` : limpio;
}

// Manda la pregunta al backend y devuelve el JSON de la respuesta 200.
// Lanza Error con mensaje claro si el status no es 2xx o si no hay respuesta.
export async function preguntar(texto, senderName) {
  const base = (process.env.BACKEND_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
  const url = `${base}/api/whatsapp/answer`;

  const headers = { 'Content-Type': 'application/json' };
  const apiKey = (process.env.WHATSAPP_API_KEY || '').trim();
  if (apiKey) headers['X-Api-Key'] = apiKey;

  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ text: texto, sender_name: senderName ?? '' }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    throw new Error(`No pude contactar el backend en ${url}: ${err.message}`);
  }

  if (!res.ok) {
    let body = '';
    try {
      body = await res.text();
    } catch {
      // El body no siempre es texto; con el status basta para diagnosticar.
    }
    throw new Error(`El backend respondio ${res.status}: ${recortar(body)}`);
  }

  return res.json();
}
