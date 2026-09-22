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

// Avlesningen har tre utfall, ikke to. "borte" er en sensor som ikke svarer,
// "venter" er en sensor som ennaa ikke har noe aa si. Rett etter omstart er
// 0,00 kW ikke et hus som ikke bruker stroem, det er fravaeret av en maaling,
// og da skal kortet ikke tegne en avlesning.
const AVLESNING_OK = "ok";
const AVLESNING_VENTER = "venter";
const AVLESNING_BORTE = "borte";

const TILSTAND_BORTE = new Set(["unavailable"]);
const TILSTAND_VENTER = new Set(["unknown", ""]);

// Ved omstart av Home Assistant kobler frontenden seg paa foer integrasjonene
// er satt opp, og da finnes ikke websocket-kommandoen ennaa: svaret er
// «Unknown command». Det retter seg selv i loepet av sekunder, saa kortet
// proever igjen med voksende pause framfor aa gi opp paa foerste forsoek.
const FORSOK_PAUSER_MS = [500, 1000, 2000, 4000, 8000, 15000, 30000];
// Femte forsoek kommer rundt femten sekunder ut. Har det ikke loest seg da, er
// det verdt aa si fra; foer det er roed tekst bare stoey.
const FEILMELDING_ETTER_FORSOK = 5;
// Editoren proever ved hver hass-oppdatering, som kommer titt. Uten et tak
// ville et virkelig brudd gitt et jevnt kall mot websocket resten av oekten.
const EDITOR_MAKS_FORSOK = 5;

// Segmentet vi ligger an til blir tykkere, neste trinn farges viserroedt.
const TRINN_AKTIV = "ev-trinn-aktiv";
const TRINN_NESTE = "ev-trinn-neste";

const FLAGG_ID = "ev-flagg";
const FORKLARING_ID = "ev-forklaring";

// Hva merkene paa skiven betyr. Fredrik maatte spoerre hva trekanten var, og
// da trenger en skjermleserbruker det samme svaret. Originalens egne merker,
// maaleverkssymbol, klasse og proevespenning, staar i docs/dashboard-kort.md:
// de er historisk pynt og hoerer ikke til avlesningen.
const FORKLARING =
  "Rød viser er projisert time-snitt, altså hvor timen ender hvis forbruket fortsetter som nå." +
  " Tynn svart viser er effekten akkurat nå." +
  " Trekanten utenfor buen er slepemerket, som står på topp-3-snittet for måneden og aldri" +
  " går ned igjen." +
  " Båndet ytterst er kapasitetstrinnene med månedspris, der trinnet måneden ligger an til er" +
  " tykt og neste trinn er rødt.";

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

/* Plassholder mens skiven hentes, saa kortet ikke hopper i hoeyden naar den
   kommer. Skiven er kvadratisk. */
.skive:empty {
  aspect-ratio: 1 / 1;
  background: var(--effektvakt-emalje);
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

/* Statuslinjen: nedtonet mens kortet venter, roed foerst naar ventingen har
   vart lenge nok til at noe trolig er galt. */
.melding {
  margin: 8px 4px;
  color: var(--secondary-text-color);
  font-size: 14px;
}

.melding.feil {
  color: var(--error-color, #db4437);
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
 * Hva sensoren faktisk forteller: en avlesning, ingen avlesning ennaa, eller
 * ingen sensor.
 *
 * Skillet mellom de to siste betyr noe. "unavailable" er en sensor som er
 * borte. "unknown", og en tilstand uten `current_kw`, er en integrasjon som
 * ikke har noen maaling aa gi: rett etter oppstart, eller etter at watchdogen
 * har toemt coordinatoren. Da er null ikke et maaleresultat.
 */
function lesAvlesning(tilstand) {
  if (!tilstand || TILSTAND_BORTE.has(tilstand.state)) return AVLESNING_BORTE;
  if (TILSTAND_VENTER.has(tilstand.state)) return AVLESNING_VENTER;
  if (talletAv(tilstand.state) === null) return AVLESNING_BORTE;
  if (talletAv(tilstand.attributes?.current_kw) === null) return AVLESNING_VENTER;
  return AVLESNING_OK;
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
    this._forsok = 0;
    this._timer = null;
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

  connectedCallback() {
    // Kortet kan flyttes i dashbordet eller komme tilbake etter at fanen har
    // vaert borte. Da tas hentingen opp igjen der den slapp.
    if (this._config && this._hass) this._sikreSkive();
  }

  disconnectedCallback() {
    this._avbrytForsok();
    // Uten skive er ingen henting i gang lenger, og neste connectedCallback
    // skal faa lov til aa begynne paa nytt.
    if (!this._skiveNokkel) this._henter = null;
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
    this._tekstalternativ.id = FORKLARING_ID;

    this._melding = document.createElement("p");
    this._melding.className = "melding";
    this._melding.hidden = true;

    this._kort.append(
      this._tittel,
      this._skive,
      this._avlesning,
      this._kostnad,
      this._tekstalternativ,
      this._melding
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
    this._avbrytForsok();
    this._forsok = 0;
    this._feil = null;
    this._henter = onsket;
    this._hentSkive(onsket);
  }

  /**
   * Nytt forsoek med voksende pause.
   *
   * `_henter` staar paa noekkelen hele tiden mellom forsoekene, saa hverken
   * en tilstandsendring i HA eller en ny `set hass` starter en henting til
   * ved siden av den som venter.
   */
  _planleggNyttForsok(nokkel) {
    this._avbrytForsok();
    if (!this.isConnected) return;
    const pause = FORSOK_PAUSER_MS[Math.min(this._forsok - 1, FORSOK_PAUSER_MS.length - 1)];
    this._timer = window.setTimeout(() => {
      this._timer = null;
      if (this._hass && this._henter === nokkel) this._hentSkive(nokkel);
    }, pause);
  }

  _avbrytForsok() {
    if (this._timer !== null) {
      window.clearTimeout(this._timer);
      this._timer = null;
    }
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
      this._forsok = 0;
      this._henter = null;
    } catch (feil) {
      if (this._henter !== nokkel) return;
      this._forsok += 1;
      this._svg = null;
      this._feil = this._forsok >= FEILMELDING_ETTER_FORSOK ? (feil?.message ?? String(feil)) : null;
      this._planleggNyttForsok(nokkel);
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
    // Skiven har alt role="img" fra faceplate.py. Etiketten settes ved hver
    // oppdatering; beskrivelsen peker paa forklaringen av merkene.
    this._svg.setAttribute("aria-describedby", FORKLARING_ID);
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

    this._visMelding();
    if (!this._svg) return;

    const projisert = this._hass.states[this._config.entity];
    const kostnad = this._kostnadTilstand();

    // set hass fyrer paa hver eneste tilstandsendring i HA. Uten denne
    // sammenligningen ville kortet regnet om skiven flere ganger i sekundet.
    const nokkel = [projisert?.last_updated, kostnad?.last_updated, this._config.tittel].join("|");
    if (nokkel === this._sisteNokkel) return;
    this._sisteNokkel = nokkel;

    const avlesning = lesAvlesning(projisert);
    const harTall = avlesning === AVLESNING_OK;
    const projisertKw = harTall ? talletAv(projisert.state) : null;
    const naKw = harTall ? talletAv(projisert.attributes?.current_kw) : null;
    const topp3Kw = harTall ? this._topp3Kw(kostnad) : null;
    const slepeKw = this._slepe_hold(topp3Kw);

    this._settViser("rod", projisertKw);
    this._settViser("svart", naKw);
    this._settViser("slepe", harTall ? slepeKw : null);
    this._flagg.style.display = harTall ? "none" : "";

    this._merkTrinn(kostnad, topp3Kw);
    this._skrivTekst(avlesning, projisertKw, naKw, slepeKw, kostnad);
  }

  /** Statuslinjen under skiven. Tom naar skiven er der og alt er som det skal. */
  _visMelding() {
    let tekst = "";
    if (this._feil) {
      tekst = `Fikk ikke hentet skiven: ${this._feil} Kortet prøver igjen.`;
    } else if (!this._svg && this._henter !== null) {
      tekst = "Henter skiven …";
    }
    this._melding.textContent = tekst;
    this._melding.hidden = !tekst;
    this._melding.classList.toggle("feil", Boolean(this._feil));
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

  _skrivTekst(avlesning, projisertKw, naKw, slepeKw, kostnad) {
    const harTall = avlesning === AVLESNING_OK;
    const venter = avlesning === AVLESNING_VENTER;
    const sprak = this._hass.locale?.language || "nb-NO";
    const kw = (v) => (v === null ? "–" : `${tall(v, 2, sprak)} kW`);
    // Skjermleseren har ikke skiven aa se paa, saa enheten skrives ut.
    // "kW" leses som bokstaver, "kilowatt" leses som ordet.
    const lest = (v) => (v === null ? "ukjent verdi" : `${tall(v, 2, sprak)} kilowatt`);

    this._felt.projisert.textContent = harTall ? kw(projisertKw) : "–";
    this._felt.na.textContent = harTall ? kw(naKw) : "–";
    this._felt.topp3.textContent = harTall ? kw(slepeKw) : "–";

    // Trinnteksten trengs i to utgaver: den synlige bruker "kW" og kan
    // innlede fritt, mens etiketten skriver ut enheten og ikke skal gjenta
    // "maaneden ligger an til", som alt staar i setningen foer.
    const harTrinn = harTall && kostnad && !erUgyldig(kostnad) && this._trinn?.aktivt;
    const trinnlinjer = (enhet, innledning) => {
      if (!harTrinn) return [];
      const a = this._trinn.aktivt;
      const n = this._trinn.neste;
      const ut = [
        `${innledning} kapasitetstrinnet ${tall(a.fra, 0, sprak)} til` +
          ` ${tall(a.til, 0, sprak)} ${enhet}, ${a.kr} kroner i måneden.`,
      ];
      if (n) {
        ut.push(
          `Neste trinn starter på ${tall(n.fra, 0, sprak)} ${enhet} og koster` +
            ` ${n.kr} kroner i måneden, altså ${kostnad.state} kroner mer.`
        );
      }
      return ut;
    };

    // Etiketten maa baere hele betydningen, ikke bare tallene: hva timen ender
    // paa, hva som gaar naa, hva maaneden ligger an til og hva det koster.
    const skive = this._dsoNavn ? `Effektmåler for ${this._dsoNavn}` : "Effektmåler";
    // Uten avlesning maa etiketten si hvorfor. «Venter» og «utilgjengelig» er
    // to ulike beskjeder til den som lurer paa hvorfor skiven er tom.
    const uten = venter
      ? "Ingen avlesning: Effektvakt har ingen måling å vise ennå,"
      : `Ingen avlesning: ${this._config.entity} er utilgjengelig,`;
    const etikett = harTall
      ? [
          `${skive}.`,
          `Timen ender på ${lest(projisertKw)} hvis forbruket fortsetter som nå.`,
          `${lest(naKw)} går akkurat nå.`,
          `Måneden ligger an til ${lest(slepeKw)}, som er topp-3-snittet og det du betaler for.`,
          ...trinnlinjer("kilowatt", "Det er"),
        ]
      : [`${skive}.`, uten, "så viserne står parkert på null."];
    this._svg.setAttribute("aria-label", etikett.join(" "));

    // Beskrivelsen sier hva merkene paa skiven betyr. Etiketten over sier hva
    // de staar paa. Delt slik gjentas ingenting for skjermleseren.
    this._tekstalternativ.textContent = harTall
      ? FORKLARING
      : `${FORKLARING} Viserne viser ingen avlesning nå.`;

    const synlig = harTall
      ? trinnlinjer("kW", "Måneden ligger an til")
      : [
          venter
            ? "Effektvakt har ingen måling å vise ennå, så viserne står parkert på null."
            : `${this._config.entity} er utilgjengelig, så viserne står parkert på null.`,
        ];
    this._kostnad.textContent = synlig.join(" ");
    this._kostnad.hidden = synlig.length === 0;
  }
}

class EffektvaktCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._stiler = null;
    this._henter = false;
    this._forsok = 0;
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
    if (this._forsok >= EDITOR_MAKS_FORSOK) return;
    this._henter = true;
    try {
      const svar = await this._hass.callWS({ type: WS_FACEPLATE, entity_id: this._config.entity });
      this._stiler = svar.stiler ?? {};
      this._tegn();
    } catch {
      // Samme kappløp som i kortet. Uten dette ble stilvelgeren borte resten
      // av økten fordi det første forsøket traff en HA som ikke var klar.
      this._forsok += 1;
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
