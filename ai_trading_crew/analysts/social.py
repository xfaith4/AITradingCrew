import os
import re
import json
import datetime
import pytz
import http.client

from ai_trading_crew.models import SentimentSnapshot


def fetch_stocktwits_messages(symbol : str, desired_count : int, lower_bound : datetime):
    messages = []
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    empty_count = 0
    pagination_max = None
    conn = http.client.HTTPSConnection("stocktwits.p.rapidapi.com")
    headers = {
        'x-rapidapi-key': os.getenv("RAPID_API_KEY"),
        'x-rapidapi-host': "stocktwits.p.rapidapi.com"
    }
    
    while len(messages) < desired_count:
        endpoint = f"/streams/symbol/{symbol}.json?limit={desired_count}"
        if pagination_max:
            endpoint += f"&max={pagination_max}"
        conn.request("GET", endpoint, headers=headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        try:
            json_data = json.loads(data)
        except Exception as e:
            print("Error decoding StockTwits JSON:", e)
            break
        
        page_msgs = json_data.get("messages", [])
        if not page_msgs:
            break
        
        stop = False
        for msg in page_msgs:
            created_at_str = msg.get("created_at")
            if not created_at_str:
                continue
            dt = datetime.datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ")
            tz_est = pytz.timezone("US/Eastern")
            dt = pytz.utc.localize(dt).astimezone(tz_est)
            if dt < lower_bound:
                stop = True
                break
            body = msg.get("body", "").strip()
            username = msg.get("user", {}).get("username", "Unknown")
            formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S %Z")
            
            if not body:
                empty_count += 1
            else:
                # Check sentiment from the entities field
                sentiment_info = msg.get("entities", {}).get("sentiment")
                if sentiment_info and isinstance(sentiment_info, dict):
                    sentiment_value = sentiment_info.get("basic")
                    if sentiment_value:
                        sentiment_value = sentiment_value.lower()
                        if sentiment_value == "bullish":
                            bullish_count += 1
                        elif sentiment_value == "bearish":
                            bearish_count += 1
                        else:
                            neutral_count += 1
                    else:
                        neutral_count += 1
                else:
                    neutral_count += 1
            
            messages.append(f"- {formatted_time}: {body}\n")
            if len(messages) >= desired_count:
                break
        if len(messages) >= desired_count or stop:
            break
        
        cursor = json_data.get("cursor", {})
        pagination_max = cursor.get("max")
        if not (cursor.get("more") and pagination_max):
            break
    return messages, bullish_count, bearish_count, neutral_count

def format_stocktwits_data(symbol: str, messages: list, bullish: int, bearish: int, neutral: int) -> str:
    """Formats StockTwits data into standardized string format."""
    return (
        f"Stock: {symbol}\n"
        f"Bullish: {bullish}, Bearish: {bearish}, Neutral: {neutral}\n"
        f"Messages:\n" + "\n".join(messages) + "\n"
    )

# A message line is "<time>: <body>". SentimentSnapshot strips whitespace from
# each item, so an empty body loses the space after the colon; this pattern
# spots that case so the formatter can restore the original line.
_EMPTY_BODY_LINE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \w+:")


def fetch_stocktwits_sentiment(
    symbol: str,
    fetch_limit: int,
    since_date: datetime.datetime,
    as_of: datetime.datetime | None = None,
) -> SentimentSnapshot:
    """Fetch StockTwits messages and tag counts as a SentimentSnapshot (A4).

    ``messages`` holds one ``"<time>: <body>"`` line per message, newest
    first, as the API returns them. ``as_of`` defaults to now (UTC).
    """
    messages, bullish, bearish, neutral = fetch_stocktwits_messages(symbol, fetch_limit, since_date)
    return SentimentSnapshot(
        symbol=symbol,
        as_of=as_of or datetime.datetime.now(datetime.timezone.utc),
        bullish=bullish,
        bearish=bearish,
        neutral=neutral,
        messages=[line.removeprefix("- ").removesuffix("\n") for line in messages],
    )


def format_stocktwits_sentiment(snapshot: SentimentSnapshot) -> str:
    """Render a SentimentSnapshot as the StockTwits prompt text."""
    lines = []
    for message in snapshot.messages:
        if _EMPTY_BODY_LINE.fullmatch(message):
            message += " "
        lines.append(f"- {message}\n")
    return format_stocktwits_data(snapshot.symbol, lines, snapshot.bullish, snapshot.bearish, snapshot.neutral)


def get_stocktwits_context(symbol: str, fetch_limit: int, since_date: datetime.datetime) -> str:
    """Get formatted StockTwits data for a symbol."""
    return format_stocktwits_sentiment(fetch_stocktwits_sentiment(symbol, fetch_limit, since_date))
