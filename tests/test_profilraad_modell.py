"""Profilenergi avgrenser bidraget uten aa endre den fysiske lastheuristikken."""

from datetime import date

from custom_components.effektvakt.modell import vurder_kuttkriterium

DAG = date(2026, 10, 10)
TRINN = [(2, 155), (5, 250), (10, 415), (float("inf"), 600)]


def _kriterium(**kwargs):
    return vurder_kuttkriterium(
        trinn=TRINN,
        daily_max_kw={date(2026, 10, 8): 5, date(2026, 10, 9): 5},
        today=DAG,
        projected_kw=6,
        actual_kwh_this_hour=1,
        elapsed_h=1 / 6,
        tilgjengelig_kutt_kw=2,
        **kwargs,
    )


def test_kort_profil_gjoer_ikke_en_fysisk_stor_last_til_liten():
    result = _kriterium(tilgjengelig_kuttenergi_kwh=1)
    assert result.kutt_mulig
    assert result.unngaaelig_besparelse_kr == 165
    assert not result.oppfylt


def test_lite_forventet_bidrag_redder_ikke_trinnet():
    result = _kriterium(tilgjengelig_kuttenergi_kwh=0.2)
    assert not result.kutt_mulig
    assert result.unngaaelig_besparelse_kr == 0


def test_profilbidrag_kan_bevare_maanedsmaal_uten_aa_redde_hele_timen():
    assert _kriterium(tilgjengelig_kuttenergi_kwh=0.2, valgt_maal_kw=5).bevarer_maanedsmaal
    assert not _kriterium(tilgjengelig_kuttenergi_kwh=0, valgt_maal_kw=5).bevarer_maanedsmaal


def test_energibidrag_kan_ikke_fjerne_allerede_brukt_energi():
    result = vurder_kuttkriterium(
        trinn=TRINN,
        daily_max_kw={date(2026, 10, 8): 5, date(2026, 10, 9): 5},
        today=DAG,
        projected_kw=6.1,
        actual_kwh_this_hour=6,
        elapsed_h=0.99,
        tilgjengelig_kutt_kw=2,
        tilgjengelig_kuttenergi_kwh=100,
    )
    assert result.unngaaelig_besparelse_kr == 0
    assert not result.kutt_mulig
