/**
 * Effektvakt-kortet: den gamle effektvakta som Lovelace-kort.
 *
 * Kortet tegner ingen skala selv. Skiven hentes ferdig som SVG over
 * websocket-kommandoen `effektvakt/faceplate`, og kortet roterer de tre
 * viserne som alt ligger der. Da kan kortet og trykkfilen ikke drifte fra
 * hverandre: geometrien leses av data-attributtene paa svg-rota.
 *
 * Vanilla custom element med shadow DOM. Ingen Lit, ingen npm, ingen
 * webfonter, ingen byggesteg: filen serveres akkurat slik den ligger her.
 */

const KORTTYPE = "effektvakt-card";
const EDITORTYPE = "effektvakt-card-editor";
const WS_FACEPLATE = "effektvakt/faceplate";

// Viseren faar noen grader overslag over full skala, slik et ekte instrument
// slaar i endestoppet i stedet for aa forsvinne ut av skiven.
const OVERSLAG_GRADER = 4;

const UGYLDIGE_TILSTANDER = new Set(["unavailable", "unknown", ""]);

// Segmentet vi ligger an til blir tykkere, neste trinn farges viserroedt.
const TRINN_AKTIV = "ev-trinn-aktiv";
const TRINN_NESTE = "ev-trinn-neste";

const FLAGG_ID = "ev-flagg";

const CSS = `
:host {
  display: block;

  /* Fargerollene fra faceplate.py. Verdiene her er reserven; skiven sender
     sin egen palett over websocket, og den settes som inline custom
     properties paa ha-card og vinner over disse. */
  --effektvakt-emalje: #ece3d0;
  --effektvakt-trykk: #241f19;
  --effektvakt-viserrod: #a32026;
  --effektvakt-krom-lys: #e6e4df;
  --effektvakt-krom-mork: #7e7c75;
  --effektvakt-skygge: #b6ae9a;
  --effektvakt-prisme-lys: #d7d9d5;
  --effektvakt-prisme-mork: #a7aaa5;
  --effektvakt-prisme-glans: #eef0ec;
}

ha-card {
  padding: 12px;
}

.tittel {
  font-size: var(--ha-card-header-font-size, 24px);
  font-weight: 400;
  color: var(--ha-card-header-color, var(--primary-text-color));
  padding: 4px 4px 12px;
  line-height: 1.2;
}

.skive {
  display: block;
  width: 100%;
  margin: 0 auto;
  max-width: 460px;
  border-radius: 10px;
  /* Kromringen rundt glasset, og skyggen plata kaster i kabinettet. */
  box-shadow:
    0 0 0 2px var(--effektvakt-krom-mork),
    0 0 0 6px var(--effektvakt-krom-lys),
    0 6px 14px -6px var(--effektvakt-skygge);
}

.skive svg {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 8px;
}

/* Viserne roteres om navet. Transformen settes som style og vinner over
   rotate()-attributtet skiven ligger i hvile med.

   Kurven har et lite oversving foer den legger seg. Det er ikke pynt: et
   dreispoleverk er svakt underdempet og gjoer nettopp dette. Holdes smalt,
   for en viser som spretter ser ut som en animasjon og ikke som et maaleverk. */
.skive #viser-rod,
.skive #viser-svart,
.skive #slepemerke {
  transition: transform 850ms cubic-bezier(0.25, 1.08, 0.38, 1);
}

.skive .${TRINN_AKTIV} .trinn-bue {
  stroke-width: 18;
}

.skive .${TRINN_NESTE} .trinn-bue {
  stroke: var(--effektvakt-viserrod);
  stroke-width: 12;
}

/* Riflet felt som bunnfeltet paa skiven, med avlesningene i klartekst. */
.avlesning {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  margin: 12px auto 0;
  max-width: 460px;
  border-radius: 6px;
  overflow: hidden;
  background: var(--effektvakt-prisme-mork);
  border: 1px solid var(--effektvakt-prisme-mork);
}

.avlesning > div {
  flex: 1 1 0;
  min-width: 96px;
  padding: 7px 10px;
  background: var(--effektvakt-prisme-lys);
  border-top: 1px solid var(--effektvakt-prisme-glans);
}

.avlesning dt {
  margin: 0;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--effektvakt-krom-mork);
}

.avlesning dd {
  margin: 2px 0 0;
  font-size: 19px;
  font-variant-numeric: tabular-nums;
  color: var(--effektvakt-trykk);
}

.avlesning .rod dd {
  color: var(--effektvakt-viserrod);
  font-weight: 600;
}

.kostnad {
  margin: 10px 4px 2px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--secondary-text-color);
}

.feil {
  margin: 8px 4px;
  color: var(--error-color, #db4437);
  font-size: 14px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

@media (prefers-reduced-motion: reduce) {
  .skive #viser-rod,
  .skive #viser-svart,
  .skive #slepemerke {
    transition: none;
  }
}
`;

/** Tallet slik det leses av: norsk komma og faa desimaler. */
function tall(verdi, desimaler = 1, sprak = "nb-NO") {
  if (!Number.isFinite(verdi)) return "–";
  return new Intl.NumberFormat(sprak, {
    minimumFractionDigits: desimaler,
    maximumFractionDigits: desimaler,
  }).format(verdi);
}

function talletAv(verdi) {
  const n = typeof verdi === "number" ? verdi : Number.parseFloat(verdi);
  return Number.isFinite(n) ? n : null;
}

function erUgyldig(tilstand) {
  return !tilstand || UGYLDIGE_TILSTANDER.has(tilstand.state);
}

/**
 * Viservinkelen for en effekt, regnet ut av data-attributtene paa svg-rota.
 *
 * Formelen er ikke gjenskapt etter hukommelsen: den leser min, eksponent,
 * sokkel og sveip rett fra skiven, saa en lineaer dreispoleskala og en
 * komprimert dreiejernskala havner paa samme sted som i trykket.
 */
function vinkelForKw(geo, kw) {
  const klemt = Math.max(kw, geo.minKw);
  let andel;
  if (geo.sokkelKw > geo.minKw && geo.sokkelAndel > 0) {
    if (klemt <= geo.sokkelKw) {
      andel = (geo.sokkelAndel * (klemt - geo.minKw)) / (geo.sokkelKw - geo.minKw);
    } else {
      const nedre = geo.sokkelKw ** geo.eksponent;
      const spenn = geo.maksKw ** geo.eksponent - nedre;
      andel = geo.sokkelAndel + ((1 - geo.sokkelAndel) * (klemt ** geo.eksponent - nedre)) / spenn;
    }
  } else {
    const nedre = geo.minKw ** geo.eksponent;
    andel = (klemt ** geo.eksponent - nedre) / (geo.maksKw ** geo.eksponent - nedre);
  }
  const vinkel = geo.start + andel * geo.sveip;
  return Math.min(vinkel, geo.start + geo.sveip + OVERSLAG_GRADER);
}

function lesGeometri(svg) {
  const les = (navn, reserve) => {
    const n = Number.parseFloat(svg.getAttribute(navn));
    return Number.isFinite(n) ? n : reserve;
  };
  return {
    navX: les("data-nav-x", 500),
    navY: les("data-nav-y", 790),
    start: les("data-vinkel-start", -50),
    sveip: les("data-vinkel-sveip", 100),
    maksKw: les("data-maks-kw", 15),
    minKw: les("data-skala-min-kw", 0),
    eksponent: les("data-skala-eksponent", 1),
    sokkelKw: les("data-skala-sokkel-kw", 0),
    sokkelAndel: les("data-skala-sokkel-andel", 0),
  };
}

/** Kapasitetstrinnene slik de ligger i skiven, i stigende rekkefoelge. */
function lesSegmenter(svg) {
  return [...svg.querySelectorAll('g[id^="trinn-"]')].map((node) => ({
    node,
    fra: talletAv(node.getAttribute("data-kw-fra")) ?? 0,
    til: talletAv(node.getAttribute("data-kw-til")) ?? 0,
    kr: talletAv(node.getAttribute("data-kr")),
  }));
}

/**
 * Segmentet maaneden ligger an til.
 *
 * Kronebeloepet er den sikreste noekkelen fordi det kommer rett fra
 * kostnadssensoren, saa den proeves foerst. Deler to trinn pris, avgjoer
 * kW-verdien. Ingen av delene gjetter paa rekkefoelgen i DOM-en.
 */
function finnAktivt(segmenter, kr, kw) {
  if (kr !== null) {
    const treff = segmenter.filter((s) => s.kr === kr);
    if (treff.length === 1) return treff[0];
    if (treff.length > 1 && kw !== null) {
      const innenfor = treff.find((s) => kw >= s.fra && kw < s.til);
      if (innenfor) return innenfor;
    }
  }
  if (kw === null) return null;
  return segmenter.find((s) => kw >= s.fra && kw < s.til) ?? segmenter[segmenter.length - 1] ?? null;
}

function finnNeste(segmenter, aktivt, kr) {
  if (!aktivt) return null;
  const over = segmenter.filter((s) => s.fra >= aktivt.til);
  if (kr !== null) {
    const treff = over.find((s) => s.kr === kr);
    if (treff) return treff;
  }
  return over[0] ?? null;
}

class EffektvaktCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._svg = null;
    this._geo = null;
    this._segmenter = [];
    this._skiveNokkel = null;
    this._henter = null;
    this._feil = null;
    this._sisteNokkel = null;
    this._slepe = { maned: null, kw: 0 };
    this._bygd = false;
  }

  static getStubConfig(hass) {
    const kandidat = Object.keys(hass?.states ?? {}).find((id) =>
      id.startsWith("sensor.") && id.includes("projisert")
    );
    return { type: `custom:${KORTTYPE}`, entity: kandidat ?? "sensor.effektvakt_projisert_time_snitt" };
  }

  static getConfigElement() {
    return document.createElement(EDITORTYPE);
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Effektvakt-kortet trenger en entity: sensoren for projisert time-snitt.");
    }
    this._config = { ...config };
    this._feil = null;
    this._sisteNokkel = null;
    this._lesSlepeFraLager();
    this._bygg();
    // Skiven hentes saa snart vi har en hass. Er kortet konfigurert paa nytt
    // mens det staar i dashbordet, har vi den alt og kan hente med en gang.
    if (this._hass) this._sikreSkive();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._config) return;
    this._sikreSkive();
    this._oppdater();
  }

  getCardSize() {
    return 8;
  }

  // --- DOM ----------------------------------------------------------------

  _bygg() {
    if (this._bygd) return;
    this._bygd = true;

    const stil = document.createElement("style");
    stil.textContent = CSS;

    this._kort = document.createElement("ha-card");

    this._tittel = document.createElement("div");
    this._tittel.className = "tittel";

    this._skive = document.createElement("div");
    this._skive.className = "skive";

    this._avlesning = document.createElement("dl");
    this._avlesning.className = "avlesning";
    // Tallene er en synlig gjentakelse av aria-etiketten paa skiven.
    // Uten dette leses de samme verdiene to ganger etter hverandre.
    this._avlesning.setAttribute("aria-hidden", "true");
    this._felt = {};
    for (const [nokkel, etikett, klasse] of [
      ["projisert", "Projisert", "rod"],
      ["na", "Effekt nå", ""],
      ["topp3", "Topp-3 mnd", ""],
    ]) {
      const boks = document.createElement("div");
      if (klasse) boks.className = klasse;
      const dt = document.createElement("dt");
      dt.textContent = etikett;
      const dd = document.createElement("dd");
      dd.textContent = "–";
      boks.append(dt, dd);
      this._avlesning.append(boks);
      this._felt[nokkel] = dd;
    }

    this._kostnad = document.createElement("p");
    this._kostnad.className = "kostnad";
    this._kostnad.setAttribute("aria-hidden", "true");

    this._tekstalternativ = document.createElement("p");
    this._tekstalternativ.className = "sr-only";

    this._feilfelt = document.createElement("p");
    this._feilfelt.className = "feil";
    this._feilfelt.hidden = true;

    this._kort.append(
      this._tittel,
      this._skive,
      this._avlesning,
      this._kostnad,
      this._tekstalternativ,
      this._feilfelt
    );
    this.shadowRoot.replaceChildren(stil, this._kort);
  }

  // --- Skiven -------------------------------------------------------------

  _skiveOnsket() {
    const c = this._config;
    return JSON.stringify([c.entity, c.maks_kw ?? null, c.stil ?? null]);
  }

  _sikreSkive() {
    const onsket = this._skiveOnsket();
    if (onsket === this._skiveNokkel || onsket === this._henter) return;
    this._henter = onsket;
    this._hentSkive(onsket);
  }

  async _hentSkive(nokkel) {
    const c = this._config;
    const melding = { type: WS_FACEPLATE, entity_id: c.entity };
    if (c.maks_kw !== undefined && c.maks_kw !== null && c.maks_kw !== "") {
      melding.maks_kw = Number(c.maks_kw);
    }
    if (c.stil) melding.stil = c.stil;

    try {
      const svar = await this._hass.callWS(melding);
      if (this._henter !== nokkel) return;
      this._settSkive(svar);
      this._skiveNokkel = nokkel;
      this._feil = null;
    } catch (feil) {
      if (this._henter !== nokkel) return;
      this._feil = feil?.message ?? String(feil);
      this._svg = null;
    } finally {
      if (this._henter === nokkel) this._henter = null;
    }
    this._sisteNokkel = null;
    this._oppdater();
  }

  _settSkive(svar) {
    const dokument = new DOMParser().parseFromString(svar.svg, "image/svg+xml");
    const svg = dokument.documentElement;
    if (svg.nodeName !== "svg") {
      throw new Error("Skiven kom ikke som gyldig SVG");
    }
    this._svg = document.importNode(svg, true);
    this._svg.removeAttribute("width");
    this._svg.removeAttribute("height");
    this._geo = lesGeometri(this._svg);
    this._segmenter = lesSegmenter(this._svg);
    this._visere = {
      rod: this._svg.querySelector("#viser-rod"),
      svart: this._svg.querySelector("#viser-svart"),
      slepe: this._svg.querySelector("#slepemerke"),
    };
    const opprinnelse = `${this._geo.navX}px ${this._geo.navY}px`;
    for (const viser of Object.values(this._visere)) {
      if (viser) viser.style.transformOrigin = opprinnelse;
    }
    this._flagg = this._lagFlagg();
    this._svg.append(this._flagg);
    this._skive.replaceChildren(this._svg);

    for (const [rolle, farge] of Object.entries(svar.palett ?? {})) {
      this._kort.style.setProperty(`--effektvakt-${rolle}`, farge);
    }
    this._dsoNavn = svar.dso_navn ?? null;
  }

  /** Lite "---"-flagg i skiven naar sensoren ikke leverer en avlesning. */
  _lagFlagg() {
    const NS = "http://www.w3.org/2000/svg";
    const g = document.createElementNS(NS, "g");
    g.setAttribute("id", FLAGG_ID);
    g.setAttribute("aria-hidden", "true");
    g.style.display = "none";

    const ramme = document.createElementNS(NS, "rect");
    ramme.setAttribute("x", "405");
    ramme.setAttribute("y", "388");
    ramme.setAttribute("width", "190");
    ramme.setAttribute("height", "86");
    ramme.setAttribute("rx", "10");
    ramme.setAttribute("stroke-width", "4");
    // Fargene settes som style og ikke som presentasjonsattributt: var() i et
    // SVG-presentasjonsattributt er ikke paalitelig paa tvers av nettlesere.
    ramme.style.fill = "var(--effektvakt-emalje)";
    ramme.style.stroke = "var(--effektvakt-krom-mork)";

    const tekst = document.createElementNS(NS, "text");
    tekst.setAttribute("x", "500");
    tekst.setAttribute("y", "431");
    tekst.setAttribute("text-anchor", "middle");
    tekst.setAttribute("dominant-baseline", "central");
    tekst.setAttribute("font-size", "62");
    tekst.setAttribute("font-weight", "700");
    tekst.setAttribute("letter-spacing", "6");
    tekst.style.fill = "var(--effektvakt-trykk)";
    tekst.textContent = "---";

    g.append(ramme, tekst);
    return g;
  }

  // --- Avlesning ----------------------------------------------------------

  /** Kostnadssensoren: konfigurert, ellers den paa samme enhet. */
  _kostnadTilstand() {
    const valgt = this._config.kostnad_entity;
    if (valgt) return this._hass.states[valgt];
    for (const id of this._sosken()) {
      const t = this._hass.states[id];
      if (t?.attributes?.trinn_neste_kr !== undefined) return t;
    }
    return undefined;
  }

  /** Topp-3-sensoren paa samme enhet. Faller tilbake paa kostnadsattributtet. */
  _topp3Kw(kostnad) {
    for (const id of this._sosken()) {
      const t = this._hass.states[id];
      if (/topp.?3/i.test(id) && !erUgyldig(t)) return talletAv(t.state);
    }
    return talletAv(kostnad?.attributes?.topp_3_projisert_kw);
  }

  /** Entitetene paa samme enhet som den konfigurerte sensoren. */
  _sosken() {
    const register = this._hass.entities;
    const meg = register?.[this._config.entity];
    if (!meg?.device_id) return [];
    return Object.keys(register).filter(
      (id) => register[id].device_id === meg.device_id && id !== this._config.entity
    );
  }

  _oppdater() {
    if (!this._hass || !this._config) return;

    this._tittel.textContent = this._config.tittel ?? "";
    this._tittel.hidden = !this._config.tittel;

    this._feilfelt.hidden = !this._feil;
    if (this._feil) {
      this._feilfelt.textContent = `Fikk ikke hentet skiven: ${this._feil}`;
      return;
    }
    if (!this._svg) return;

    const projisert = this._hass.states[this._config.entity];
    const kostnad = this._kostnadTilstand();

    // set hass fyrer paa hver eneste tilstandsendring i HA. Uten denne
    // sammenligningen ville kortet regnet om skiven flere ganger i sekundet.
    const nokkel = [projisert?.last_updated, kostnad?.last_updated, this._config.tittel].join("|");
    if (nokkel === this._sisteNokkel) return;
    this._sisteNokkel = nokkel;

    const tilgjengelig = !erUgyldig(projisert);
    const projisertKw = tilgjengelig ? talletAv(projisert.state) : null;
    const naKw = tilgjengelig ? talletAv(projisert.attributes?.current_kw) : null;
    const topp3Kw = tilgjengelig ? this._topp3Kw(kostnad) : null;
    const slepeKw = this._slepe_hold(topp3Kw);

    this._settViser("rod", projisertKw);
    this._settViser("svart", naKw);
    this._settViser("slepe", tilgjengelig ? slepeKw : null);
    this._flagg.style.display = tilgjengelig ? "none" : "";

    this._merkTrinn(kostnad, topp3Kw);
    this._skrivTekst(tilgjengelig, projisertKw, naKw, slepeKw, kostnad);
  }

  _settViser(navn, kw) {
    const viser = this._visere?.[navn];
    if (!viser) return;
    // Uten avlesning parkeres viseren i hvile. En frossen viser som ser ut
    // som en maaling er verre enn en tom skive.
    const verdi = kw === null ? this._geo.minKw : kw;
    viser.style.transform = `rotate(${vinkelForKw(this._geo, verdi).toFixed(3)}deg)`;
  }

  /**
   * Slepemerket er ekte max-hold, ikke et speil av sensoren.
   *
   * top_n_average deler paa antall dager og ikke alltid paa tre, saa
   * topp-3-snittet kan gaa ned igjen tidlig i maaneden. En slepeviser som
   * synker ser oedelagt ut, saa hoeyeste verdi holdes til maaneden snur.
   */
  _slepe_hold(kw) {
    const na = new Date();
    const maned = `${na.getFullYear()}-${String(na.getMonth() + 1).padStart(2, "0")}`;
    if (this._slepe.maned !== maned) this._slepe = { maned, kw: 0 };
    if (kw !== null && kw > this._slepe.kw) {
      this._slepe = { maned, kw };
      this._skrivSlepeTilLager();
    }
    return this._slepe.kw;
  }

  _slepeNokkel() {
    return `effektvakt-slepemerke:${this._config.entity}`;
  }

  _lesSlepeFraLager() {
    // Uten lager ville slepemerket falt tilbake til sensorverdien hver gang
    // dashbordet lastes, og da er max-hold verdiloes.
    try {
      const raa = window.localStorage.getItem(this._slepeNokkel());
      const lagret = raa ? JSON.parse(raa) : null;
      if (lagret && typeof lagret.maned === "string" && Number.isFinite(lagret.kw)) {
        this._slepe = lagret;
      }
    } catch {
      this._slepe = { maned: null, kw: 0 };
    }
  }

  _skrivSlepeTilLager() {
    try {
      window.localStorage.setItem(this._slepeNokkel(), JSON.stringify(this._slepe));
    } catch {
      // Privat modus eller full kvote. Max-hold lever da bare i denne oekten.
    }
  }

  _merkTrinn(kostnad, topp3Kw) {
    for (const s of this._segmenter) s.node.classList.remove(TRINN_AKTIV, TRINN_NESTE);
    this._trinn = null;
    if (!kostnad || erUgyldig(kostnad)) return;

    const aktivt = finnAktivt(
      this._segmenter,
      talletAv(kostnad.attributes?.trinn_na_kr),
      talletAv(kostnad.attributes?.topp_3_projisert_kw) ?? topp3Kw
    );
    if (!aktivt) return;
    aktivt.node.classList.add(TRINN_AKTIV);

    const neste = finnNeste(this._segmenter, aktivt, talletAv(kostnad.attributes?.trinn_neste_kr));
    if (neste) neste.node.classList.add(TRINN_NESTE);
    this._trinn = { aktivt, neste };
  }

  _skrivTekst(tilgjengelig, projisertKw, naKw, slepeKw, kostnad) {
    const sprak = this._hass.locale?.language || "nb-NO";
    const kw = (v) => (v === null ? "–" : `${tall(v, 2, sprak)} kW`);

    this._felt.projisert.textContent = tilgjengelig ? kw(projisertKw) : "–";
    this._felt.na.textContent = tilgjengelig ? kw(naKw) : "–";
    this._felt.topp3.textContent = tilgjengelig ? kw(slepeKw) : "–";

    const skive = this._dsoNavn ? `Effektvakt for ${this._dsoNavn}` : "Effektvakt";
    this._svg.setAttribute(
      "aria-label",
      tilgjengelig
        ? `${skive}. Projisert time-snitt ${kw(projisertKw)}, effekt nå ${kw(naKw)},` +
          ` topp-3 denne måneden ${kw(slepeKw)}.`
        : `${skive}. Ingen avlesning, sensoren er utilgjengelig.`
    );

    const linjer = [];
    if (!tilgjengelig) {
      linjer.push(`${this._config.entity} er utilgjengelig, så viserne står parkert på null.`);
    } else if (kostnad && !erUgyldig(kostnad) && this._trinn?.aktivt) {
      const a = this._trinn.aktivt;
      const n = this._trinn.neste;
      linjer.push(
        `Måneden ligger an til kapasitetstrinnet ${tall(a.fra, 0, sprak)} til` +
          ` ${tall(a.til, 0, sprak)} kW, ${a.kr} kroner i måneden.`
      );
      if (n) {
        linjer.push(
          `Neste trinn starter på ${tall(n.fra, 0, sprak)} kW og koster ${n.kr} kroner i måneden,` +
            ` altså ${kostnad.state} kroner mer.`
        );
      }
    }
    // Skjult tekstalternativ for trinnbaandet, som ellers bare finnes som
    // grafikk. De tre avlesningene ligger i aria-etiketten paa skiven, saa de
    // gjentas ikke her.
    this._tekstalternativ.textContent = linjer.join(" ");
    this._kostnad.textContent = linjer.join(" ");
    this._kostnad.hidden = linjer.length === 0;
  }
}

class EffektvaktCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._stiler = null;
    this._henter = false;
  }

  setConfig(config) {
    this._config = { ...config };
    this._tegn();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._skjema) this._skjema.hass = hass;
    this._hentStiler();
  }

  /** Stilvalgene kommer fra registeret i faceplate.py, ikke fra en liste her. */
  async _hentStiler() {
    if (this._stiler || this._henter || !this._hass || !this._config.entity) return;
    this._henter = true;
    try {
      const svar = await this._hass.callWS({ type: WS_FACEPLATE, entity_id: this._config.entity });
      this._stiler = svar.stiler ?? {};
      this._tegn();
    } catch {
      this._stiler = {};
    } finally {
      this._henter = false;
    }
  }

  _skjemaet() {
    const entitet = { entity: { domain: "sensor", integration: "effektvakt" } };
    const felt = [
      { name: "entity", required: true, selector: entitet },
      { name: "tittel", selector: { text: {} } },
      { name: "kostnad_entity", selector: entitet },
      {
        name: "maks_kw",
        selector: { number: { min: 15, max: 150, step: 15, mode: "box", unit_of_measurement: "kW" } },
      },
    ];
    const stiler = Object.entries(this._stiler ?? {});
    if (stiler.length) {
      felt.push({
        name: "stil",
        selector: {
          select: {
            mode: "dropdown",
            options: stiler.map(([verdi, etikett]) => ({ value: verdi, label: etikett })),
          },
        },
      });
    }
    return felt;
  }

  _tegn() {
    if (!this._skjema) {
      this._skjema = document.createElement("ha-form");
      this._skjema.computeLabel = (felt) => ETIKETTER[felt.name] ?? felt.name;
      this._skjema.addEventListener("value-changed", (hendelse) => {
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config: hendelse.detail.value },
            bubbles: true,
            composed: true,
          })
        );
      });
      this.shadowRoot.replaceChildren(this._skjema);
    }
    if (this._hass) this._skjema.hass = this._hass;
    this._skjema.schema = this._skjemaet();
    this._skjema.data = this._config;
  }
}

const ETIKETTER = {
  entity: "Sensor for projisert time-snitt",
  kostnad_entity: "Kostnadssensor (valgfri, finnes automatisk)",
  tittel: "Tittel",
  maks_kw: "Skalaens toppverdi",
  stil: "Skive",
};

customElements.define(KORTTYPE, EffektvaktCard);
customElements.define(EDITORTYPE, EffektvaktCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: KORTTYPE,
  name: "Effektvakt",
  description: "Analog effektvakt med kapasitetstrinn, projisert time-snitt og slepemerke.",
  preview: true,
  documentationURL: "https://github.com/fredrik-lindseth/hacs-effektvakt/blob/main/docs/dashboard-kort.md",
});
