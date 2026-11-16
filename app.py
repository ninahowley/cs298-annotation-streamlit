import ast
import os
from datetime import datetime
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
CSV_FILE = "typology_dataset.csv"
RESULTS_SNAPSHOT_FILE = "current_annotations.csv"
KEY_FILE = os.path.join("secrets", "app_key.txt")

TYPOLOGY_OPTIONS = [
    "loyal liberal",
    "leftward progressive",
    "no apologies right",
    "pragmatic and polite right",
    "tuned-out middle",
    "left-out left",
    "faith first conservative",
    "unconventional right",
]

TYPOLOGY_DEFINITIONS = {
    "leftward progressive": "Liberal across the board, they are among the strongest critics of the U.S. economic system and the Trump administration. Support expanding the social safety net. Economically populist. Want more political parties in the U.S. Young, very online and largely religiously unaffiliated.",
    "loyal liberal": "Liberal across most issues, they are invested in the Democratic Party and in domestic and international institutions. Feel well-represented by the Democratic Party. Progressive views on many key cultural issues. Highly engaged with politics and news. Less cynical about elected officials than most other groups.",
    "left-out left": "Democratic-leaning, with a mix of liberal and moderate views and limited confidence in the parties and the political system. Support social safety net policies such as government-backed healthcare. Somewhat moderate views on gender, sexuality and immigration. Largely working class. Racially and ethnically diverse and relatively young.",
    "order and opportunity left": "Economically liberal positions with moderate stances on immigration and concerns about safety and crime. Mostly Democratic-leaning in orientation, but 25% associate with the Republican Party. Socially moderate. Economically pinched, but economically optimistic.",
    "tuned-out middle": "Largely disconnected from politics, they tilt liberal on economic concerns but not on social issues. Much less likely than other groups to follow politics. Fewer than half voted in 2024. Very financially strained and relatively young. Equally likely to associate with the two major parties.",
    "pragmatic and polite right": "Moderate in tone and on many issues, with a small-government streak. Center-right on gender and sexuality issues. Moderate to liberal views on race and diversity issues. Want a secure border, but also a path to legal status for those in the U.S. illegally. Support close ties with traditional U.S. allies.",
    "unconventional right": "Conservative on immigration and culture, but they break from those to their right on some other key issues. Support strict immigration enforcement. More open than groups to their right to working with allies. Younger and less religious than other Republican-oriented groups. Moderately politically engaged.",
    "faith first conservative": "Staunch conservatives and strong Trump supporters who stand out for their faith-oriented politics. Devout and overwhelmingly Christian. Oppose abortion and see same-sex marriage as bad for society. Prefer a smaller government and limited social safety net.",
    "no apologies right": "Unwavering Trump supporters with a pugilistic political style and an ‘America first’ outlook. Strong backers of the administration’s efforts to deport immigrants in the U.S. illegally. See traditional U.S. allies as burdensome. Strongly oppose diversity, equity and inclusion (DEI) programs. Distrustful of experts and many traditional media organizations.",
}

SHEET_COLUMNS = [
    "id",
    "account",
    "user",
    "user_label",
    "qwen_label",
    "qwen_certainty",
    "timestamp",
]


# --- PASSPHRASE AUTHENTICATION ---
def get_stored_app_key():
    if "APP_KEY" in st.secrets:
        return st.secrets["APP_KEY"]

    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()

    return ""


# --- GOOGLE SHEETS DATABASE OPERATIONS ---
def get_gsheets_connection():
    return st.connection("gsheets", type=GSheetsConnection)


def fetch_all_annotations():
    """Reads live annotations from Google Sheets with 60s cache."""
    conn = get_gsheets_connection()
    try:
        df_sheet = conn.read(ttl=60)
        if df_sheet is None or df_sheet.empty:
            return pd.DataFrame(columns=SHEET_COLUMNS)
        df_sheet["id"] = df_sheet["id"].astype(str)
        df_sheet["user"] = df_sheet["user"].astype(str)
        return df_sheet
    except Exception:
        return pd.DataFrame(columns=SHEET_COLUMNS)


def load_existing_user_annotations(user_id):
    """Loads a specific user's saved annotations from Google Sheets."""
    df_sheet = fetch_all_annotations()
    if df_sheet.empty or "user_label" not in df_sheet.columns:
        return {}
    user_rows = df_sheet[df_sheet["user"] == str(user_id)]
    return dict(zip(user_rows["id"], user_rows["user_label"]))


def save_user_annotations(user_id, annotations_dict, user_df):
    """Upserts user typology annotations along with Qwen model baseline data to Google Sheets."""
    conn = get_gsheets_connection()
    df_sheet = fetch_all_annotations()

    if not df_sheet.empty:
        df_sheet = df_sheet[df_sheet["user"] != str(user_id)]

    new_rows = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    typ_col = (
        "qwen_typology"
        if "qwen_typology" in user_df.columns
        else ("qwen_label" if "qwen_label" in user_df.columns else ("typology" if "typology" in user_df.columns else None))
    )
    cert_col = (
        "qwen_certainty"
        if "qwen_certainty" in user_df.columns
        else ("certainty" if "certainty" in user_df.columns else ("typology_certainty" if "typology_certainty" in user_df.columns else None))
    )

    for item_id, typology_val in annotations_dict.items():
        if typology_val:
            sub_df = user_df[user_df["id"].astype(str) == str(item_id)]

            acct_name = sub_df["account"].values[0] if not sub_df.empty and "account" in sub_df.columns else ""
            qwen_typ = sub_df[typ_col].values[0] if not sub_df.empty and typ_col else ""
            qwen_cert = sub_df[cert_col].values[0] if not sub_df.empty and cert_col else ""

            new_rows.append(
                {
                    "id": str(item_id),
                    "account": str(acct_name),
                    "user": str(user_id),
                    "user_label": str(typology_val),
                    "qwen_label": str(qwen_typ),
                    "qwen_certainty": str(qwen_cert),
                    "timestamp": timestamp,
                }
            )

    if new_rows:
        df_new = pd.DataFrame(new_rows)
        df_updated = pd.concat([df_sheet, df_new], ignore_index=True)
    else:
        df_updated = df_sheet

    conn.update(data=df_updated)
    st.cache_data.clear()


def delete_user_annotations(user_id):
    """Deletes all saved annotations for a specific student from Google Sheets."""
    conn = get_gsheets_connection()
    df_sheet = fetch_all_annotations()

    if not df_sheet.empty:
        df_updated = df_sheet[df_sheet["user"] != str(user_id)]
        conn.update(data=df_updated)
        st.cache_data.clear()


# --- DATA LOADING ---
@st.cache_data
def load_data():
    df = pd.read_csv(CSV_FILE, encoding="utf-8")

    df["id"] = df["id"].astype(str)
    df["user"] = df["user"].astype(str).str.strip()

    def parse_posts(val):
        if pd.isna(val) or not val:
            return []
        try:
            return ast.literal_eval(val)
        except Exception:
            return []

    df["parsed_posts"] = df["posts"].apply(parse_posts)
    return df


# --- PAGE 1: LAUNCH / ACCESS GATE ---
def render_launch_page():
    _, center_col, _ = st.columns([1, 1.5, 1])

    with center_col:
        st.title("🔒 Restricted Access")
        st.write("Please enter the passphrase to access the Political Typology Annotator.")

        correct_key = get_stored_app_key()
        user_input = st.text_input("Passphrase:", type="password", key="passphrase_input")

        if st.button("Enter Website", type="primary", use_container_width=True):
            if user_input == correct_key:
                st.session_state.authenticated = True
                st.session_state.page = "annotate"
                st.rerun()
            else:
                st.error("Incorrect passphrase. Please try again.")

        if st.button("Explore Results", use_container_width=True):
            # Clear cached results snapshot so opening Explore Results loads fresh state
            st.session_state.pop("results_df", None)
            st.session_state.page = "explore_results"
            st.rerun()


# --- PAGE 2: EXPLORE RESULTS (ONLY ACCESSIBLE FROM LAUNCH PAGE) ---
def render_explore_results_page():
    top_col1, top_col2, top_col3 = st.columns([5, 1.5, 1.5])
    with top_col1:
        st.title("📊 Annotation Results Explorer")
    with top_col2:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.pop("results_df", None)
            st.rerun()
    with top_col3:
        if st.button("⬅️ Back to Launch Page", use_container_width=True):
            st.session_state.page = "launch"
            st.rerun()

    # Save current state of the results CSV into session_state DataFrame & local CSV snapshot
    if "results_df" not in st.session_state:
        df_live = fetch_all_annotations()
        if not df_live.empty:
            for col in ["id", "account", "user", "user_label", "qwen_label", "qwen_certainty"]:
                if col in df_live.columns:
                    df_live[col] = df_live[col].fillna("").astype(str).str.strip()
        st.session_state.results_df = df_live
        st.session_state.results_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_live.to_csv(RESULTS_SNAPSHOT_FILE, index=False)

    df_results = st.session_state.results_df
    df_assignments = load_data()

    # --- DISPLAY CURRENT CSV STATE DATAFRAME ON SCREEN ---
    st.subheader("Current Annotations Dataset (`df`)")
    st.caption(
        f"Snapshot captured at **{st.session_state.get('results_saved_at', '')}** | "
        f"**{len(df_results)}** rows × **{len(df_results.columns)}** columns"
    )
    st.dataframe(df_results, use_container_width=True, hide_index=True)

    st.download_button(
        label="⬇️ Download Current CSV",
        data=df_results.to_csv(index=False).encode("utf-8"),
        file_name=f"typology_annotations_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    st.divider()

    # --- SUMMARY METRICS ---
    total_expected = len(df_assignments)
    total_submitted = len(df_results)
    unique_profiles_done = df_results["id"].nunique() if not df_results.empty else 0
    total_unique_profiles = df_assignments["id"].nunique()

    if not df_results.empty and {"user_label", "qwen_label"}.issubset(df_results.columns):
        valid_comp = df_results[(df_results["user_label"] != "") & (df_results["qwen_label"] != "")]
        model_agreement = (
            (valid_comp["user_label"].str.lower() == valid_comp["qwen_label"].str.lower()).mean() * 100
            if not valid_comp.empty
            else 0.0
        )
    else:
        model_agreement = 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Annotations Submitted", f"{total_submitted} / {total_expected}")
    m2.metric("Unique Profiles Annotated", f"{unique_profiles_done} / {total_unique_profiles}")
    m3.metric(
        "Active Students",
        f"{df_results['user'].nunique() if not df_results.empty else 0} / {df_assignments['user'].nunique()}",
    )
    m4.metric("Student vs. Qwen Agreement", f"{model_agreement:.1f}%")

    st.divider()

    # --- STUDENT COMPLETION PROGRESS ---
    st.subheader("Student Completion Progress")
    assigned_counts = df_assignments.groupby("user")["id"].count().reset_index(name="Assigned")
    if not df_results.empty:
        submitted_counts = df_results.groupby("user")["id"].nunique().reset_index(name="Submitted")
        progress_df = pd.merge(assigned_counts, submitted_counts, on="user", how="left").fillna(0)
    else:
        progress_df = assigned_counts.copy()
        progress_df["Submitted"] = 0

    progress_df["Submitted"] = progress_df["Submitted"].astype(int)
    progress_df["Completion (%)"] = ((progress_df["Submitted"] / progress_df["Assigned"]) * 100).round(1)
    progress_df = progress_df.sort_values(by=["Submitted", "user"], ascending=[False, True])

    p_col1, p_col2 = st.columns([1.2, 1.8])
    with p_col1:
        st.dataframe(progress_df, use_container_width=True, hide_index=True)
    with p_col2:
        st.bar_chart(progress_df.set_index("user")[["Submitted", "Assigned"]])

    if df_results.empty:
        st.info("No annotations have been submitted to Google Sheets yet.")
        return

    st.divider()

    # --- LABEL DISTRIBUTIONS & MODEL COMPARISON ---
    st.subheader("Label Distribution: Students vs. Qwen")
    d_col1, d_col2 = st.columns(2)

    with d_col1:
        st.markdown("**Student Labels (`user_label`)**")
        user_dist = df_results["user_label"].value_counts().reset_index()
        user_dist.columns = ["Typology", "Count"]
        st.bar_chart(user_dist.set_index("Typology"))

    with d_col2:
        st.markdown("**Qwen Baseline Labels (`qwen_label`)**")
        qwen_dist = df_results["qwen_label"].value_counts().reset_index()
        qwen_dist.columns = ["Typology", "Count"]
        st.bar_chart(qwen_dist.set_index("Typology"))

    st.divider()

    # --- INTER-ANNOTATOR AGREEMENT ---
    st.subheader("Inter-Student Agreement (Multi-Annotated Profiles)")
    grouped_profiles = (
        df_results.groupby(["id", "account", "qwen_label", "qwen_certainty"])
        .agg(
            annotator_count=("user", "count"),
            students=("user", lambda x: ", ".join(x)),
            student_labels=("user_label", lambda x: ", ".join(x)),
            unique_labels=("user_label", lambda x: x.str.lower().nunique()),
        )
        .reset_index()
    )

    multi_annotated = grouped_profiles[grouped_profiles["annotator_count"] >= 2].copy()
    if not multi_annotated.empty:
        multi_annotated["Students Agree?"] = multi_annotated["unique_labels"].apply(
            lambda n: "✅ Exact Match" if n == 1 else "⚠️ Disagreement"
        )
        exact_match_rate = (multi_annotated["unique_labels"] == 1).mean() * 100
        st.caption(
            f"**{len(multi_annotated)}** profiles have 2+ student annotations | "
            f"Exact inter-student agreement: **{exact_match_rate:.1f}%**"
        )
        st.dataframe(
            multi_annotated[
                ["id", "account", "students", "student_labels", "qwen_label", "qwen_certainty", "Students Agree?"]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No profiles have been annotated by 2 or more students yet.")


# --- PAGE 3: STUDENT ANNOTATOR WORKSPACE ---
def render_annotator_page():
    df = load_data()

    # --- SIDEBAR: USER SELECTION & DEFINITIONS ---
    st.sidebar.title("Student Login")
    available_users = sorted(df["user"].dropna().unique().tolist())

    selected_user = st.sidebar.selectbox(
        "Select your User ID:",
        options=["-- Select User --"] + available_users,
    )

    if selected_user == "-- Select User --":
        st.info("Please select your User ID in the sidebar to begin annotating.")
        st.sidebar.divider()
        if st.sidebar.button("🔒 Exit App", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.page = "launch"
            st.rerun()
        return

    user_df = df[df["user"] == selected_user].reset_index(drop=True)

    if user_df.empty:
        st.warning(f"No profiles assigned to user '{selected_user}'.")
        return

    # --- SIDEBAR: TYPOLOGY DEFINITIONS DROPDOWN ---
    st.sidebar.divider()
    with st.sidebar.expander("📖 Typology Definitions"):
        for title, desc in TYPOLOGY_DEFINITIONS.items():
            st.markdown(f"**{title.title()}**")
            st.write(desc)
            st.divider()

    # --- SESSION STATE INITIALIZATION ---
    if "user_id" not in st.session_state or st.session_state.user_id != selected_user:
        st.session_state.user_id = selected_user
        st.session_state.current_idx = 0

        saved_annotations = load_existing_user_annotations(selected_user)
        st.session_state.annotations = {
            row["id"]: saved_annotations.get(row["id"], None) for _, row in user_df.iterrows()
        }
        st.session_state.db_submitted_count = len(saved_annotations)

    # Sidebar counter
    submitted_count = st.session_state.get("db_submitted_count", 0)
    st.sidebar.info(f"**Submitted:** {submitted_count} / {len(user_df)} profiles")

    # Clear All Responses Button
    if st.sidebar.button("Clear All Responses", use_container_width=True):
        delete_user_annotations(selected_user)
        st.session_state.annotations = {row["id"]: None for _, row in user_df.iterrows()}
        st.session_state.db_submitted_count = 0
        st.session_state.current_idx = 0
        st.sidebar.success("Cleared all responses from Google Sheets!")
        st.rerun()

    st.sidebar.divider()
    if st.sidebar.button("🔒 Exit App", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.page = "launch"
        st.rerun()

    idx = st.session_state.current_idx
    current_row = user_df.iloc[idx]
    current_id = current_row["id"]

    # --- TOP PROGRESS BAR & HEADER ---
    st.title("Political Typology Profile Annotator")

    progress = (idx + 1) / len(user_df)
    st.progress(progress)
    st.caption(
        f"Assigned User: **{selected_user}** | Profile **{idx + 1}** of **{len(user_df)}**"
    )

    # --- PROFILE DISPLAY ---
    col_left, col_right = st.columns([1, 1], gap="medium")

    # LEFT PANEL: Profile metadata
    with col_left:
        st.markdown(f"### Account: [:blue[@{current_row['account']}]]({current_row.get('url', '#')})")
        with st.container(height=450, key=f"left_container_{current_id}"):
            m1, m2, m3 = st.columns(3)
            m1.metric("Followers", f"{current_row['followers']:,}" if pd.notna(current_row["followers"]) else "N/A")
            m2.metric("Verified", "Yes" if current_row.get("is_verified") else "No")
            m3.metric("Category", str(current_row.get("category", current_row.get("account_category", "N/A"))))

            st.markdown(f"**Full Name:** {current_row['full_name']}")
            st.markdown("**Biography:**")

            bio_text = current_row["biography"] if pd.notna(current_row["biography"]) else "No biography available."
            st.markdown(
                f"""
                <div style="
                    font-size: 1.25rem; 
                    color: #111111; 
                    line-height: 1.5; 
                    background-color: #f8f9fa; 
                    padding: 14px; 
                    margin-top: 4px;
                ">
                    {bio_text}
                </div>
                """,
                unsafe_allow_html=True,
            )

    # RIGHT PANEL: Video Captions
    with col_right:
        st.subheader("Video Posts Captions")
        with st.container(height=450, key=f"video_container_{current_id}"):
            posts_list = current_row["parsed_posts"]
            if posts_list:
                posts_list = sorted(posts_list, key=lambda x: str(x.get("datetime", "")), reverse=True)
                for i, post in enumerate(posts_list, 1):
                    caption = post.get("caption", "No caption provided.")
                    content_type = post.get("content_type", "Video")
                    raw_dt = post.get("datetime")
                    dt = str(raw_dt)[:10] if pd.notna(raw_dt) and raw_dt else ""

                    st.markdown(f"**Video #{i}** *({content_type} • {dt})*")
                    st.write(f"{caption}")
                    st.divider()
            else:
                st.write("No video posts found for this profile.")

    # --- ANNOTATION SELECTION AREA ---
    st.markdown("---")
    st.subheader("Annotate Political Typology")

    existing_choice = st.session_state.annotations.get(current_id)
    default_index = TYPOLOGY_OPTIONS.index(existing_choice) if existing_choice in TYPOLOGY_OPTIONS else 0

    selected_typology = st.radio(
        "Select the political typology for this profile:",
        options=TYPOLOGY_OPTIONS,
        index=default_index,
        horizontal=True,
        key=f"radio_{current_id}",
    )

    st.session_state.annotations[current_id] = selected_typology

    # --- NAVIGATION & SUBMIT BUTTONS ---
    nav_col1, nav_col2, nav_col3 = st.columns([2, 4, 2])

    with nav_col1:
        if st.button("Previous", disabled=(idx == 0), use_container_width=True):
            st.session_state.current_idx -= 1
            st.rerun()

    with nav_col3:
        if idx < len(user_df) - 1:
            if st.button("Next", use_container_width=True):
                st.session_state.current_idx += 1
                st.rerun()

    with nav_col2:
        if st.button("Submit All Annotations", type="primary", use_container_width=True):
            save_user_annotations(selected_user, st.session_state.annotations, user_df)

            new_count = sum(1 for v in st.session_state.annotations.values() if v is not None)
            st.session_state.db_submitted_count = new_count

            st.success(f"All annotations for user '{selected_user}' have been saved directly to Google Sheets!")
            st.rerun()


# --- MAIN ROUTER ---
def main():
    st.set_page_config(page_title="Political Typology Annotator", layout="wide")

    if "page" not in st.session_state:
        st.session_state.page = "launch"

    if st.session_state.page == "explore_results":
        render_explore_results_page()
    elif st.session_state.page == "annotate" and st.session_state.get("authenticated", False):
        render_annotator_page()
    else:
        st.session_state.page = "launch"
        render_launch_page()


if __name__ == "__main__":
    main()