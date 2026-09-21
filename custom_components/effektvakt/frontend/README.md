# Statiske filer for Effektvakt-kortet

Alt i denne katalogen serveres av integrasjonen paa `/effektvakt-static`, uten
innlogging. Legg bare inn filer som taaler aa vaere offentlige.

`effektvakt-card.js` er selve Lovelace-kortet. URL-en meldes inn med
`add_extra_js_url` fra `async_setup`, med `?v=<versjon fra manifest.json>` som
cache-buster, saa kortet trenger ingen ressursregistrering i Lovelace.
