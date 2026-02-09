import requests
import streamlit as st

st.set_page_config(page_title="Resume ↔ JD Matcher", layout="wide")

API_BASE = st.sidebar.text_input("API Base URL", value="http://api:8000").strip()

st.title("Resume ↔ Job Description Matching (Demo UI)")
st.caption("Upload a resume → create a JD → match → view ranked results + explanations.")

col1, col2 = st.columns(2)

with col1:
    st.subheader("1) Upload Resume")
    resume_file = st.file_uploader("Choose a PDF/DOCX resume", type=["pdf", "docx"])
    if st.button("Upload Resume"):
        if not resume_file:
            st.error("Please select a resume file first.")
        else:
            files = {"file": (resume_file.name, resume_file.getvalue(), resume_file.type)}
            r = requests.post(f"{API_BASE}/resumes", files=files, timeout=60)
            if r.status_code != 200:
                st.error(f"Upload failed: {r.status_code} {r.text}")
            else:
                data = r.json()
                st.session_state["resume_id"] = data["resume_id"]
                st.success(f"Uploaded. resume_id = {data['resume_id']}")

    resume_id = st.text_input("Resume ID", value=st.session_state.get("resume_id", "")).strip()

    if st.button("Check Resume Status"):
        if not resume_id:
            st.error("Enter a resume_id first.")
        else:
            r = requests.get(f"{API_BASE}/resumes/{resume_id}", timeout=30)
            if r.status_code != 200:
                st.error(f"Error: {r.status_code} {r.text}")
            else:
                st.json(r.json())

with col2:
    st.subheader("2) Create Job Description")
    jd_title = st.text_input("JD Title", value="Machine Learning Engineer")
    jd_content = st.text_area(
        "JD Content",
        value="Need a Data science intern who knows pandas, numpy, tensor flow, deep learning.",
        height=160,
    )
    if st.button("Create JD"):
        payload = {"title": jd_title, "content": jd_content}
        r = requests.post(f"{API_BASE}/job-descriptions", json=payload, timeout=60)
        if r.status_code != 200:
            st.error(f"Create JD failed: {r.status_code} {r.text}")
        else:
            data = r.json()
            st.session_state["jd_id"] = data["jd_id"]
            st.success(f"Created. jd_id = {data['jd_id']}")

    jd_id = st.text_input("JD ID", value=st.session_state.get("jd_id", "")).strip()

st.divider()

st.subheader("3) Match")
top_k = st.slider("Top K results", 1, 25, 10)

if st.button("Run Match"):
    if not jd_id:
        st.error("Enter a jd_id first.")
    else:
        payload = {"jd_id": jd_id, "top_k": int(top_k)}
        r = requests.post(f"{API_BASE}/match", json=payload, timeout=60)
        if r.status_code != 200:
            st.error(f"Match failed: {r.status_code} {r.text}")
        else:
            data = r.json()
            st.success("Match completed.")
            st.write("**JD skills detected:**", data.get("jd_skills_detected", []))

            results = data.get("results", [])
            if not results:
                st.warning("No results returned. Make sure you have PROCESSED resumes.")
            else:
                rows = []
                for item in results:
                    rows.append({
                        "resume_id": item["resume_id"],
                        "final_score": item["final_score"],
                        "semantic_similarity": item["semantic_similarity"],
                        "skills_overlap": item["skills_overlap"],
                        "experience_alignment": item["experience_alignment"],
                        "skills_matched": ", ".join(item.get("skills_matched", [])),
                        "skills_missing": ", ".join(item.get("skills_missing", [])),
                    })
                st.dataframe(rows, use_container_width=True)

                st.markdown("### Explanations (per resume)")
                for item in results:
                    with st.expander(f"Resume {item['resume_id']} — score {item['final_score']}"):
                        st.json(item)
