import ast
import os
from datetime import datetime
import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION ---
CSV_FILE = "data/annotation_dataset.csv"
BASE_DATA_CSV_FILE = os.path.join("data", "typology_dataset.csv")
LABELLED_CSV_FILE = os.path.join("data", "instagram_labelled_typology.csv")
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

TYPOLOGY_COLORS = {
    "leftward progressive": "#174d79",
    "loyal liberal": "#12689b",
    "left-out left": "#5a7dbe",
    "order and opportunity left": "#61a9bf",
    "tuned-out middle": "#cebf48",
    "pragmatic and polite right": "#ce703f",
    "unconventional right": "#f18878",
    "faith first conservative": "#c13c29",
    "no apologies right": "#912e20",
    "not applicable": "#747474",
}

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


# --- HELPER FUNCTIONS ---
def normalize_label(val):
    """Standardizes typology strings and maps long 'not applicable' label to 'not applicable'."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if s.lower() == "not applicable (the profile is not political)":
        return "not applicable"
    return s


def normalize_id(val):
    """Normalizes profile IDs consistently across CSVs (strips '.0' and float formatting)."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    if s.endswith(".0"):
        s = s[:-2]
    return s


def normalize_account(val):
    """Normalizes Instagram usernames for reliable cross-file matching."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip().lstrip("@").lower()
    return "" if s == "nan" else s


def render_label_badge(label_text):
    """Returns an HTML pill badge styled with the typology's assigned hex color."""
    clean_label = normalize_label(label_text)
    if not clean_label:
        return "<span style='color:#666;'>N/A</span>"

    key = clean_label.lower()
    bg_color = TYPOLOGY_COLORS.get(key, "#747474")
    text_color = "#111111" if key in {"tuned-out middle"} else "#ffffff"

    return (
        f"<span style='"
        f"background-color: {bg_color}; "
        f"color: {text_color}; "
        f"padding: 4px 12px; "
        f"border-radius: 14px; "
        f"font-weight: 600; "
        f"font-size: 0.9rem; "
        f"display: inline-block; "
        f"letter-spacing: 0.2px;"
        f"'>{clean_label}</span>"
    )


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
        df_sheet["id"] = df_sheet["id"].apply(normalize_id)
        df_sheet["user"] = df_sheet["user"].astype(str).str.strip()
        return df_sheet
    except Exception:
        return pd.DataFrame(columns=SHEET_COLUMNS)


def load_existing_user_annotations(user_id):
    """Loads a specific user's saved annotations from Google Sheets."""
    df_sheet = fetch_all_annotations()
    if df_sheet.empty or "user_label" not in df_sheet.columns:
        return {}
    user_rows = df_sheet[df_sheet["user"] == str(user_id).strip()]
    return dict(zip(user_rows["id"], user_rows["user_label"].apply(normalize_label)))


def save_user_annotations(user_id, annotations_dict, user_df):
    """Upserts user typology annotations along with Qwen model baseline data to Google Sheets."""
    conn = get_gsheets_connection()
    df_sheet = fetch_all_annotations()

    if not df_sheet.empty:
        df_sheet = df_sheet[df_sheet["user"].astype(str).str.strip() != str(user_id).strip()]

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
            norm_item_id = normalize_id(item_id)
            sub_df = user_df[user_df["id"].apply(normalize_id) == norm_item_id]

            acct_name = sub_df["account"].values[0] if not sub_df.empty and "account" in sub_df.columns else ""
            qwen_typ = sub_df[typ_col].values[0] if not sub_df.empty and typ_col else ""
            qwen_cert = sub_df[cert_col].values[0] if not sub_df.empty and cert_col else ""

            new_rows.append(
                {
                    "id": norm_item_id,
                    "account": str(acct_name),
                    "user": str(user_id).strip(),
                    "user_label": normalize_label(typology_val),
                    "qwen_label": normalize_label(qwen_typ),
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
        df_updated = df_sheet[df_sheet["user"].astype(str).str.strip() != str(user_id).strip()]
        conn.update(data=df_updated)
        st.cache_data.clear()


# --- DATA LOADING ---
@st.cache_data
def load_data():
    df = pd.read_csv(CSV_FILE, encoding="utf-8", dtype={"id": str})

    df["id"] = df["id"].apply(normalize_id)
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


@st.cache_data
def load_labelled_typology_data(annotation_usernames):
    """
    1. Reads data/instagram_labelled_typology.csv and joins profile info from data/typology_dataset.csv via `id`.
    2. Filters rows to only those whose username (`account`) matches a username in the annotations dataset.
    """
    if not annotation_usernames:
        return pd.DataFrame()

    # Load base metadata CSV (data/typology_dataset.csv)
    base_path = BASE_DATA_CSV_FILE if os.path.exists(BASE_DATA_CSV_FILE) else CSV_FILE
    df_base = pd.DataFrame()
    if os.path.exists(base_path):
        df_base = pd.read_csv(base_path, encoding="utf-8", dtype={"id": str})
        df_base["id"] = df_base["id"].apply(normalize_id)
        df_base = df_base[df_base["id"] != ""].drop_duplicates(subset=["id"]).reset_index(drop=True)

    # Load labelled typology CSV (data/instagram_labelled_typology.csv)
    lab_path = LABELLED_CSV_FILE if os.path.exists(LABELLED_CSV_FILE) else "instagram_labelled_typology.csv"
    if os.path.exists(lab_path):
        df_lab = pd.read_csv(lab_path, encoding="utf-8", dtype={"id": str})
        if "id" in df_lab.columns:
            df_lab["id"] = df_lab["id"].apply(normalize_id)
            df_lab = df_lab[df_lab["id"] != ""].drop_duplicates(subset=["id"]).reset_index(drop=True)
    else:
        df_lab = df_base.copy()

    if df_lab.empty:
        return pd.DataFrame()

    # Merge full profile info from data/typology_dataset.csv by `id`
    if not df_base.empty and "id" in df_lab.columns:
        meta_cols = [
            "account",
            "full_name",
            "biography",
            "is_verified",
            "followers",
            "url",
            "category",
            "political",
            "typology",
            "typology_justification",
            "typology_certainty",
            "account_summary",
            "info",
        ]
        available_meta = [c for c in meta_cols if c in df_base.columns]
        cols_to_drop = [c for c in available_meta if c in df_lab.columns and not c.startswith("qwen_")]
        df_lab = df_lab.drop(columns=cols_to_drop).merge(
            df_base[["id"] + available_meta], on="id", how="left"
        )

    if "account" not in df_lab.columns:
        return pd.DataFrame()

    # Filter using username (`account`) against the annotations dataset
    valid_usernames = {normalize_account(u) for u in annotation_usernames if normalize_account(u)}
    df_lab["account"] = df_lab["account"].fillna("").astype(str).str.strip()
    df_lab["account_norm"] = df_lab["account"].apply(normalize_account)
    df_lab = df_lab[df_lab["account_norm"].isin(valid_usernames)].copy()
    df_lab = df_lab.drop_duplicates(subset=["account_norm"]).reset_index(drop=True)

    if df_lab.empty:
        return df_lab

    # Standardize Qwen label column
    q_label_col = next(
        (c for c in ["qwen_label", "qwen_typology", "typology"] if c in df_lab.columns),
        None,
    )
    df_lab["qwen_label_clean"] = df_lab[q_label_col].apply(normalize_label) if q_label_col else ""

    # Standardize Qwen justification column
    q_just_col = next(
        (c for c in ["qwen_justification", "typology_justification", "justification"] if c in df_lab.columns),
        None,
    )
    df_lab["qwen_justification_clean"] = (
        df_lab[q_just_col].fillna("No justification provided.").astype(str)
        if q_just_col
        else "No justification provided."
    )

    # Standardize Qwen certainty column
    q_cert_col = next(
        (c for c in ["qwen_certainty", "typology_certainty", "certainty"] if c in df_lab.columns),
        None,
    )
    df_lab["qwen_certainty_clean"] = (
        df_lab[q_cert_col].fillna("N/A").astype(str) if q_cert_col else "N/A"
    )

    return df_lab


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
            st.session_state.pop("results_df", None)
            st.session_state.page = "explore_results"
            st.rerun()


# --- PAGE 2: EXPLORE RESULTS (ONLY ACCESSIBLE FROM LAUNCH PAGE) ---
def render_explore_results_page():
    top_col1, top_col2, top_col3 = st.columns([5, 1.5, 1.5])
    with top_col1:
        st.title("Annotation Results Explorer")
    with top_col2:
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.session_state.pop("results_df", None)
            st.rerun()
    with top_col3:
        if st.button("Back to Launch Page", use_container_width=True):
            st.session_state.page = "launch"
            st.rerun()

    # Save current state of the results CSV into session_state DataFrame & local snapshot
    if "results_df" not in st.session_state:
        df_live = fetch_all_annotations()
        if not df_live.empty:
            for col in ["id", "account", "user", "user_label", "qwen_label", "qwen_certainty"]:
                if col in df_live.columns:
                    df_live[col] = df_live[col].fillna("").astype(str).str.strip()
            df_live["id"] = df_live["id"].apply(normalize_id)
            if "user_label" in df_live.columns:
                df_live["user_label"] = df_live["user_label"].apply(normalize_label)
            if "qwen_label" in df_live.columns:
                df_live["qwen_label"] = df_live["qwen_label"].apply(normalize_label)

        st.session_state.results_df = df_live
        st.session_state.results_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df_live.to_csv(RESULTS_SNAPSHOT_FILE, index=False)

    df_results = st.session_state.results_df

    # --- 1. PRINTED DATAFRAME AT TOP ---
    st.caption(
        f"Snapshot captured at **{st.session_state.get('results_saved_at', '')}** | "
        f"**{len(df_results)}** rows × **{len(df_results.columns)}** columns"
    )
    st.dataframe(df_results, use_container_width=True, hide_index=True)

    st.divider()

    # --- 2. DROPDOWN: JUSTIFICATIONS ---
    with st.expander("Justifications", expanded=True):
        annotation_usernames = (
            tuple(sorted(df_results["account"].dropna().unique().tolist()))
            if not df_results.empty and "account" in df_results.columns
            else ()
        )
        df_lab = load_labelled_typology_data(annotation_usernames)

        if df_lab.empty:
            st.info("No matching usernames found between `data/instagram_labelled_typology.csv` and the annotations CSV.")
            return

        df_results_work = df_results.copy()
        df_results_work["account_norm"] = df_results_work["account"].apply(normalize_account)

        # Build ideology options ordered by TYPOLOGY_COLORS
        available_ideologies_lower = set(df_lab["qwen_label_clean"].str.lower().unique())
        ordered_ideologies = [
            ideo for ideo in TYPOLOGY_COLORS.keys() if ideo in available_ideologies_lower
        ]
        for raw_ideo in sorted(df_lab["qwen_label_clean"].unique()):
            if raw_ideo and raw_ideo.lower() not in TYPOLOGY_COLORS:
                ordered_ideologies.append(raw_ideo)

        if not ordered_ideologies:
            st.info("No `qwen_label` ideologies found for the matched usernames.")
            return

        # Color-coded ideology legend strip
        legend_html = " ".join(
            [
                f"<span style='background-color:{TYPOLOGY_COLORS.get(ideo.lower(), '#747474')}; "
                f"color:{'#111111' if ideo.lower() == 'tuned-out middle' else '#ffffff'}; "
                f"padding:2px 8px; border-radius:10px; font-size:0.78rem; font-weight:600; "
                f"display:inline-block; margin:2px;'>{ideo}</span>"
                for ideo in ordered_ideologies
            ]
        )
        st.markdown(legend_html, unsafe_allow_html=True)
        st.write("")

        filter_col1, filter_col2 = st.columns([1, 1], gap="medium")

        with filter_col1:
            ideo_counts = df_lab["qwen_label_clean"].str.lower().value_counts().to_dict()
            selected_ideology = st.selectbox(
                "Select Qwen Ideology (`qwen_label`):",
                options=ordered_ideologies,
                format_func=lambda x: f"{x} ({ideo_counts.get(x.lower(), 0)} profiles)",
                key="justifications_ideology_filter",
            )
            st.markdown(
                f"Selected Ideology: {render_label_badge(selected_ideology)}",
                unsafe_allow_html=True,
            )

        # Filter profiles matching the selected Qwen ideology
        filtered_profiles = df_lab[
            df_lab["qwen_label_clean"].str.lower() == selected_ideology.lower()
        ].copy()

        # Count student labels per username (`account_norm`)
        acct_counts = df_results_work.groupby("account_norm")["user"].count().to_dict()
        filtered_profiles["student_ann_count"] = filtered_profiles["account_norm"].map(
            lambda acc: acct_counts.get(acc, 0)
        )

        filtered_profiles = filtered_profiles.sort_values(
            by=["student_ann_count", "account"], ascending=[False, True]
        ).reset_index(drop=True)

        with filter_col2:
            profile_indices = list(range(len(filtered_profiles)))

            def format_profile_option(idx_val):
                r = filtered_profiles.iloc[idx_val]
                acct_str = str(r.get("account", "")).strip()
                cnt = r["student_ann_count"]
                return f"@{acct_str} ({cnt} student label{'' if cnt == 1 else 's'})"

            selected_prof_idx = st.selectbox(
                "Select Profile Account:",
                options=profile_indices,
                format_func=format_profile_option,
                key=f"justifications_profile_filter_{selected_ideology}",
            )

        st.markdown("---")

        prof_row = filtered_profiles.iloc[selected_prof_idx]
        prof_id = str(prof_row.get("id", ""))
        prof_account = str(prof_row.get("account", "")).strip()
        prof_account_norm = prof_row["account_norm"]
        prof_url = (
            prof_row.get("url")
            if pd.notna(prof_row.get("url")) and str(prof_row.get("url")).strip()
            else f"https://www.instagram.com/{prof_account}/"
        )

        # --- TWO-COLUMN PROFILE & LABELS VIEW ---
        col_left, col_right = st.columns([1, 1], gap="medium")

        # LEFT PANEL: Profile metadata from data/typology_dataset.csv
        with col_left:
            st.markdown(f"### Account: [:blue[@{prof_account}]]({prof_url})")
            with st.container(height=450, key=f"just_left_{prof_id}_{prof_account_norm}"):
                m1, m2, m3 = st.columns(3)
                followers_val = pd.to_numeric(prof_row.get("followers"), errors="coerce")
                m1.metric("Followers", f"{int(followers_val):,}" if pd.notna(followers_val) else "N/A")
                m2.metric(
                    "Verified",
                    "Yes"
                    if prof_row.get("is_verified") is True or str(prof_row.get("is_verified")).lower() == "true"
                    else "No",
                )
                m3.metric("Category", str(prof_row.get("category", "N/A")) if pd.notna(prof_row.get("category")) else "N/A")

                full_name_val = (
                    prof_row.get("full_name")
                    if pd.notna(prof_row.get("full_name")) and str(prof_row.get("full_name")).strip()
                    else "N/A"
                )
                st.markdown(f"**Full Name:** {full_name_val}")
                st.markdown("**Biography:**")

                bio_text = (
                    prof_row["biography"]
                    if "biography" in prof_row and pd.notna(prof_row["biography"]) and str(prof_row["biography"]).strip()
                    else "No biography available."
                )
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

                for extra_col, extra_label in [("account_summary", "Account Summary"), ("info", "Additional Info")]:
                    if extra_col in prof_row and pd.notna(prof_row[extra_col]) and str(prof_row[extra_col]).strip():
                        st.markdown(f"**{extra_label}:**")
                        st.write(str(prof_row[extra_col]))

        # RIGHT PANEL: Student labels (matched by username) + Qwen label, certainty & justification
        with col_right:
            st.subheader("Annotations & Qwen Justification")
            with st.container(height=450, key=f"just_right_{prof_id}_{prof_account_norm}"):
                st.markdown("**Student Labels:**")
                matched_students = df_results_work[df_results_work["account_norm"] == prof_account_norm]

                if not matched_students.empty:
                    for _, s_row in matched_students.iterrows():
                        s_user = s_row.get("user", "Unknown")
                        s_label = s_row.get("user_label", "")
                        badge_html = render_label_badge(s_label)
                        st.markdown(
                            f"<div style='margin-bottom:8px;'>👤 <strong>{s_user}</strong>: {badge_html}</div>",
                            unsafe_allow_html=True,
                        )
                else:
                    st.caption("No student annotations submitted for this profile yet.")

                st.divider()

                q_label = prof_row.get("qwen_label_clean", "")
                q_cert = prof_row.get("qwen_certainty_clean", "N/A")
                q_just = prof_row.get("qwen_justification_clean", "No justification provided.")

                q_col1, q_col2 = st.columns([1.4, 1])
                with q_col1:
                    st.markdown("**Qwen Label:**")
                    st.markdown(render_label_badge(q_label), unsafe_allow_html=True)
                with q_col2:
                    st.markdown("**Qwen Certainty:**")
                    if q_cert != "N/A":
                        st.markdown(f"""<p style="font-size:2rem;">{q_cert}%</p>""", unsafe_allow_html=True)
                    else:
                        st.markdown(f"""<p style="font-size:2rem;">{q_cert}</p>""", unsafe_allow_html=True)

                st.write("")

                st.markdown("**Qwen Justification:**")
                border_hex = TYPOLOGY_COLORS.get(q_label.lower(), "#747474")
                st.markdown(
                    f"""
                    <div style="
                        font-size: 1.02rem;
                        color: #111111;
                        line-height: 1.55;
                        background-color: #f8f9fa;
                        padding: 14px;
                        border-left: 5px solid {border_hex};
                        border-radius: 6px;
                        margin-top: 4px;
                    ">
                        {q_just}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


# --- PAGE 3: STUDENT ANNOTATOR WORKSPACE ---
def render_annotator_page():

    st.set_page_config(page_title="Political Typology Annotator", layout="wide")

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
        return

    user_df = df[df["user"] == selected_user].reset_index(drop=True)

    if user_df.empty:
        st.warning(f"No profiles assigned to user '{selected_user}'.")
        return

    # --- SIDEBAR: TYPOLOGY DEFINITIONS DROPDOWN ---
    st.sidebar.divider()
    with st.sidebar.expander("Typology Definitions"):
        for title, desc in TYPOLOGY_DEFINITIONS.items():
            st.markdown(f"**{title.title()}**")
            st.caption(desc)
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
            m1.metric("Followers", f"{current_row['followers']:,}" if pd.notna(current_row['followers']) else "N/A")
            m2.metric("Verified", "Yes" if current_row.get("is_verified") else "No")
            m3.metric("Category (labelled by AI)", str(current_row.get("category", current_row.get("account_category", "N/A"))))

            st.markdown(f"**Full Name:** {current_row['full_name']}")
            st.markdown("**Biography:**")

            bio_text = current_row['biography'] if pd.notna(current_row['biography']) else "No biography available."
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
                    
                    # Safely extract and slice date regardless of missing/null data types
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