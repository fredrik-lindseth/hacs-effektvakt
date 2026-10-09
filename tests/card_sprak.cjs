// Tester den ekte kortfilen med et lite DOM-skall, uten npm-avhengigheter.
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");
const { test } = require("node:test");
const path = require("node:path");

class Node {
  constructor() { this.children = []; this.style = {}; this.attributes = {}; this.textContent = "";
    this.classList = { toggle() {}, add() {}, remove() {} }; }
  append(...barn) { this.children.push(...barn); }
  replaceChildren(...barn) { this.children = barn; }
  setAttribute(key, value) { this.attributes[key] = value; }
  getAttribute(key) { return this.attributes[key]; }
  addEventListener() {}
  attachShadow() { this.shadowRoot = new Node(); }
}

function last() {
  const document = { createElement: () => new Node(), documentElement: { lang: "nb" } };
  const context = vm.createContext({ document, HTMLElement: Node, customElements: { define() {} },
    window: { localStorage: { getItem() { return null; }, setItem() {} } }, Intl, Date, console });
  const fil = path.join(__dirname, "../custom_components/effektvakt/www/effektvakt-card.js");
  vm.runInContext(readFileSync(fil, "utf8"), context);
  return { ...vm.runInContext("({kortSprak, kortTekst, EffektvaktCard, EffektvaktCardEditor})", context), context };
}

function kortMedTall(api) {
  const kort = new api.EffektvaktCard();
  kort.setConfig({ entity: "sensor.effektvakt_projisert_time_snitt" });
  kort._sikreSkive = () => {};
  kort._svg = new Node();
  kort._flagg = new Node();
  return kort;
}

function hass(language) {
  return { locale: { language }, states: { "sensor.effektvakt_projisert_time_snitt": {
    state: "4.25", attributes: { current_kw: 3.5 }, last_updated: "samme-tid" } } };
}

test("språkvalg følger locale, language-reserve og norsk fallback", () => {
  const api = last();
  assert.equal(api.kortSprak({ locale: { language: "en-GB" }, language: "nb" }), "en");
  assert.equal(api.kortSprak({ language: "en" }), "en");
  for (const language of ["nb", "nb-NO", "nn", "fr", ""]) {
    assert.equal(api.kortSprak({ language }), "nb");
  }
  assert.equal(api.kortSprak(undefined), "nb");
});

test("synlige etiketter og skjermlesertekst bytter uten ny sensoravlesning", () => {
  const api = last();
  const kort = kortMedTall(api);
  kort.hass = hass("nb");
  assert.equal(kort._etiketter.projisert.textContent, "Projisert");
  assert.equal(kort._felt.projisert.textContent, "4,25 kW");
  assert.match(kort._svg.getAttribute("aria-label"), /Effektmåler/);
  kort.hass = hass("en");
  assert.equal(kort._etiketter.projisert.textContent, "Projected");
  assert.equal(kort._etiketter.na.textContent, "Power now");
  assert.equal(kort._felt.projisert.textContent, "4.25 kW");
  assert.match(kort._svg.getAttribute("aria-label"), /The hour will end at 4.25 kilowatts/);
  assert.match(kort._tekstalternativ.textContent, /The red needle/);
  assert.equal(kort._config.entity, "sensor.effektvakt_projisert_time_snitt");
});

test("kostnader bevarer tarifførene i begge språk", () => {
  const api = last();
  const kort = kortMedTall(api);
  kort._trinn = { aktivt: { fra: 2, til: 5, kr: 562.5 }, neste: { fra: 5, til: 8, kr: 650 } };
  const kostnad = { state: "87.5", attributes: { kostnad_neste_trinn_kr: 87.5 } };
  kort._hass = hass("en");
  kort._skrivTekst("ok", 4.25, 3.5, 4, kostnad);
  assert.match(kort._kostnad.textContent, /NOK 562.50 per month/);
  assert.match(kort._kostnad.textContent, /increase of NOK 87.50/);
  kort._hass = hass("nb");
  kort._skrivTekst("ok", 4.25, 3.5, 4, kostnad);
  assert.match(kort._kostnad.textContent, /562,50 kroner i måneden/);
});

test("manglende måling, lasting og hentefeil har engelske forklaringer", () => {
  const api = last();
  const kort = kortMedTall(api);
  kort._hass = hass("en");
  kort._skrivTekst("venter", null, null, null, null);
  assert.match(kort._kostnad.textContent, /no measurement to display yet/);
  kort._skrivTekst("borte", null, null, null, null);
  assert.match(kort._kostnad.textContent, /is unavailable/);
  kort._svg = null; kort._henter = "aktiv";
  kort._visMelding();
  assert.equal(kort._melding.textContent, "Loading the dial …");
  kort._feil = "Unknown command";
  kort._visMelding();
  assert.match(kort._melding.textContent, /Could not load the dial/);
});

test("editoren følger språkbytte og kortvelgeren følger dokumentets språk", () => {
  const api = last();
  const editor = new api.EffektvaktCardEditor();
  editor.setConfig({ entity: "sensor.effektvakt_projisert_time_snitt" });
  editor._hentStiler = () => {};
  editor.hass = hass("nb");
  assert.equal(editor._skjema.computeLabel({ name: "tittel" }), "Tittel");
  editor.hass = hass("en");
  assert.equal(editor._skjema.computeLabel({ name: "tittel" }), "Title");
  assert.equal(editor._skjema.computeLabel({ name: "maks_kw" }), "Scale maximum");
  api.context.document.documentElement.lang = "en";
  assert.match(api.context.window.customCards[0].description, /Analog demand monitor/);
});
