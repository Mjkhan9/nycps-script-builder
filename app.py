import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
from datetime import datetime

# -------- Settings you can tweak ----------
SCRIPT_TEMPLATE = """
[GREETING]
Thank you for calling NYCPS Service Desk. My name is {agent_name}. Are you calling for a new issue or an existing ticket?

[CLASSIFICATION]
Catalog: {catalog}
Area: {area}
Technology/Application: {tech_app}
OS: {os}

[WHAT TO SAY / DO]
1) {step_1}
2) {step_2}
3) {step_3}

[URLS / FORMS]
{urls_block}

[ESCALATION / ROUTING]
- Route to: {routing_group}
- Notes: {routing_notes}

[REQUIRED DATA TO COLLECT]
{required_fields}

[HOURS / SCHEDULE]
{hours}

[CONTACTS]
{contacts}

[CLOSING]
For your reference, the ticket number is {ticket_number}. Thank you for calling and have a great day.
""".strip()

MIN_SCORE = 65         # Lower if you want fuzzier matches
ALTERNATIVES = 4       # How many backup matches to show
# ------------------------------------------

@st.cache_data
def load_kb():
    df = pd.read_csv("kb.csv")
    df = df.fillna("")  # avoid NaNs
    return df

def build_match_corpus(row):
    parts = [
        row.get("kb_id",""), row.get("title",""), row.get("keywords",""),
        row.get("catalog",""), row.get("area",""), row.get("tech_app","")
    ]
    return " | ".join(str(p) for p in parts if p)

def match_issue(query, kb_df):
    choices = [(idx, build_match_corpus(row)) for idx, row in kb_df.iterrows()]
    scored = [(idx, fuzz.token_set_ratio(query, text)) for idx, text in choices]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = [s for s in scored if s[1] >= MIN_SCORE][:ALTERNATIVES]
    return top

def render_script(row, agent_name, ticket_number):
    urls = row["urls"].strip()
    urls_block = "- " + urls.replace(";", "\n- ") if urls else "-"
    return SCRIPT_TEMPLATE.format(
        agent_name=agent_name or "[Your Name]",
        catalog=row["catalog"] or "-",
        area=row["area"] or "-",
        tech_app=row["tech_app"] or "-",
        os=row["os"] or "Any",
        step_1=row["step_1"] or "-",
        step_2=row["step_2"] or "-",
        step_3=row["step_3"] or "-",
        urls_block=urls_block,
        routing_group=row["routing_group"] or "-",
        routing_notes=row["routing_notes"] or "-",
        required_fields=(row["required_fields"] or "-").replace(";", "\n- "),
        hours=row["hours"] or "-",
        contacts=row["contacts"] or "-",
        ticket_number=ticket_number or "[Ticket #]"
    )

def main():
    st.set_page_config(page_title="NYCPS Script Builder", layout="wide")
    st.title("NYCPS Call Script Builder")

    kb_df = load_kb()
    with st.sidebar:
        st.subheader("Agent Options")
        agent_name = st.text_input("Agent name", value="")
        ticket_number = st.text_input("Ticket # (optional)", value="")
        st.markdown("---")
        st.caption("Tip: keep your kb.csv current. Add keywords for better matches.")

    query = st.text_area("Describe the issue (paste caller’s words):", height=120,
                         placeholder="e.g., Teacher needs RACF password reset; can’t log in; PIN known...")
    if st.button("Build Script", type="primary"):
        if not query.strip():
            st.warning("Type an issue description first.")
            st.stop()

        matches = match_issue(query, kb_df)
        if not matches:
            st.error("No strong match found. Try adding more detail or synonyms.")
            st.stop()

        best_idx, best_score = matches[0]
        best_row = kb_df.iloc[best_idx]

        st.success(f"Matched: {best_row['kb_id']} — {best_row['title']} (score {best_score})")
        script = render_script(best_row, agent_name, ticket_number)
        st.code(script)

        if len(matches) > 1:
            with st.expander("See alternative matches"):
                for alt_idx, score in matches[1:]:
                    row = kb_df.iloc[alt_idx]
                    st.write(f"**{row['kb_id']} — {row['title']}** (score {score})")
                    st.caption(row["keywords"])

        with st.expander("Article metadata"):
            meta = best_row.to_dict()
            meta["matched_at"] = datetime.now().isoformat(timespec="seconds")
            st.json(meta)

    st.markdown("—")
    st.caption("v1 • Streamlit • rapidfuzz • pandas")

if __name__ == "__main__":
    main()
