# streamlit_app/app.py
#
# HR Shortlisting Agent — Recruiter Dashboard
# Four tabs: Upload & Run | Rankings | Override Scores | Audit Log

import streamlit as st
import pandas as pd
import json
import os
import sys
import tempfile
from pathlib import Path

# Path fix — works from any directory
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))


from parsers.resume_parser import run_pipeline
from parsers.linkedin_parser import parse_linkedin_profile
from core.scorer import score_all_candidates, score_candidate, calculate_weighted_total
from core.override_logger import (
    log_override, get_all_overrides,
    get_overrides_for_candidate, get_recommendation, WEIGHTS
)

#Page config
st.set_page_config(
    page_title="HR Shortlisting Agent",
    layout="wide"
)

# Session state
for key, default in {
    "jd_requirements"  : None,
    "passed_profiles"  : [],
    "scored_candidates": [],
    "pipeline_ran"     : False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

TEMP_DIR = ROOT_DIR / "streamlit_app" / "temp_uploads"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("HR Agent")
    st.caption("Powered by Llama 3.3 70B · Groq")
    st.divider()
    tab = st.radio(
        "Navigation",
        ["Upload & Run", "Rankings", "Override Scores", "Audit Log"],
    )
    st.divider()
    if st.session_state.pipeline_ran:
        st.success(f"{len(st.session_state.scored_candidates)} candidates scored")
        if st.session_state.jd_requirements:
            st.caption(f"Role: {st.session_state.jd_requirements.role_title}")


# TAB 1 — UPLOAD & RUN

if tab == "Upload & Run":

    st.title("HR Resume Shortlisting Agent")
    st.write("Upload resumes and/or LinkedIn profiles to screen and rank candidates.")

    # JD input
    st.header("1. Job Description")
    jd_text = st.text_area(
        "Paste the full Job Description here",
        height=180,
        placeholder="Paste complete JD text..."
    )

    st.divider()

    # Resume upload
    st.header("2. Candidate Input")

    input_tabs = st.tabs(["PDF Resumes", "LinkedIn URL (RapidAPI)", "LinkedIn JSON Export", "LinkedIn Text Paste"])

    with input_tabs[0]:
        uploaded_resumes = st.file_uploader(
            "Upload PDF Resumes",
            type=["pdf"],
            accept_multiple_files=True,
            key="pdf_upload"
        )

    with input_tabs[1]:

        linkedin_urls_input = st.text_area(
            "LinkedIn Profile URLs (one per line)",
            placeholder="https://linkedin.com/in/rahulsharma99\nhttps://linkedin.com/in/sneha-chauhan",
            height=120
        )
        linkedin_urls = [u.strip() for u in linkedin_urls_input.splitlines() if u.strip()]
        if linkedin_urls:
            st.caption(f"{len(linkedin_urls)} URL(s) entered")

    with input_tabs[2]:
        st.info("Candidate exports their LinkedIn profile from Settings → Data Privacy → Get a copy of your data. Upload the Profile.json file here.")
        linkedin_json_files = st.file_uploader(
            "Upload LinkedIn JSON Export files",
            type=["json"],
            accept_multiple_files=True,
            key="linkedin_json"
        )

    # with input_tabs[3]:
    #     st.info("Copy all text from a candidate's LinkedIn page and paste below.")
    #     li_paste_name = st.text_input("Candidate name (optional)", key="li_paste_name")
    #     li_paste_url  = st.text_input("LinkedIn URL (for reference)", key="li_paste_url")
    #     li_paste_text = st.text_area("Paste LinkedIn profile text", height=200, key="li_paste_text")

    st.divider()

    # ── Run button ────────────────────────────────────────────────────────────
    if st.button("Run Screening Pipeline", type="primary", use_container_width=True):

        if not jd_text.strip():
            st.error("Please paste a Job Description.")
            st.stop()

        has_input = (
                uploaded_resumes or
                linkedin_urls    or
                linkedin_json_files
        )
        if not has_input:
            st.error("Please provide at least one candidate input.")
            st.stop()

        all_scored    = []
        all_passed    = []
        all_failed    = []
        all_rejected  = []
        jd_req        = None

        # ── Process PDFs ──────────────────────────────────────────────────────
        if uploaded_resumes:
            resume_paths = []
            for file in uploaded_resumes:
                save_path = str(TEMP_DIR / file.name)
                with open(save_path, "wb") as f:
                    f.write(file.read())
                resume_paths.append(save_path)

            with st.spinner(f"Processing {len(resume_paths)} PDF resume(s)..."):
                passed, failed, rejected = run_pipeline(
                resume_paths=resume_paths,
                jd_text=jd_text
            )
            all_passed.extend(passed)
            all_failed.extend(failed)
            all_rejected.extend(rejected)

        from parsers.jd_parser import parse_jd
        with st.spinner("Parsing Job Description..."):
            try:
                jd_req = parse_jd(jd_text)
            except Exception as e:
                st.error(f"JD parsing failed: {e}")
                st.stop()

        # ── Process LinkedIn URLs (RapidAPI) ──────────────────────────────────
        if linkedin_urls:
            st.write(f"Processing {len(linkedin_urls)} LinkedIn URL(s) via RapidAPI...")
            progress = st.progress(0)
            for i, url in enumerate(linkedin_urls):
                with st.spinner(f"Fetching {url}..."):
                    result = parse_linkedin_profile(
                        method="rapidapi",
                        linkedin_url=url
                    )
                if result.status == "passed":
                    profile = result.to_dict()
                    profile["source"] = "LinkedIn (RapidAPI)"
                    all_passed.append(profile)
                    st.success(f"{profile.get('name', url)}")
                else:
                    all_failed.append({"file": url, "stage": "linkedin_api", "reason": result.error_detail})
                    st.warning(f"{url} — {result.error_detail}")
                progress.progress((i + 1) / len(linkedin_urls))

        # ── Process LinkedIn JSON exports ─────────────────────────────────────
        if linkedin_json_files:
            for json_file in linkedin_json_files:
                save_path = str(TEMP_DIR / json_file.name)
                with open(save_path, "wb") as f:
                    f.write(json_file.read())
                with st.spinner(f"Parsing {json_file.name}..."):
                    result = parse_linkedin_profile(
                        method="json_export",
                        json_path=save_path
                    )
                if result.status == "passed":
                    profile = result.to_dict()
                    profile["source"] = "LinkedIn (JSON Export)"
                    all_passed.append(profile)
                    st.success(f"{profile.get('name', json_file.name)}")
                else:
                    all_failed.append({"file": json_file.name, "stage": "linkedin_json", "reason": result.error_detail})
                    st.warning(f"{json_file.name} — {result.error_detail}")

        # ── Process LinkedIn text paste ───────────────────────────────────────
        # if li_paste_text.strip():
        #     with st.spinner("Extracting LinkedIn profile from pasted text..."):
        #         result = parse_linkedin_profile(
        #             method="text_paste",
        #             linkedin_url=li_paste_url,
        #             raw_text=li_paste_text
        #         )
        #     if result.status == "passed":
        #         profile = result.to_dict()
        #         if li_paste_name and not profile.get("name"):
        #             profile["name"] = li_paste_name
        #         profile["source"] = "LinkedIn (Text Paste)"
        #         all_passed.append(profile)
        #         st.success(f"✓ {profile.get('name', 'LinkedIn Candidate')}")
        #     else:
        #         all_failed.append({"file": "linkedin_paste", "stage": "linkedin_text", "reason": result.error_detail})
        #         st.error(f"LinkedIn text extraction failed: {result.error_detail}")

        # ── Score all passed candidates ───────────────────────────────────────
        if all_passed:
            with st.spinner(f"Scoring {len(all_passed)} candidate(s)..."):
                scored, errored = score_all_candidates(
                    all_passed,
                    jd_req.model_dump()
                )
                all_failed.extend(errored)
        else:
            scored = []

        # ── Save to session state
        st.session_state.jd_requirements   = jd_req
        st.session_state.passed_profiles   = all_passed
        st.session_state.scored_candidates = [
            {"score": s, "profile": p, "source": p.get("source", "PDF Resume")}
            for s, p in zip(scored, all_passed[:len(scored)])
        ]
        st.session_state.pipeline_ran = True

        # Summary
        st.divider()
        st.subheader("Pipeline Summary")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Input",    len(all_passed) + len(all_failed) + len(all_rejected))
        c2.metric("Passed",         len(all_passed))
        c3.metric("Scored",         len(scored))
        c4.metric("Failed/Rejected",len(all_failed) + len(all_rejected))

        st.success(f"Done! {len(scored)} candidates scored. Go to Rankings to see results.")

        if all_rejected:
            with st.expander(f"Rejected ({len(all_rejected)})"):
                st.dataframe(pd.DataFrame(all_rejected), use_container_width=True)
        if all_failed:
            with st.expander(f"Failed ({len(all_failed)})"):
                st.dataframe(pd.DataFrame(all_failed), use_container_width=True)


# TAB 2 — RANKINGS

elif tab == "Rankings":

    st.title("Candidate Rankings")

    if not st.session_state.scored_candidates:
        st.info("No candidates scored yet. Go to Upload & Run first.")
        st.stop()

    ranked = sorted(
        st.session_state.scored_candidates,
        key=lambda x: x["score"].weighted_total,
        reverse=True
    )

    # ── Rankings table ────────────────────────────────────────────────────────
    table_rows = []
    for i, c in enumerate(ranked, 1):
        s = c["score"]
        table_rows.append({
            "Rank"              : i,
            "Candidate"         : s.candidate_name,
            "Source"            : c.get("source", "PDF"),
            "Total"             : s.weighted_total,
            "Verdict"           : s.recommendation.upper().replace("_", " "),

            "Skills (30%)"      : s.skills_match.score,
            "Skills Reason"     : s.skills_match.justification,

            "Exp (25%)"         : s.experience_relevance.score,
            "Exp Reason"        : s.experience_relevance.justification,

            "Edu (15%)"         : s.education_certs.score,
            "Edu Reason"        : s.education_certs.justification,

            "Projects (20%)"    : s.project_portfolio.score,
            "Projects Reason"   : s.project_portfolio.justification,

            "Comm (10%)"        : s.communication_quality.score,
            "Comm Reason"       : s.communication_quality.justification,
        })

    df = pd.DataFrame(table_rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Download
    st.download_button(
        "⬇Download Shortlist JSON",
        data=json.dumps([
            {**row, "summary": ranked[i-1]["score"].summary}
            for i, row in enumerate(table_rows, 1)
        ], indent=2),
        file_name="shortlist_report.json",
        mime="application/json"
    )

    st.divider()

    # ── Candidate detail
    st.subheader("Candidate Detail")
    names = [c["score"].candidate_name for c in ranked]
    selected_name = st.selectbox("Select candidate", names)
    selected = next((c for c in ranked if c["score"].candidate_name == selected_name), None)

    if selected:
        s = selected["score"]
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Dimension Scores")
            dims = [
                ("Skills Match (30%)",         s.skills_match),
                ("Experience Relevance (25%)",  s.experience_relevance),
                ("Education & Certs (15%)",     s.education_certs),
                ("Project Portfolio (20%)",     s.project_portfolio),
                ("Communication Quality (10%)", s.communication_quality),
            ]
            for label, dim in dims:
                st.write(f"**{label}:** {dim.score}/10")
                st.caption(f"_{dim.justification}_")
                st.progress(dim.score / 10)

            st.divider()
            colour = {"strong_hire":"green","hire":"blue","maybe":"orange","no_hire":"red"}
            st.metric("Weighted Total", f"{s.weighted_total}/10")
            st.markdown(f"**Verdict:** :{colour.get(s.recommendation,'gray')}[**{s.recommendation.upper().replace('_',' ')}**]")

        with col2:
            st.subheader("AI Summary")
            st.write(s.summary)

            profile = selected.get("profile", {})
            if profile.get("skills"):
                st.subheader("Skills")
                st.write(", ".join(profile["skills"]))
            if profile.get("experience"):
                st.subheader("Experience")
                for exp in profile["experience"]:
                    st.write(f"• {exp.get('role')} at {exp.get('company')} — {exp.get('duration_months','?')} months")

            overrides = get_overrides_for_candidate(selected_name)
            if overrides:
                st.subheader("Override History")
                for o in overrides:
                    st.caption(f"{o['timestamp'][:19]} | {o['dimension'].replace('_',' ')} | {o['original_score']} → {o['new_score']} | {o['reason']}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — OVERRIDE SCORES
# ══════════════════════════════════════════════════════════════════════════════
elif tab == "Override Scores":

    st.title("HR Score Override")
    st.info("Override any dimension score. A documented reason is mandatory. All changes are permanently logged.")

    if not st.session_state.scored_candidates:
        st.warning("No candidates scored yet. Run the pipeline first.")
        st.stop()

    names = [c["score"].candidate_name for c in st.session_state.scored_candidates]
    selected_name = st.selectbox("Select candidate", names)

    selected_idx = next(
        (i for i, c in enumerate(st.session_state.scored_candidates)
         if c["score"].candidate_name == selected_name), None
    )

    if selected_idx is not None:
        candidate = st.session_state.scored_candidates[selected_idx]
        score     = candidate["score"]

        # ── Current scores
        st.subheader(f"Current Scores — {selected_name}")

        dim_map = {
            "Skills Match"          : "skills_match",
            "Experience Relevance"  : "experience_relevance",
            "Education & Certs"     : "education_certs",
            "Project Portfolio"     : "project_portfolio",
            "Communication Quality" : "communication_quality",
        }

        current_scores = {
            "skills_match"         : score.skills_match.score,
            "experience_relevance" : score.experience_relevance.score,
            "education_certs"      : score.education_certs.score,
            "project_portfolio"    : score.project_portfolio.score,
            "communication_quality": score.communication_quality.score,
        }

        for label, key in dim_map.items():
            c1, c2, c3 = st.columns([2, 1, 3])
            c1.write(f"**{label}**")
            c2.write(f"{current_scores[key]}/10")
            c3.progress(current_scores[key] / 10)

        st.metric("Current Weighted Total", f"{score.weighted_total}/10",
                  delta=None, help="Recalculates automatically after override")
        st.divider()

        # ── Override form
        st.subheader("Apply Override")

        dim_label   = st.selectbox("Dimension to override", list(dim_map.keys()))
        dim_key     = dim_map[dim_label]
        orig_score  = current_scores[dim_key]

        new_score = st.slider(
            f"New score for {dim_label}",
            min_value=0.0, max_value=10.0,
            value=float(orig_score), step=0.5
        )

        # show live preview of what new total would be
        preview_scores = dict(current_scores)
        preview_scores[dim_key] = new_score
        preview_total = round(sum(preview_scores[d] * w for d, w in WEIGHTS.items()), 2)
        preview_rec   = get_recommendation(preview_total)

        if new_score != orig_score:
            delta = round(new_score - orig_score, 1)
            st.info(f"Preview: Weighted Total {score.weighted_total} → **{preview_total}** | Verdict → **{preview_rec.upper().replace('_',' ')}** | Delta on this dimension: {delta:+.1f}")

        reason = st.text_area(
            "Reason for override (required)",
            placeholder="e.g. Reviewed GitHub repository directly — project has 300+ stars and is actively maintained. LLM underscored based on resume description alone."
        )

        if st.button("Submit Override", type="primary"):
            if not reason.strip():
                st.error("A reason is required. Describe why you are overriding this score.")
            elif new_score == orig_score:
                st.warning("Score is unchanged. Move the slider to set a different score.")
            else:
                updated_scores = dict(current_scores)
                updated_scores[dim_key] = new_score

                result = log_override(
                    candidate_name=selected_name,
                    dimension=dim_key,
                    original_score=orig_score,
                    new_score=new_score,
                    reason=reason.strip(),
                    all_current_scores=updated_scores,
                    logged_by="HR"
                )

                # update session state live
                getattr(score, dim_key).score = new_score
                score.weighted_total  = result["weighted_total"]
                score.recommendation  = result["recommendation"]

                st.success(
                    f"Override logged. "
                    f"New total: {result['weighted_total']}/10 | "
                    f"Verdict: {result['recommendation'].upper().replace('_',' ')}"
                )
                st.rerun()

        # ── Override history for this candidate ───────────────────────────────
        overrides = get_overrides_for_candidate(selected_name)
        if overrides:
            st.divider()
            st.subheader("Override History for this Candidate")
            for o in reversed(overrides):
                with st.expander(f"{o['timestamp'][:19]} | {o['dimension'].replace('_',' ').title()} | {o['original_score']} → {o['new_score']}"):
                    st.write(f"Reason: {o['reason']}")
                    st.write(f"By: {o['logged_by']}")
                    st.write(f"New total after: {o['new_weighted_total']}/10")
                    st.write(f"New verdict: {o['new_recommendation'].upper().replace('_',' ')}")


# TAB 4 — AUDIT LOG

elif tab == "Audit Log":

    st.title("Override Audit Log")
    st.caption("Every HR score override is permanently logged here with reason, timestamp, and delta.")

    overrides = get_all_overrides()

    if not overrides:
        st.info("No overrides logged yet.")
        st.stop()

    st.write(f"**Total overrides:** {len(overrides)}")
    st.divider()

    log_rows = [{
        "Timestamp"  : o["timestamp"][:19].replace("T", " "),
        "Candidate"  : o["candidate_name"],
        "Dimension"  : o["dimension"].replace("_", " ").title(),
        "Before"     : o["original_score"],
        "After"      : o["new_score"],
        "Delta"      : f"{o['score_delta']:+.1f}",
        "New Total"  : o["new_weighted_total"],
        "New Verdict": o["new_recommendation"].upper().replace("_", " "),
        "Reason"     : o["reason"],
        "By"         : o["logged_by"],
    } for o in reversed(overrides)]

    st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)

    st.download_button(
        "⬇Download Audit Log",
        data=json.dumps(overrides, indent=2),
        file_name="override_audit_log.json",
        mime="application/json"
    )