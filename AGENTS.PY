# -----------------------------
# Agent implementations (simple, extensible)
# -----------------------------
MOCK_API_BASE = "http://127.0.0.1:8001"

class DataCollectorAgent:
    """Collects raw signals from configured sources via the mock API."""
    def __init__(self, sources:List[str]=None):
        self.sources = sources or ["jira","sharepoint","confluence","outlook","teams","zoom_transcripts","azure_devops"]

    def fetch_all(self) -> Dict[str, Any]:
        collected = {}
        for s in self.sources:
            try:
                r = requests.get(f"{MOCK_API_BASE}/sources/{s}")
                if r.status_code==200:
                    collected[s] = r.json()
                else:
                    collected[s] = []
            except Exception as e:
                print(f"Error fetching {s}: {e}")
                collected[s] = []
        return collected

class GrainClassifierAgent:
    """Routes events to a grain using basic keyword matching and project fields."""
    def __init__(self, grains:List[str]):
        # grains should be canonical names like 'mobile-v3.2'
        self.grains = grains

    def assign(self, collected:Dict[str,Any]) -> Dict[str, Dict[str,List[Dict]]]:
        # returns {grain: {source: [events]}}
        grain_map = {g: {} for g in self.grains}
        # naive mapping: check event['project'] or search text for grain keywords
        for source, events in collected.items():
            for ev in events:
                assigned = None
                if isinstance(ev, dict) and 'project' in ev and ev['project'] in self.grains:
                    assigned = ev['project']
                else:
                    # check textual fields
                    text = ' '.join([str(v) for v in ev.values()]) if isinstance(ev, dict) else str(ev)
                    for g in self.grains:
                        if g.replace('-',' ') in text or g in text:
                            assigned = g
                            break
                if assigned is None:
                    # put into a 'unassigned' bucket on first grain
                    assigned = self.grains[0]
                grain_map[assigned].setdefault(source, []).append(ev)
        return grain_map

class SummarizerAgent:
    """Creates short digest summaries per grain."""
    def summarize(self, grain:str, events:Dict[str,List[Dict]]) -> Dict[str,Any]:
        # Simple heuristics: counts of ticket statuses, recent notes, and top mentions
        summary = {
            "grain": grain,
            "timestamp": datetime.utcnow().isoformat(),
            "highlights": [],
            "state": {}
        }
        # collect textual corpus
        corpus = []
        for src, evs in events.items():
            for e in evs:
                # pick representative fields
                txt = ''
                if isinstance(e, dict):
                    for key in ['summary','title','content','transcript','body','text']:
                        if key in e:
                            txt += ' ' + str(e[key])
                corpus.append(txt)
        # find simple highlights
        joined = '\n'.join(corpus)
        # find lines with TODO, Action, pending, needs
        for line in joined.split('\n'):
            if any(kw in line.lower() for kw in ['todo','action','pending','need','needs','blocker','blocked','approve','approval','design']):
                summary['highlights'].append(line.strip())
        # state: quick counts
        ticket_counts = {}
        for src in ['jira','azure_devops']:
            ticket_counts[src] = len(events.get(src, []))
        summary['state']['ticket_counts'] = ticket_counts
        summary['excerpt'] = joined[:800]
        return summary

class ActionExtractorAgent:
    """Extracts 'What, Who, By When' style actions using regex heuristics."""
    ACTION_PATTERNS = [r"action[:\-]?\s*(.+)", r"todo[:\-]?\s*(.+)", r"assign to @?(\w+)", r"@?(\w+) to review", r"by\s+(\d{4}-\d{2}-\d{2})"]

    def extract(self, grain:str, events:Dict[str,List[Dict]]) -> List[Dict]:
        actions = []
        for src, evs in events.items():
            for e in evs:
                text = ' '.join([str(v) for v in e.values()]) if isinstance(e, dict) else str(e)
                # find simple action sentences
                # split into sentences
                sentences = re.split(r"(?<=[.?!])\s+", text)
                for s in sentences:
                    s_low = s.lower()
                    if any(k in s_low for k in ['todo','action','assign','due','by','please']):
                        # try to find who and when
                        who_match = re.search(r"@?(\w+)", s)
                        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", s)
                        action = {
                            'grain': grain,
                            'source': src,
                            'text': s.strip(),
                            'who': who_match.group(1) if who_match else None,
                            'when': date_match.group(1) if date_match else None,
                            'extracted_at': datetime.utcnow().isoformat()
                        }
                        actions.append(action)
        # dedupe simple
        uniq = { (a['text'], a['who'], a['when']): a for a in actions }
        return list(uniq.values())

class OrchestratorAgent:
    """Decides whether to meet or go async based on unresolved actions / blockers."""
    def __init__(self, meeting_threshold:int=2):
        self.meeting_threshold = meeting_threshold

    def decide(self, grain:str, summary:Dict[str,Any], actions:List[Dict]) -> Dict[str,Any]:
        # Simple rules:
        # - if any highlight contains 'blocker' or 'blocked' -> meet
        # - if number of actions without who or when > threshold -> meet
        # - else async digest
        decision = {'grain': grain, 'mode': 'async', 'reason': [], 'agenda': None}
        highlights = ' '.join(summary.get('highlights', []))
        if 'block' in highlights.lower():
            decision['mode'] = 'meet'
            decision['reason'].append('blocker mentioned')
        unresolved = [a for a in actions if not a.get('who') or not a.get('when')]
        if len(unresolved) >= self.meeting_threshold:
            decision['mode'] = 'meet'
            decision['reason'].append(f'{len(unresolved)} unresolved actions')
        if decision['mode']=='meet':
            # draft a short agenda from unresolved actions
            agenda_items = [a['text'] for a in unresolved[:8]]
            decision['agenda'] = {
                'duration_minutes': 15,
                'items': agenda_items
            }
        return decision

class NudgerAgent:
    """Sends nudges (here: write to a simple notifications.json in mock_store)."""
    NOTIF_PATH = os.path.join(MOCK_DIR, 'notifications.json')

    def __init__(self):
        pass

    def push(self, notifications:List[Dict]):
        existing = []
        if os.path.exists(self.NOTIF_PATH):
            with open(self.NOTIF_PATH) as f:
                try:
                    existing = json.load(f)
                except:
                    existing = []
        existing.extend(notifications)
        with open(self.NOTIF_PATH, 'w') as f:
            json.dump(existing, f, indent=2)
        # in real life, integrate with Teams bot / email
        for n in notifications:
            print(f"NUDGE -> To: {n.get('who') or 'team'} | Msg: {n.get('message')}")

# -----------------------------
# Final application glue: FastAPI endpoints to run pipeline
# -----------------------------
app = FastAPI(title="AI PMO Pipeline Demo")

@app.get("/run_pipeline")
def run_pipeline(grain: str = "mobile-v3.2"):
    # 1. Collect
    collector = DataCollectorAgent()
    collected = collector.fetch_all()

    # 2. Classify by grain
    classifier = GrainClassifierAgent(grains=[grain])
    grain_map = classifier.assign(collected)

    events = grain_map.get(grain, {})

    # 3. Summarize
    summarizer = SummarizerAgent()
    summary = summarizer.summarize(grain, events)

    # 4. Extract actions
    extractor = ActionExtractorAgent()
    actions = extractor.extract(grain, events)

    # 5. Orchestrate
    orchestrator = OrchestratorAgent(meeting_threshold=2)
    decision = orchestrator.decide(grain, summary, actions)

    # 6. Nudges (push reminders for actions with who but overdue/by soon)
    nudger = NudgerAgent()
    notifications = []
    today = datetime.utcnow().date()
    for a in actions:
        if a.get('who') and a.get('when'):
            try:
                due = datetime.strptime(a['when'], '%Y-%m-%d').date()
                if due < today:
                    notifications.append({'who': a['who'], 'message': f"Overdue: {a['text']}", 'action': a})
                elif due <= today + timedelta(days=2):
                    notifications.append({'who': a['who'], 'message': f"Upcoming: {a['text']} (due {a['when']})", 'action': a})
            except:
                pass
    if notifications:
        nudger.push(notifications)

    result = {
        'grain': grain,
        'summary': summary,
        'actions': actions,
        'decision': decision,
        'notifications_pushed': len(notifications)
    }
    return JSONResponse(content=result)

@app.get("/sources")
def list_sources_proxy():
    return requests.get(f"{MOCK_API_BASE}/sources").json()

@app.get("/source/{source_name}")
def source_proxy(source_name: str):
    return requests.get(f"{MOCK_API_BASE}/sources/{source_name}").json()

# -----------------------------
# Main runner
# -----------------------------
if __name__ == '__main__':
    print("Starting AI PMO demo app on http://127.0.0.1:8000 — mock API on 8001")
    uvicorn.run(app, host='127.0.0.1', port=8000)
