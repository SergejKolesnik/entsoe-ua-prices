"""Synthetic format fixtures; no copied source history or network calls."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from market_forecast.gas_indices_dry_run import run
from market_forecast.parsers.gas_indices import CEGH_HEADER, parse_ceghix, parse_ueex, parse_ueex_margin
from market_forecast.sources.base import RawResponse
from market_forecast.sources.gas_indices import CEGHIX_URL, UEEX_MARGIN_URL, UEEX_URL, fetch_gas_index

NOW = datetime(2026, 9, 9, tzinfo=timezone.utc)
CSV = ";".join(CEGH_HEADER) + "\n08.09.2026;CEGH VTP DA 2026-09-09;1;1;1;1;1;1;999;888;40.123\n"
HTML = '''З 1 липня 2022 року без урахування ПДВ
<h6>станом на&nbsp;08.09.2026</h6><table class="standard-table rates weighted"><tr>
<th>Ресурс (дата фіксації ціни)</th><th>по всіх умовах оплати грн/тис. куб. м</th>
<th>передоплата грн/тис. куб. м</th><th>післяплата грн/тис. куб. м</th></tr>
<tr><td>вересня&nbsp;2026<br><span class="fd">(01.09.2026)</span></td>
<td><span class=u>18&nbsp;000,12</span><span class=e>999,99</span></td>
<td><span class=u>17 000,34</span><span class=e>888,88</span></td>
<td><span class=u>19 000,56</span><span class=e>777,77</span></td></tr></table>'''
MARGIN = '''<input type="text" name=ogts_date id=ogts_date placeholder="08.09.2026" readonly>
<table id="ogts_table"><tbody>
<tr><td>Маржинальна ціна продажу:</td><td><span>16&nbsp;515,00</span> грн/тис. куб. м. без ПДВ</td></tr>
<tr><td class=vat>з ПДВ</td><td class=vat><span>19&nbsp;818,00</span> грн/тис. куб. м. з ПДВ</td></tr>
<tr><td>Середньозважена ціна короткострокових стандартизованих продуктів:</td><td><span>18&nbsp;350,00</span> грн/тис. куб. м. без ПДВ</td></tr>
<tr><td class=vat>з ПДВ</td><td class=vat><span>22&nbsp;020,00</span> грн/тис. куб. м. з ПДВ</td></tr>
<tr><td>Маржинальна ціна придбання:</td><td><span>20&nbsp;185,00</span> грн/тис. куб. м. без ПДВ</td></tr>
<tr><td class=vat></td><td class=vat><span>24&nbsp;222,00</span> грн/тис. куб. м. з ПДВ</td></tr>
</tbody></table>'''


def raw(text=CSV, source="ceghix"):
    urls = {"ceghix": CEGHIX_URL, "ueex": UEEX_URL, "ueex_margin": UEEX_MARGIN_URL}
    return RawResponse(text.encode(), "text/csv" if source == "ceghix" else "text/html", 200, urls[source])


class GasIndexTests(unittest.TestCase):
    def test_cegh_uses_only_index_and_delivery_contract(self):
        row = parse_ceghix(raw(), NOW).observations[0]
        self.assertEqual(row.price, Decimal("40.123"))
        self.assertEqual(row.delivery_date.day, 9)
        self.assertEqual(row.available_at, NOW)

    def test_cegh_missing_is_not_vwap_and_weekend_not_daily(self):
        text = CSV + CSV.splitlines()[1].replace("40.123", "-") + "\n"
        text += CSV.splitlines()[1].replace("DA 2026-09-09", "WE 2026-09-12/13") + "\n"
        result = parse_ceghix(raw(text), NOW)
        self.assertEqual((len(result.observations), result.missing_prices, result.unsupported_contracts), (1, 1, 1))

    def test_cegh_rejects_corruption(self):
        for text in (CSV.replace("CEGHIX", "UNKNOWN"), CSV.replace("40.123", "NaN"),
                     CSV.replace("40.123", "0"), CSV.replace("40.123", ""),
                     CSV + CSV.splitlines()[1], CSV.replace("2026-09-09", "2026-09-08"),
                     CSV.replace(";888;", ";"), CSV.replace("40.123", "-")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_ceghix(raw(text), NOW)

    def test_malformed_da_is_not_counted_as_unsupported(self):
        for contract in ('CEGH VTP DA unknown', 'CEGH VTP DA 2026-09-XX'):
            text = CSV + CSV.splitlines()[1].replace('CEGH VTP DA 2026-09-09', contract)
            with self.subTest(contract=contract), self.assertRaisesRegex(ValueError, 'Malformed CEGH DA'):
                parse_ceghix(raw(text), NOW)
        text = CSV + CSV.splitlines()[1].replace('2026-09-09', '2026-09-08').replace('40.123', '-')
        with self.assertRaisesRegex(ValueError, 'delivery must follow'):
            parse_ceghix(raw(text), NOW)

    def test_ueex_rejects_html_that_could_truncate_prices(self):
        for html in (
            HTML.replace('18&nbsp;000,12', '18<span>000</span>,12'),
            HTML.replace('18&nbsp;000,12</span>', '18&nbsp;000,12'),
            HTML.replace('<td><span class=u>', '<td colspan="2"><span class=u>', 1),
            HTML.replace('</td>', '', 1),
            HTML.replace('</tr>', '', 1),
            HTML.replace('</td>', '</th>', 1),
            HTML.replace('<tr><td>', '<table><tr><td>', 1),
            HTML.replace('</table>', '<tr><td>unfinished</table>'),
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_ueex(raw(html, 'ueex'), NOW)

    def test_ueex_currency_payment_and_fixing_date(self):
        rows = parse_ueex(raw(HTML, "ueex"), NOW).observations
        self.assertEqual([r.price for r in rows], [Decimal("18000.12"), Decimal("17000.34"), Decimal("19000.56")])
        self.assertEqual([r.payment_terms for r in rows], ["all", "prepayment", "postpayment"])
        self.assertEqual(rows[0].vat, "excluded")

    def test_ueex_rejects_drift_duplicates_and_legacy_vat(self):
        for html in (HTML.replace("передоплата", "невідомо"), HTML.replace("class=u", "class=x"),
                     HTML.replace("тис.", "МВт"), HTML + HTML,
                     HTML.replace("18&nbsp;000,12", "NaN"),
                     HTML.replace("01.09.2026", "01.06.2022"), HTML.replace("</table>", ""),
                     HTML.replace("</table>", HTML[HTML.index('<tr><td>'):])):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_ueex(raw(html, "ueex"), NOW)

    def test_ueex_missing_is_explicit(self):
        result = parse_ueex(raw(HTML.replace("18&nbsp;000,12", "-"), "ueex"), NOW)
        self.assertEqual((len(result.observations), result.missing_prices), (2, 1))

    def test_ueex_margin_uses_only_explicit_no_vat_rows(self):
        rows = parse_ueex_margin(raw(MARGIN, "ueex_margin"), NOW).observations
        self.assertEqual([row.series for row in rows], [
            "UEEX_MARGIN_SALE", "UEEX_MARGIN_WEIGHTED_SHORT_TERM", "UEEX_MARGIN_PURCHASE",
        ])
        self.assertEqual([row.price for row in rows], [
            Decimal("16515.00"), Decimal("18350.00"), Decimal("20185.00"),
        ])
        self.assertTrue(all(row.vat == "excluded" for row in rows))

    def test_ueex_margin_rejects_drift_or_ambiguous_values(self):
        for html in (
            MARGIN.replace("Маржинальна ціна продажу", "Невідомий показник"),
            MARGIN.replace("без ПДВ", "з ПДВ", 1),
            MARGIN.replace("name=ogts_date", "name=other_date"),
            MARGIN.replace("</table>", ""),
            MARGIN.replace("<tr>", "<tr><td colspan=2>", 1),
        ):
            with self.subTest(html=html), self.assertRaises(ValueError):
                parse_ueex_margin(raw(html, "ueex_margin"), NOW)

    def test_empty_ueex_cell_and_legacy_rows_are_reported(self):
        empty = HTML.replace('<span class=u>17 000,34</span><span class=e>888,88</span>', '')
        legacy = HTML[HTML.index('<tr><td>'):HTML.index('</table>')].replace('01.09.2026', '01.06.2022')
        result = parse_ueex(raw(empty.replace('</table>', legacy + '</table>'), 'ueex'), NOW)
        self.assertEqual((len(result.observations), result.missing_prices, result.unsupported_vat_rows), (2, 1, 1))

    def test_stale_future_or_missing_snapshot_rejected(self):
        for content in (HTML.replace('08.09.2026', '01.09.2026'),
                        HTML.replace('08.09.2026', '10.09.2026'),
                        HTML.replace('станом на', 'дата'),
                        HTML.replace('без урахування ПДВ', 'невідомо')):
            with self.subTest(content=content), self.assertRaises(ValueError):
                parse_ueex(raw(content, 'ueex'), NOW)
        with self.assertRaises(ValueError):
            parse_ceghix(raw(), NOW.replace(day=20))

    def test_model_rejects_invalid_native_contract(self):
        row = parse_ceghix(raw(), NOW).observations[0]
        for changes in ({"price": 40.1}, {"price": Decimal("Infinity")}, {"currency": "UAH"},
                        {"vat": "excluded"}, {"raw_sha256": "bad"}, {"series": "TTF"},
                        {"available_at": NOW.replace(tzinfo=None)}, {"source_url": "https://evil.test/"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(row, **changes)

    def test_wrong_provenance_and_encoding(self):
        for value in (replace(raw(), source_url=UEEX_URL), replace(raw(), content=b"\xff")):
            with self.assertRaises(ValueError):
                parse_ceghix(value, NOW)

    @patch("market_forecast.gas_indices_dry_run.fetch_gas_index")
    def test_dry_run_evidence_and_atomic_validation(self, fetch):
        with tempfile.TemporaryDirectory() as temp:
            fetch.side_effect = [raw(), raw(HTML, "ueex"), raw(MARGIN, "ueex_margin")]
            output = Path(temp) / "ok"
            result = run(output, retrieved_at=NOW)
            self.assertFalse(result["database_writes"])
            self.assertEqual(len(json.loads((output / "observations.json").read_text())), 7)
            self.assertEqual((output / "ceghix.raw").read_bytes(), raw().content)
            with self.assertRaises(FileExistsError):
                run(output, retrieved_at=NOW)
            fetch.reset_mock()
            replay = run(Path(temp) / "replay", output)
            fetch.assert_not_called()
            self.assertEqual(replay["mode"], "replay")
            (output / "ceghix.raw").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                run(Path(temp) / "tampered", output)
            fetch.side_effect = [raw(), raw("broken", "ueex"), raw(MARGIN, "ueex_margin")]
            failed = Path(temp) / "bad"
            with self.assertRaises(ValueError):
                run(failed, retrieved_at=NOW)
            self.assertFalse((failed / "observations.json").exists())
            self.assertEqual(json.loads((failed / "manifest.json").read_text())["status"], "failed")

    @patch("market_forecast.sources.gas_indices.requests.get")
    def test_transport_bounds_and_status(self, get):
        response = MagicMock()
        get.return_value.__enter__.return_value = response
        response.status_code = 200
        response.headers = {"Content-Type": "application/csv"}
        response.iter_content.return_value = [b"abc"]
        self.assertEqual(fetch_gas_index("ceghix").content, b"abc")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        for status, content_type, chunks in ((302, "application/csv", [b"x"]),
                                            (200, "text/html", [b"x"]),
                                            (200, "application/csv", []),
                                            (200, "application/csv", [b"x" * 10_000_001])):
            response.status_code = status
            response.headers = {"Content-Type": content_type}
            response.iter_content.return_value = chunks
            with self.assertRaises(ValueError):
                fetch_gas_index("ceghix")
