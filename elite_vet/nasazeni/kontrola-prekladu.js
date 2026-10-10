// Projde vsechny stranky ve vsech ctyrech jazycich a hleda dve veci:
//   1. anglictinu, ktera zustala v cestine, nemcine nebo rustine
//   2. cestinu, ktera zustala v nemcine, rustine nebo anglictine
// Porovnava se text proti anglicke a ceske verzi tehoz mista, takze to chytne
// i termin, ktery jen nikdo neprelozil a ma v sobe zdroj.
// Adresa webu se da predat argumentem, takze stejna kontrola projde lokal
// i ostry web:   node kontrola-prekladu.js https://www.elite-vet.cz
const http = require('http');
const https = require('https');
const ZAKLAD = new URL(process.argv[2] || 'http://localhost:8076');

const STRANKY = ['/', '/rezervacni-system', '/cenik', '/rozpis-lekaru', '/nas-tym', '/o-nas'];
const JAZYKY = [
    { kod: 'cs', pred: '', hlavicka: 'cs-CZ,cs', ocekavany: 'cs-CZ' },
    { kod: 'de', pred: '/de', hlavicka: 'de-DE,de', ocekavany: 'de-DE' },
    { kod: 'en', pred: '/en', hlavicka: 'en-US,en', ocekavany: 'en-US' },
    { kod: 'ru', pred: '/ru', hlavicka: 'ru-RU,ru', ocekavany: 'ru-RU' },
];
// znacka, adresa, kontakty, nazvy jazyku a polozky menu (ty jsou v adminu, ne v kodu)
const POVOLENE = new Set([
    'Elite Vet', 'EliteVet', 'Elite', 'Vet', 'Michal Varys', 'Varyshop', 'WinVet',
    'info@elite-vet.cz', 'CZ', 'DE', 'EN', 'RU', 'Čeština', 'Deutsch', 'English', 'Русский',
    '24/7', 'My Website', 'Kontakt', 'Contact', 'Chirurgie', 'Dermatologie', 'Stomatologie',
    'Služby', 'Náš tým', 'Rezervační systém', 'Rozpis služeb', 'Kontaktujte nás',
    'ELITE VET Karlovy Vary',
]);

function stahni(cesta, hlavicka) {
    return new Promise((splnit, selhat) => {
        const klient = ZAKLAD.protocol === 'https:' ? https : http;
        klient.get({ host: ZAKLAD.hostname, port: ZAKLAD.port || undefined, path: cesta,
            headers: { 'Accept-Language': hlavicka, Accept: 'text/html' } }, (o) => {
            if (o.statusCode >= 300 && o.statusCode < 400) {
                o.resume();
                return splnit(stahni(o.headers.location, hlavicka));
            }
            let t = '';
            o.setEncoding('utf8');
            o.on('data', (c) => { t += c; });
            o.on('end', () => splnit(t));
        }).on('error', selhat);
    });
}
// jen obsah stranky; skryta vychozi hlavicka a patka Odoo se neposuzuji
// Styly a skripty se musi zahodit DRIV, nez se hleda hranice obsahu. Nazev tridy
// ev-footer-credit se totiz objevi uz v <style> a driv se podle nej orezavalo —
// kontrole pak zbyla jen hlavicka stranky a hlasila OK i na uplne neprelozene.
function obsah(html) {
    const cisty = html
        .replace(/<script[\s\S]*?<\/script>/g, ' ')
        .replace(/<style[\s\S]*?<\/style>/g, ' ')
        .replace(/<!--[\s\S]*?-->/g, ' ');
    const od = cisty.indexOf('<div id="wrap"');
    const doo = cisty.indexOf('ev-footer-credit');
    if (od < 0) { throw new Error('na strance chybi #wrap, kontrola by merila nesmysl'); }
    return cisty.slice(od, doo > od ? doo : cisty.length);
}

function texty(html) {
    const cisty = obsah(html);
    const ven = new Set();
    cisty.replace(/>([^<>]+)</g, (cely, t) => {
        const s = t.replace(/&nbsp;| /g, ' ').replace(/\s+/g, ' ').trim();
        if (s.length > 2 && /[a-zA-Zá-žÁ-Ža-яА-Я]/.test(s)) { ven.add(s); }
        return cely;
    });
    return ven;
}
// jmena lidi, e-mailove adresy, casy sluzeb a nazvy mesicu shodne s anglictinou
// se neprekladaji — bez tohohle by je kontrola hlasila jako chybu
const JMENA = /^(MVDr\.|Bc\.|Mgr\.|Silvie |Nikola |Lucie )|, DiS\.$/;
const zajimave = (t) => !POVOLENE.has(t) && !/^[\d\s+\-–—:.,()/]+$/.test(t)
    && !/^Hybešova|^Rybáře|^\+420|^360 05/.test(t)
    && !/@elite-vet\.cz$/.test(t)
    && !JMENA.test(t)
    && !/^[·\s]*\d{1,2}:\d{2}/.test(t)
    && !/^(September|November|December) \d{4}$/.test(t)
    && !/^\d[\d\s]*(Kč|CZK|€)$/.test(t);

(async () => {
    let nalezu = 0;
    for (const stranka of STRANKY) {
        const cesta = (p) => p + (stranka === '/' ? '/' : stranka);
        const en = texty(await stahni(cesta('/en'), 'en-US,en'));
        const cs = texty(await stahni(cesta(''), 'cs-CZ,cs'));
        for (const j of JAZYKY) {
            const html = await stahni(cesta(j.pred), j.hlavicka);
            const jazykStranky = (html.match(/<html[^>]*lang="([^"]+)"/) || [])[1] || '?';
            const t = texty(html);
            const potize = [];
            if (jazykStranky !== j.ocekavany) {
                potize.push('!! stranka se vratila v jazyce ' + jazykStranky);
            }
            if (j.kod !== 'en') {
                for (const s of t) { if (en.has(s) && zajimave(s)) { potize.push('anglicky: ' + s.slice(0, 80)); } }
            }
            if (j.kod !== 'cs') {
                // Rozhoduje shoda s ceskou verzi tehoz mista. Puvodne se hledala
                // i ceska pismena, jenze nemecky text s ceskym jmenem uvnitr
                // (Žilina, Raušerova) pak hlasil chybu, ktera zadna nebyla.
                for (const s of t) {
                    if (!zajimave(s) || en.has(s)) { continue; }
                    if (cs.has(s)) { potize.push('cesky: ' + s.slice(0, 80)); }
                }
            }
            nalezu += potize.length;
            console.log(`${ZAKLAD.host}${stranka}  ${j.kod}: ${potize.length ? potize.length + ' problemu' : 'OK'}`);
            for (const p of potize) { console.log('      ' + p); }
        }
    }
    console.log('\n===== celkem problemu: ' + nalezu + ' =====');
})();
