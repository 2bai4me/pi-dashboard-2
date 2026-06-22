"""Regression-Tests fuer _conflict_keyword_matches in workflow.py.

BUGFIX 22.06.2026: Wortgrenzen-Match verhindert False-Positives.
Vorher: 'tba' matched in 'sichtbar' (weil 'sich-TBA-r' als Substring).
Nachher: 'tba' matched nur als eigenstaendiges Wort.

Diese Tests sichern den Fix ab.
"""
from __future__ import annotations

import pytest

from app.routers.workflow import _conflict_keyword_matches


class TestWortKeywordsMitWortgrenzen:
    """Wort-Keywords (alphanumerisch) muessen Wortgrenzen respektieren."""

    @pytest.mark.parametrize("kw", ["tba", "tbd", "fixme", "klären", "unbekannt"])
    def test_keyword_als_eigenes_wort_wird_gefunden(self, kw):
        """Eigenstaendiges Wort im Text wird erkannt."""
        text = f"das ist ein {kw} marker im text"
        assert _conflict_keyword_matches(kw, text) is True

    @pytest.mark.parametrize("kw", ["tba", "tbd", "fixme", "klären", "unbekannt"])
    def test_keyword_als_substring_in_laengerem_wort_wird_NICHT_gefunden(self, kw):
        """Substring-Match (False-Positive) wird verhindert.

        Vor dem BUGFIX: 'tba' wurde in 'sichtbar' gefunden.
        Nach dem BUGFIX: 'tba' wird NUR in eigenstaendigen Woertern gefunden.
        """
        # Finde ein laengeres Wort, das 'kw' als Substring enthaelt
        # (aber das ganze Wort ist kein Konflikt-Keyword).
        substr_examples = {
            "tba": "sichtbar",       # sich-TBA-r
            "tbd": "vorabbestimmung",  # vorabd...-bestimmung
            "fixme": "fixiert",       # fix-ME-iert
            "klären": "erklären",     # er-KLÄR-en
            "unbekannt": "unbekanntes",  # gleicher Wortstamm
        }
        long_word = substr_examples[kw]
        text = f"das wort {long_word} ist hier"
        assert _conflict_keyword_matches(kw, text) is False, (
            f"BUG: '{kw}' wurde fälschlicherweise in '{long_word}' gefunden!"
        )


class TestSymbolKeywordsOhneWortgrenzen:
    """Symbol-Keywords (mit Sonderzeichen) werden als Substring gematcht."""

    @pytest.mark.parametrize("kw", ["todo:", "??", "???", "[todo]"])
    def test_symbol_keyword_wird_gefunden(self, kw):
        """Symbol-Keyword wird im Text gefunden."""
        text = f"hier steht ein {kw} marker"
        assert _conflict_keyword_matches(kw, text) is True

    @pytest.mark.parametrize("kw", ["todo:", "??", "???", "[todo]"])
    def test_symbol_keyword_nicht_vorhanden(self, kw):
        """Symbol-Keyword wird NICHT gefunden wenn nicht im Text."""
        text = "dieser text enthaelt das keyword nicht"
        assert _conflict_keyword_matches(kw, text) is False


class TestRealWorldFaelle:
    """Tests mit echten Task-Titeln und Beschreibungen aus der Praxis."""

    def test_sichtbar_matcht_nicht_auf_tba(self):
        """Der urspruengliche Bug-Fall: 'sichtbar' darf NICHT 'tba' matchen.

        Task 13b322a2b926 (Performance-Tabelle um Timestamp-Spalte erweitern)
        hatte die Description '...damit man sehen kann wie alt der eintrag ist.'
        und der Title '(Alter des Eintrags sichtbar)'. Beide enthalten 'tba'
        als Substring in 'sichtbar'.
        """
        title = "Performance-Tabelle um Timestamp-Spalte erweitern (Alter des Eintrags sichtbar)"
        desc = "In der Performance Tabelle soll ein Timestamp mit angezeigt werden damit man sehen kann wie alt der eintrag ist."
        full_text = f"{title} {desc}".lower()

        # Vor dem Fix: 'tba' wurde gefunden (False-Positive)
        # Nach dem Fix: 'tba' wird NICHT mehr gefunden
        assert _conflict_keyword_matches("tba", full_text) is False

    def test_echtes_tba_keyword_wird_trotzdem_gefunden(self):
        """Aber echtes 'tba' als eigenstaendiges Wort wird weiterhin erkannt."""
        # Aufrufer macht .lower() (siehe workflow.py:323)
        text = "die Anforderung ist noch TBA, bitte spaeter definieren".lower()
        assert _conflict_keyword_matches("tba", text) is True

    def test_echtes_fixme_keyword_wird_gefunden(self):
        """'fixme' als eigenstaendiges Wort wird gefunden."""
        text = "FIXME: hier muss noch was gefixt werden".lower()
        assert _conflict_keyword_matches("fixme", text) is True

    def test_fix_in_fixiertem_matcht_nicht(self):
        """'fix' in 'fixiertem' darf NICHT 'fixme' matchen."""
        text = "das problem wurde in einem fixierten branch geloest"
        assert _conflict_keyword_matches("fixme", text) is False


class TestEdgeCases:
    """Edge-Cases fuer robuste Wortgrenzen-Behandlung."""

    def test_leerer_text(self):
        assert _conflict_keyword_matches("tba", "") is False

    def test_keyword_am_textanfang(self):
        """Keyword am Anfang des Textes wird gefunden."""
        assert _conflict_keyword_matches("tba", "tba sollte ersetzt werden") is True

    def test_keyword_am_textende(self):
        """Keyword am Ende des Textes wird gefunden."""
        assert _conflict_keyword_matches("tba", "das wort am ende ist tba") is True

    def test_keyword_mit_satzzeichen_davor(self):
        """Wortgrenzen funktionieren auch mit Satzzeichen."""
        assert _conflict_keyword_matches("tba", "noch zu klaeren: tba.") is True

    def test_mehrfaches_vorkommen(self):
        """Mehrfaches Vorkommen wird auch erkannt."""
        assert _conflict_keyword_matches("tba", "tba und nochmal tba hier") is True

    def test_keyword_in_grossbuchstaben(self):
        """Test geht von bereits lowercased Text aus (Aufrufer macht .lower())."""
        # Caller ruft mit full_text.lower() auf, daher testen wir lowercase
        assert _conflict_keyword_matches("tba", "TBA" ) is False  # ohne .lower()
        assert _conflict_keyword_matches("tba", "tba") is True     # mit .lower()