from datetime import datetime


def _parse_ts(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return float(ts)
    if isinstance(ts, str):
        try:
            if ts.endswith("Z"):
                ts = ts[:-1]
            dt = datetime.fromisoformat(ts)
            return dt.timestamp()
        except ValueError:
            return None
    return None
