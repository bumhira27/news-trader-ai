from datetime import date

from app.ingest import CalendarParser, make_source_key, parse_ff_time


def test_parse_ff_time_returns_utc():
    value = parse_ff_time("8:30am", date(2026, 8, 3))
    assert value is not None
    assert value.tzinfo is not None


def test_parser_extracts_core_fields():
    html = '''
    <table>
      <tr class="calendar__row" data-day-dateline="1785628800">
        <td class="calendar__time">8:30am</td>
        <td class="calendar__currency">USD</td>
        <td class="calendar__impact"><span class="icon--ff-impact-red" title="High"></span></td>
        <td class="calendar__event"><a href="/calendar/event/1">CPI y/y</a></td>
        <td class="calendar__actual">2.7%</td>
        <td class="calendar__forecast">2.8%</td>
        <td class="calendar__previous">2.9%</td>
      </tr>
    </table>
    '''
    parser = CalendarParser()
    parser.feed(html)
    assert len(parser.rows) == 1
    assert parser.rows[0]["currency"] == "USD"
    assert parser.rows[0]["event"] == "CPI y/y"
    assert parser.rows[0]["actual"] == "2.7%"
    assert parser.rows[0]["forecast"] == "2.8%"
    assert parser.rows[0]["previous"] == "2.9%"


def test_source_key_is_deterministic():
    event = {
        "currency": "USD",
        "event": "CPI y/y",
        "timestamp_utc": parse_ff_time("8:30am", date(2026, 8, 3)),
    }
    assert make_source_key(event) == make_source_key(event)
