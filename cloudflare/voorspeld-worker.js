// Worker 'voorspeld-api' — route www.bet-experts.nl/api/voorspeld/*
// Geeft de vermoedelijke (of definitieve) opstelling van een voorbeschouwing terug in het formaat van
// API-Football (/api/match/<id>/lineups), zodat het opstellingen-blok op de site dezelfde elf toont als de tekst.
// Gevuld door opstellingen-agent/vb_sync.py (KV-sleutel fx:<fixture-id>).
export default {
  async fetch(req, env) {
    const m = new URL(req.url).pathname.match(/^\/api\/voorspeld\/(\d+)\/?$/);
    const h = { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*" };
    if (!m) return new Response('{"response":[]}', { status: 404, headers: h });
    const v = await env.VS.get("fx:" + m[1]);
    return new Response(v || '{"response":[]}', { headers: { ...h, "cache-control": "public, max-age=120" } });
  },
};
