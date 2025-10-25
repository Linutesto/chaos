
import sys
import json
from default_api import google_web_search

if __name__ == "__main__":
    query = " ".join(sys.argv[1:])
    if not query:
        print(json.dumps({"error": "No query provided."}))
        sys.exit(1)

    try:
        results = google_web_search(query=query)
        print(json.dumps(results))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
