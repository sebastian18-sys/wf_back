import sys, json
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re

def main():
    # try:
    #     raw = sys.stdin.read().strip() or "{}"
    #     payload = json.loads(raw)
    # except Exception as e:
    #     print(json.dumps({"error": str(e)}))
    #     sys.exit(1)

    # #demo
    # records = payload.get("records", [{"value": 1}, {"value": 2}, {"value": 3}])
    # df = pd.DataFrame(records)
    # total = float(df["value"].sum()) if "value" in df.columns else 0

    # #demo simple with ThreadPoolExecutor
    # def sq(x): return x*x
    # with ThreadPoolExecutor(max_workers=4) as ex:
    #     squares = list(ex.map(sq, [1, 2, 3, 4]))

    # result = {
    #     "message": "PYTHON SUCCESS",
    #     "total": total,
    #     "squares": squares,
    #     "regex_demo": bool(re.search(r"\d+", "abc123")),
    # }
    # print(json.dumps(result))

    print("EXEC PYTHON!")

if __name__ == "__main__":
    main()