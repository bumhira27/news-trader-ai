from datetime import datetime, timezone

from app.providers.forexfactory import ForexFactoryProvider


class DummyResponse:
    def __init__(self, text: str):
        self.text = text


HISTORICAL_HTML = """
<html>
  <body>
    <div>Calendar Time Zone: America/New_York (GMT -4)</div>
    <table class="calendar__table">
      <tbody>
        <tr class="calendar__row calendar_row">
          <td class="calendar__cell calendar__date date">Fri Aug 7</td>
          <td class="calendar__cell calendar__time time">8:30am</td>
          <td class="calendar__cell calendar__currency currency">USD</td>
          <td class="calendar__cell calendar__impact impact calendar__impact--high">
            <span title="High Impact"></span>
          </td>
          <td class="calendar__cell calendar__event event">
            <a href="/calendar/107-nonfarm-payrolls">
              <span class="calendar__event-title">Nonfarm Payrolls</span>
            </a>
          </td>
          <td class="calendar__cell calendar__actual actual">165K</td>
          <td class="calendar__cell calendar__forecast forecast">150K</td>
          <td class="calendar__cell calendar__previous previous">143K</td>
        </tr>
        <tr class="calendar__row calendar_row">
          <td class="calendar__cell calendar__date date"></td>
          <td class="calendar__cell calendar__time time"></td>
          <td class="calendar__cell calendar__currency currency">USD</td>
          <td class="calendar__cell calendar__impact impact calendar__impact--medium">
            <span title="Medium Impact"></span>
          </td>
          <td class="calendar__cell calendar__event event">
            <span class="calendar__event-title">Unemployment Rate</span>
          </td>
          <td class="calendar__cell calendar__actual actual">4.2%</td>
          <td class="calendar__cell calendar__forecast forecast">4.3%</td>
          <td class="calendar__cell calendar__previous previous">4.3%</td>
        </tr>
      </tbody>
    </table>
  </body>
</html>
"""


def test_parse_historical_html_and_timezone():
    provider = ForexFactoryProvider()
    records = provider._parse_html(
        HISTORICAL_HTML,
        source_url="https://www.forexfactory.com/calendar?month=aug.2026",
        year=2026,
    )

    assert len(records) == 2
    assert records[0]["title"] == "Nonfarm Payrolls"
    assert records[0]["country"] == "USD"
    assert records[0]["impact"] == "High"
    assert records[0]["actual"] == "165K"
    assert records[0]["forecast"] == "150K"
    assert records[0]["previous"] == "143K"
    assert records[0]["url"] == "https://www.forexfactory.com/calendar/107-nonfarm-payrolls"
    assert records[0]["date"] == "2026-08-07T08:30:00-04:00"
    assert records[1]["title"] == "Unemployment Rate"
    assert records[1]["impact"] == "Medium"


def test_historical_range_uses_month_endpoint():
    provider = ForexFactoryProvider()
    requested_urls = []

    def fake_get(url: str):
        requested_urls.append(url)
        return DummyResponse(HISTORICAL_HTML)

    provider._get_with_retry = fake_get

    records = provider.fetch_events(
        start_date=datetime(2026, 8, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 8, 31, 23, 59, 59, tzinfo=timezone.utc),
    )

    assert requested_urls == ["https://www.forexfactory.com/calendar?month=aug.2026"]
    assert len(records) == 2
