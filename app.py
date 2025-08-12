import streamlit as st
import pandas as pd
from rapidfuzz import fuzz
from datetime import datetime

APP_TITLE = "NYCPS DOE Script Builder — Pro (No dropdowns)"
MIN_SCORE = 70    # adjust if matching feels too strict
ALT_COUNT = 5

SCRIPT_TEMPLATE = """
[GREETING]
Thank you for calling NYCPS Service Desk. My name is {agent_name}. Are you calling for a new issue or an existing ticket?

[VERIFICATION — DOE 5‑Point]
1) Full Name  2) DOE Email  3) Title  4) School DBN / Central Location  5) Callback #

[CLASSIFICATION — 4 Levels]
Catalog: {catalog}
Service Group: {service_group}
Category: {category}
Action: {action}

[TECHNOLOGY]
Technology/Application: {tech_app}
OS: {os}

[WHAT TO ASK (Probing)]
{probing_block}

[WHAT TO SAY / DO (Resolution Steps)]
{steps_block}

[URLS / FORMS]
{urls_block}

[ESCALATION / ROUTING]
- Route to: {routing_group}
- Routing Notes: {routing_notes}

[REQUIRED DATA TO COLLECT]
{required_fields_block}

[CAUSE / RESOLUTION CODES]
- Cause Code: {cause_code}
- Resolution Code: {resolution_code}

[HOURS / SCHEDULE]
{hours}

[CONTACTS]
{contacts}

[SOURCES]
{kb_sources}

[CLOSING]
For your reference, the ticket number is {ticket_number}. Thank you for calling and have a great day.
""".strip()

@st.cache_data
def load_kb(csv_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(csv_bytes)
    return df.fillna("")

def read_csv_file(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    return df.fillna("")

def weight_score(query: str, row: pd.Series) -> int:
    """Weighted fuzzy score across multiple fields to avoid simplistic 'RACF/email/etc' buckets."""
    fields = {
        "title": 3,
        "keywords": 3,
        "kb_id": 2,
        "tech_app": 2,
        "category": 2,
        "action": 2,
        "catalog": 1,
        "service_group": 1,
        "probing": 1,
        "steps": 1
    }
    total = 0
    max_total = 0
    for f, w in fields.items():
        text = row.get(f, "")
        if isinstance(text, str) and text:
            s = fuzz.token_set_ratio(query, text)
            total += s * w
            max_total += 100 * w
        else:
            max_total += 100 * w
    # normalize to 0..100
    return int((total / max_total) * 100) if max_total else 0

def match_issue(query: str, kb_df: pd.DataFrame):
    scored = []
    for idx, row in kb_df.iterrows():
        score = weight_score(query, row)
        if score >= MIN_SCORE:
            scored.append((idx, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:ALT_COUNT] if scored else []

def render_script(row: pd.Series, agent_name: str, ticket_number: str) -> str:
    # Blocks
    probing = row.get("probing", "").strip()
    probing_block = "- " + probing.replace(";", "\n- ") if probing else "-"
    steps = row.get("steps", "").strip()
    steps_block = "1) " + steps.replace(";", "\n2) ", 1).replace("\n2) ", "\n2) ").replace(";", "\n• ") if steps else "-"
    urls = row.get("urls", "").strip()
    urls_block = "- " + urls.replace(";", "\n- ") if urls else "-"
    required_fields = row.get("required_fields", "").strip()
    required_fields_block = "- " + required_fields.replace(";", "\n- ") if required_fields else "-"

    return SCRIPT_TEMPLATE.format(
        agent_name=agent_name or "[Your Name]",
        catalog=row.get("catalog","-") or "-",
        service_group=row.get("service_group","-") or "-",
        category=row.get("category","-") or "-",
        action=row.get("action","-") or "-",
        tech_app=row.get("tech_app","-") or "-",
        os=row.get("os","Any") or "Any",
        probing_block=probing_block,
        steps_block=steps_block,
        urls_block=urls_block,
        routing_group=row.get("routing_group","-") or "-",
        routing_notes=row.get("routing_notes","-") or "-",
        required_fields_block=required_fields_block,
        cause_code=row.get("cause_code","-") or "-",
        resolution_code=row.get("resolution_code","-") or "-",
        hours=row.get("hours","-") or "-",
        contacts=row.get("contacts","-") or "-",
        kb_sources=row.get("kb_sources","-") or "-",
        ticket_number=ticket_number or "[Ticket #]",
    )

def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption("Paste caller's words. The app finds the closest DOE KB and generates a full call script. No dropdowns, just precise matching.")

    # Sidebar: agent/ticket only (no category selectors)
    with st.sidebar:
        agent_name = st.text_input("Agent name", value="")
        ticket_number = st.text_input("Ticket # (optional)", value="")
        st.markdown("---")
        st.write("Upload your **kb.csv** below. Use the provided v3 schema.")

    kb_file = st.file_uploader("Upload kb.csv (v3 schema)", type=["csv"])
    query = st.text_area("Caller’s words / issue description:", height=160,
                         placeholder="Example: Teacher moved offices; lost access to RTE/CICS; can reach purple.com but not ATS Print; needs VLAN2...")

    if st.button("Build Script", type="primary"):
        if kb_file is None:
            st.error("Upload kb.csv first (v3 schema).")
            st.stop()
        if not query.strip():
            st.warning("Type a short description of the issue from the caller.")
            st.stop()

        kb_df = read_csv_file(kb_file)
        matches = match_issue(query, kb_df)

        if not matches:
            st.error("No strong match found. Try more specifics (app name, error text, route, KB ID).")
            st.stop()

        # Best match
        best_idx, best_score = matches[0]
        best_row = kb_df.iloc[best_idx]
        st.success(f"Matched: {best_row.get('kb_id','?')} — {best_row.get('title','?')} (score {best_score})")

        script = render_script(best_row, agent_name, ticket_number)
        st.code(script)

        # Alternatives (click-to-preview, not dropdowns)
        if len(matches) > 1:
            st.subheader("Alternative matches")
            for i, (idx, score) in enumerate(matches[1:], start=1):
                alt = kb_df.iloc[idx]
                with st.expander(f"{i}. {alt.get('kb_id','?')} — {alt.get('title','?')} (score {score})"):
                    st.caption(alt.get("keywords",""))
                    st.text(render_script(alt, agent_name, ticket_number))

        # Metadata
        with st.expander("Article metadata (best match)"):
            meta = best_row.to_dict()
            meta["matched_at"] = datetime.now().isoformat(timespec="seconds")
            st.json(meta)

    st.caption("v3 • Weighted matching across title/keywords/KB/tech/category/action • No dropdowns • DOE 4‑level classification")

if __name__ == "__main__":
    main()
