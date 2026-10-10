// Projde kazdou stranku v kazdem jazyce a podiva se na to, co clovek opravdu
// vidi: titulek v zalozce, meta popis a text stranky. Hlasi, kdyz v cizim
// jazyce zustala cestina nebo anglictina tam, kde nema.
const http = require('http');
const https = require('https');

const ZAKLAD = process.argv[2] || 'http://localhost:8076';
const STRANKY = ['/', '/rezervacni-system', '/cenik', '/rozpis-lekaru', '/nas-tym', '/o-nas'];
const JAZYKY = [
  { kod: 'cs', prefix: '', hlavicka: 'cs-CZ,cs', ocekavany: 'cs-CZ' },
  { kod: 'de', prefix: '/de', hlavicka: 'de-DE,de', ocekavany: 'de-DE' },
  { kod: 'en', prefix: '/en', hlavicka: 'en-US,en', ocekavany: 'en-US' },
  { kod: 'ru', prefix: '/ru', hlavicka: 'ru-RU,ru', ocekavany: 'ru-RU' },
];

// Slova, ktera v dane mutaci nemaji co delat. Diakritika sama nestaci —
// „Diagnostika“ nebo „Adresa“ by proklouzly.
const CESKA_SLOVA = ['služb', 'lékař', 'objednat', 'ordinač', 'více', 'naše', 'našeho',
  'pondělí', 'sobota', 'neděle', 'zavřeno', 'otevír', 'kontaktujte', 'rezervač',
  'přijímáme', 'ceník', 'cena', 'zjistit', 'napsat', 'zeptat'];
const ANGLICKA_SLOVA = ['opening hours', 'our team', 'book an appointment', 'price list',
  'duty schedule', 'read more', 'contact us', 'find out'];

function stahni(cesta, hlavicka) {
  const klient = ZAKLAD.startsWith('https:') ? https : http;
  return new Promise((splnit, selhat) => {
    const zadost = klient.get(ZAKLAD + cesta, { headers: { 'Accept-Language': hlavicka } },
      (odpoved) => {
        if (odpoved.statusCode >= 300 && odpoved.statusCode < 400 && odpoved.headers.location) {
          const dalsi = odpoved.headers.location.replace(ZAKLAD, '');
          odpoved.resume();
          return splnit(stahni(dalsi, hlavicka));
        }
        let telo = '';
        odpoved.setEncoding('utf8');
        odpoved.on('data', (k) => { telo += k; });
        odpoved.on('end', () => splnit({ kod: odpoved.statusCode, telo }));
      });
    zadost.on('error', selhat);
    zadost.setTimeout(60000, () => { zadost.destroy(); selhat(new Error('timeout ' + cesta)); });
  });
}

function vytahni(html) {
  const zacatek = html.indexOf('id="wrap"');
  const telo = zacatek > -1 ? html.slice(zacatek) : html;
  return telo.replace(/<script[\s\S]*?<\/script>/g, ' ')
             .replace(/<style[\s\S]*?<\/style>/g, ' ')
             .replace(/<[^>]+>/g, ' ')
             .replace(/&nbsp;|&#160;/g, ' ')
             .replace(/\s+/g, ' ');
}

(async () => {
  let problemu = 0;
  for (const s of STRANKY) {
    for (const j of JAZYKY) {
      const { kod, telo } = await stahni(j.prefix + s, j.hlavicka);
      const potize = [];
      if (kod !== 200) { potize.push('HTTP ' + kod); }

      const lang = (telo.match(/<html[^>]*lang="([^"]+)"/) || [])[1];
      if (lang !== j.ocekavany) { potize.push('html lang=' + lang); }

      const titulek = (telo.match(/<title>([^<]*)<\/title>/) || [])[1] || '';
      const popis = (telo.match(/<meta name="description" content="([^"]*)"/) || [])[1] || '';
      if (!titulek.trim()) { potize.push('chybi titulek'); }
      if (!popis.trim()) { potize.push('chybi meta popis'); }

      const text = vytahni(telo).toLowerCase();
      const hlavicka = (titulek + ' ' + popis).toLowerCase();
      if (j.kod !== 'cs') {
        const nalez = CESKA_SLOVA.filter(w => text.includes(w));
        if (nalez.length) { potize.push('cestina v textu: ' + nalez.slice(0, 4).join(', ')); }
        const nalezH = CESKA_SLOVA.filter(w => hlavicka.includes(w));
        if (nalezH.length) { potize.push('cestina v titulku/popisu: ' + nalezH.slice(0, 3).join(', ')); }
      }
      if (j.kod === 'cs') {
        const nalez = ANGLICKA_SLOVA.filter(w => text.includes(w));
        if (nalez.length) { potize.push('anglictina v textu: ' + nalez.slice(0, 4).join(', ')); }
      }
      if (j.kod === 'ru' && !/[Ѐ-ӿ]/.test(titulek)) {
        potize.push('titulek bez azbuky: ' + titulek.slice(0, 50));
      }

      problemu += potize.length;
      console.log('%s %s  %s', (j.prefix + s).padEnd(26), j.kod,
        potize.length ? 'PROBLEM: ' + potize.join(' | ') : 'OK  ' + titulek.slice(0, 52));
    }
  }
  console.log();
  console.log('===== problemu celkem: ' + problemu + ' =====');
})().catch((e) => { console.error('SELHALO:', e.message); process.exit(1); });
