import json, sys, collections, pathlib

def main():
    p = pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path("state")
    counts=collections.Counter(); by_agent=collections.Counter(); scores=set(); triggers=collections.Counter()
    for j in p.rglob("events.jsonl"):
        aid=j.parts[-2]
        try:
            for line in j.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    ev=json.loads(line)
                except Exception:
                    continue
                if ev.get("type")=="retrieval_inject":
                    counts["injects"]+=1; by_agent[aid]+=1
                    m=ev.get("meta",{})
                    if "min_score" in m: scores.add(float(m.get("min_score",0)))
                    tr=m.get("trigger")
                    if tr: triggers[tr]+=1
        except Exception:
            continue
    print("total injects:", counts["injects"]) 
    print("by agent:", by_agent.most_common(10))
    if scores: print("min_score (distinct):", sorted(scores))
    if triggers: print("triggers:", dict(triggers))

if __name__ == "__main__":
    main()

