import streamlit as st
import json

from parsers.resume_parser import run_pipeline
from core.scorer import score_all_candidates

st.title("AI Recruitment Agent")

if st.button("Run Pipeline"):

    passed, failed, rejected = run_pipeline()

    sample_jd = {...}

    scored, errored = score_all_candidates(
        passed,
        sample_jd
    )

    final_output = {
        "scored_candidates": [s.to_dict() for s in scored],
        "rejected_candidates": rejected,
        "failed_candidates": failed
    }

    st.success("Pipeline completed")

    st.json(final_output)