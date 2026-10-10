# Statiske filer for Effektvakt-kortet

Katalogen serveres uten innlogging på `/effektvakt-static`; legg bare offentlige filer her. Navnet `www` hindrer kollisjon med Python-modulen `frontend.py`.

`frontend.py` registrerer `effektvakt-card.js?v=<manifestversjon>` som modul i Lovelace. Ved YAML-ressurser må brukeren legge den inn selv. Se [kortoppsettet](../../../docs/dashboard-kort.md#ressurser-i-yaml-modus).
